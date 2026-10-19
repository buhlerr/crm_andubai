"""Importação da base de alunos (planilha semanal, aba "Base").

Fluxo: criar_previa() -> a equipe confere o resumo -> confirmar() ou descartar().
Detalhes do fluxo em app/importacao/comum.py.
"""

import os
from collections import Counter, defaultdict
from dataclasses import dataclass

from app import publico_teen
from app.extensions import db
from app.importacao import ErroImportacao, comum
from app.importacao.comum import Coletor
from app.importacao.consultores import ResolvedorConsultor
from app.importacao.valores import (
    IdInvalido,
    normalizar_id_egali,
    para_data,
    para_decimal,
    para_texto,
    separar_compras,
)
from app.models import (
    Aluno,
    Compra,
    Importacao,
    OrigemCompra,
    Programa,
    SituacaoPrograma,
    Tarefa,
    TipoImportacao,
    TipoOcorrencia,
    TipoPrograma,
)
from app.models.base import agora

NOME_ABA = "Base"

COL_PROGRAMA = "programa_id"
COL_ALUNO = "aluno_id"
COL_NOME = "aluno_name"
COL_COMPRAS = "compra_id"
COL_CONSULTOR = "consultor"
COLUNAS_OBRIGATORIAS = (COL_PROGRAMA, COL_ALUNO, COL_NOME, COL_COMPRAS, COL_CONSULTOR)

# Atributo do Programa -> (coluna da planilha, conversor, rótulo na tela).
CAMPOS = {
    "mes_embarque": ("mês embarque", para_data, "Mês de embarque"),
    "data_embarque": ("programa_data_embarque", para_data, "Data de embarque"),
    "visto_normalizado": ("visto normalizado", para_texto, "Visto"),
    "pais": ("pais_name", para_texto, "País"),
    "cidade": ("cidade_name", para_texto, "Cidade"),
    "escola": ("escola_name", para_texto, "Escola"),
    "acomodacao": ("acomodacao_tipo", para_texto, "Acomodação"),
    "grupo": ("grupo", para_texto, "Grupo"),
    "pontuacao": ("pt_prog", para_decimal, "Pontuação"),
    # Usados para marcar o público teen (app/publico_teen.py).
    "servicos_egali": ("servico_name", para_texto, "Serviços contratados"),
    "tags_egali": ("tags", para_texto, "Tags"),
}
ROTULOS = {"aluno": "Aluno", "consultor": "Consultor", **{k: v[2] for k, v in CAMPOS.items()}}

COLUNAS_USADAS = frozenset(COLUNAS_OBRIGATORIAS) | {c[0] for c in CAMPOS.values()}

# Aviso de segurança: muitos cancelamentos de uma vez costumam ser arquivo errado ou filtrado.
LIMITE_CANCELAMENTO_MINIMO = 10
LIMITE_CANCELAMENTO_FRACAO = 0.2

CONTAGENS = (
    "alunos_novos", "alunos_renomeados",
    "programas_novos", "programas_atualizados", "programas_sem_mudanca", "programas_reativados",
    "programas_cancelados", "programas_so_visto_incorporados", "programas_sem_consultor",
    "compras_ligadas", "compras_movidas", "compras_desligadas",
)


@dataclass
class LinhaBase:
    linha: int
    programa_id: str
    aluno_id: str
    nome: str
    compras: list[str]
    consultor_texto: str | None
    campos: dict


# ---------------------------------------------------------------- leitura


def interpretar(linhas_brutas: list[dict], coletor: Coletor) -> list[LinhaBase]:
    if not linhas_brutas:
        raise ErroImportacao("A planilha não tem nenhuma linha de dados.")
    colunas = set().union(*(b["valores"].keys() for b in linhas_brutas))
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in colunas]
    if faltando:
        raise ErroImportacao(
            f"A planilha não tem a(s) coluna(s): {', '.join(faltando)}. "
            f"Confira se é o arquivo certo e se a aba '{NOME_ABA}' tem o cabeçalho na primeira linha."
        )

    primeira_linha_do_programa: dict[str, int] = {}
    resultado = []
    for bruta in linhas_brutas:
        n, v = bruta["linha"], bruta["valores"]
        if all(para_texto(v.get(c)) is None for c in (COL_PROGRAMA, COL_ALUNO, COL_NOME, COL_COMPRAS)):
            # Ex.: a coluna "Enviado" com "Sim" em linhas abaixo dos dados. Não é aluno.
            coletor.linhas_ignoradas += 1
            continue
        try:
            programa_id = normalizar_id_egali(v.get(COL_PROGRAMA))
            aluno_id = normalizar_id_egali(v.get(COL_ALUNO))
        except IdInvalido as erro:
            coletor.erro(TipoOcorrencia.LINHA_INVALIDA, f"ID que não é um número: {erro.args[0]!r}. A linha não foi importada.", n)
            continue
        if not programa_id:
            coletor.erro(TipoOcorrencia.SEM_PROGRAMA_ID, "Linha sem programa_id. Não foi importada.", n, aluno_id)
            continue
        if not aluno_id:
            coletor.erro(TipoOcorrencia.SEM_ALUNO_ID, "Linha sem aluno_id. Não foi importada.", n, programa_id)
            continue
        if programa_id in primeira_linha_do_programa:
            coletor.erro(
                TipoOcorrencia.LINHA_INVALIDA,
                f"O programa {programa_id} aparece de novo (já estava na linha {primeira_linha_do_programa[programa_id]}). "
                "Esta linha não foi importada.",
                n, programa_id,
            )
            continue
        nome = para_texto(v.get(COL_NOME))
        if not nome:
            coletor.erro(TipoOcorrencia.LINHA_INVALIDA, "Linha sem nome do aluno. Não foi importada.", n, programa_id)
            continue

        compras, invalidas = separar_compras(v.get(COL_COMPRAS))
        if invalidas:
            coletor.aviso(
                TipoOcorrencia.LINHA_INVALIDA,
                f"Pedaço(s) da coluna compra_id que não são IDs e foram ignorados: {', '.join(invalidas)}.",
                n, programa_id,
            )

        campos = {}
        for atributo, (coluna, converter, rotulo) in CAMPOS.items():
            if coluna not in colunas:
                continue  # coluna ausente no arquivo: não mexe no valor que já existe
            try:
                campos[atributo] = converter(v.get(coluna))
            except ValueError:
                coletor.aviso(
                    TipoOcorrencia.LINHA_INVALIDA,
                    f"{rotulo} com valor inválido ({v.get(coluna)!r}). O valor atual foi mantido.",
                    n, programa_id,
                )

        primeira_linha_do_programa[programa_id] = n
        resultado.append(LinhaBase(n, programa_id, aluno_id, nome, compras, para_texto(v.get(COL_CONSULTOR)), campos))
    return resultado


# ---------------------------------------------------------------- sincronização


def _sincronizar(linhas: list[LinhaBase], coletor: Coletor, importacao_id: int | None) -> dict:
    """Aplica a planilha na sessão, sem commit. Devolve o resumo."""
    momento = agora()
    alunos = {a.aluno_id_egali: a for a in db.session.execute(db.select(Aluno)).scalars()}
    programas = {
        p.programa_id_egali: p
        for p in db.session.execute(db.select(Programa).where(Programa.programa_id_egali.is_not(None))).scalars()
    }
    compras = {c.compra_id_egali: c for c in db.session.execute(db.select(Compra)).scalars()}
    resolvedor = ResolvedorConsultor()

    ativos_antes = sum(1 for p in programas.values() if p.tipo == TipoPrograma.NORMAL and p.ativo)
    cont = Counter({c: 0 for c in CONTAGENS})
    detalhes = defaultdict(list)
    renomeados: set[str] = set()
    alunos_criados: set[str] = set()
    dono_da_compra: dict[str, str] = {}  # compra -> programa em que apareceu neste arquivo
    problemas_consultor: dict[tuple, list[str]] = defaultdict(list)

    for linha in linhas:
        aluno = alunos.get(linha.aluno_id)
        if aluno is None:
            aluno = Aluno(aluno_id_egali=linha.aluno_id, nome=linha.nome)
            db.session.add(aluno)
            alunos[linha.aluno_id] = aluno
            alunos_criados.add(linha.aluno_id)
            cont["alunos_novos"] += 1
        elif aluno.nome != linha.nome:
            if linha.aluno_id not in alunos_criados and linha.aluno_id not in renomeados:
                renomeados.add(linha.aluno_id)
                cont["alunos_renomeados"] += 1
                detalhes["alunos_renomeados"].append({"aluno_id": linha.aluno_id, "de": aluno.nome, "para": linha.nome})
            aluno.nome = linha.nome

        programa = programas.get(linha.programa_id)
        novo = programa is None
        mudou: list[str] = []
        if novo:
            programa = Programa(programa_id_egali=linha.programa_id, aluno=aluno, tipo=TipoPrograma.NORMAL)
            db.session.add(programa)
            programas[linha.programa_id] = programa
        else:
            if programa.aluno is not aluno:
                coletor.aviso(
                    TipoOcorrencia.DIVERGENCIA_ALUNO,
                    f"O programa {linha.programa_id} era do aluno {programa.aluno.aluno_id_egali} e agora aparece "
                    f"com o aluno {linha.aluno_id}. A ligação foi atualizada.",
                    linha.linha, linha.programa_id,
                )
                programa.aluno = aluno
                mudou.append("aluno")
            if programa.situacao == SituacaoPrograma.CANCELADO:
                programa.situacao = SituacaoPrograma.ATIVO
                programa.reativado_em = momento
                cont["programas_reativados"] += 1
                detalhes["programas_reativados"].append({"programa_id": linha.programa_id, "aluno": linha.nome})

        consultor_id, problema = resolvedor.resolver(linha.consultor_texto)
        if problema:
            problemas_consultor[(linha.consultor_texto, problema)].append(linha.programa_id)
        if consultor_id is None:
            cont["programas_sem_consultor"] += 1
        if not programa.consultor_do_checklist and (
            programa.consultor_texto != linha.consultor_texto or programa.consultor_id != consultor_id
        ):
            mudou.append("consultor")
            programa.consultor_texto = linha.consultor_texto
            programa.consultor_id = consultor_id

        for atributo, valor in linha.campos.items():
            if getattr(programa, atributo) != valor:
                mudou.append(atributo)
                setattr(programa, atributo, valor)
        programa.ultima_importacao_id = importacao_id

        _ligar_compras(programa, linha, compras, dono_da_compra, cont, coletor, momento)

        if novo:
            cont["programas_novos"] += 1
            detalhes["programas_novos"].append({"programa_id": linha.programa_id, "aluno": linha.nome})
        elif mudou:
            cont["programas_atualizados"] += 1
            detalhes["programas_atualizados"].append(
                {"programa_id": linha.programa_id, "aluno": linha.nome, "campos": [ROTULOS[c] for c in mudou]}
            )
        else:
            cont["programas_sem_mudanca"] += 1

    no_arquivo = {linha.programa_id for linha in linhas}
    _desligar_compras(compras, dono_da_compra, no_arquivo, cont, momento)
    _cancelar_ausentes(programas, no_arquivo, cont, detalhes, momento)
    _incorporar_so_visto(cont, detalhes, coletor)
    db.session.flush()
    publico_teen.recalcular()

    for (texto, problema), ids in problemas_consultor.items():
        coletor.aviso(
            TipoOcorrencia.CONSULTOR_NAO_ENCONTRADO,
            f"Consultor \"{texto}\": {problema} ({len(ids)} programa(s)). "
            "Cadastre o usuário ou uma exceção de nome; até lá, esses programas ficam sem consultor.",
            chave=texto,
        )

    cancelados = cont["programas_cancelados"]
    if ativos_antes and cancelados >= LIMITE_CANCELAMENTO_MINIMO and cancelados / ativos_antes > LIMITE_CANCELAMENTO_FRACAO:
        coletor.aviso(
            TipoOcorrencia.CANCELAMENTO_EM_MASSA,
            f"Atenção: {cancelados} de {ativos_antes} programas ativos ({cancelados / ativos_antes:.0%}) seriam cancelados. "
            "Confira se é a planilha certa e se ela não está filtrada antes de confirmar.",
        )

    db.session.flush()
    return {"linhas_importadas": len(linhas), **cont, "detalhes": dict(detalhes)}


def _ligar_compras(programa, linha, compras, dono_da_compra, cont, coletor, momento):
    for compra_id in linha.compras:
        if compra_id in dono_da_compra:
            coletor.aviso(
                TipoOcorrencia.LINHA_INVALIDA,
                f"A compra {compra_id} aparece nos programas {dono_da_compra[compra_id]} e {linha.programa_id}. "
                f"Ficou no programa {dono_da_compra[compra_id]}.",
                linha.linha, compra_id,
            )
            continue
        dono_da_compra[compra_id] = linha.programa_id

        compra = compras.get(compra_id)
        if compra is None:
            compra = Compra(compra_id_egali=compra_id, programa=programa, origem=OrigemCompra.PLANILHA, ligada_em=momento)
            db.session.add(compra)
            compras[compra_id] = compra
            cont["compras_ligadas"] += 1
        elif compra.programa is not programa:
            if compra.programa is None:
                cont["compras_ligadas"] += 1
            else:
                cont["compras_movidas"] += 1
                # A tarefa segue a compra.
                for tarefa in db.session.execute(db.select(Tarefa).filter_by(compra_id=compra.id)).scalars():
                    tarefa.programa = programa
            compra.programa = programa
            compra.ligada_em = momento
            compra.desligada_em = None
        compra.origem = OrigemCompra.PLANILHA


def _desligar_compras(compras, dono_da_compra, no_arquivo, cont, momento):
    """Compra que saiu da célula compra_id é desligada do programa. Só vale para
    compras que vieram da planilha e de programas que estão no arquivo: compras
    juntadas pelo checklist e programas que sumiram (cancelados) ficam como estão."""
    for compra_id, compra in compras.items():
        if (
            compra.origem == OrigemCompra.PLANILHA
            and compra.programa is not None
            and compra.programa.programa_id_egali in no_arquivo
            and compra_id not in dono_da_compra
        ):
            compra.programa = None
            compra.desligada_em = momento
            cont["compras_desligadas"] += 1


def _cancelar_ausentes(programas, no_arquivo, cont, detalhes, momento):
    for programa_id, programa in programas.items():
        if programa.tipo == TipoPrograma.NORMAL and programa.ativo and programa_id not in no_arquivo:
            programa.situacao = SituacaoPrograma.CANCELADO
            programa.cancelado_em = momento
            cont["programas_cancelados"] += 1
            detalhes["programas_cancelados"].append({"programa_id": programa_id, "aluno": programa.aluno.nome})


def _incorporar_so_visto(cont, detalhes, coletor):
    """Aluno só de visto que apareceu na planilha com um programa de curso: o
    programa só de visto (compras e tarefas) é juntado a esse programa."""
    db.session.flush()
    so_visto = db.session.execute(
        db.select(Programa).filter_by(tipo=TipoPrograma.SO_VISTO, situacao=SituacaoPrograma.ATIVO)
    ).scalars().all()
    for origem in so_visto:
        destinos = [p for p in origem.aluno.programas if p.tipo == TipoPrograma.NORMAL and p.ativo]
        if len(destinos) == 1:
            destino = destinos[0]
            for compra in list(origem.compras):
                compra.programa = destino
            for tarefa in list(origem.tarefas):
                tarefa.programa = destino
            origem.situacao = SituacaoPrograma.INCORPORADO
            origem.incorporado_ao_programa_id = destino.id
            cont["programas_so_visto_incorporados"] += 1
            detalhes["programas_so_visto_incorporados"].append(
                {"aluno": origem.aluno.nome, "programa_id": destino.programa_id_egali}
            )
        elif len(destinos) > 1:
            coletor.aviso(
                TipoOcorrencia.ALUNO_COM_VARIOS_PROGRAMAS,
                f"{origem.aluno.nome} tem vistos avulsos e {len(destinos)} programas na planilha. "
                "Escolha à mão em qual programa os vistos devem ficar.",
                chave=origem.aluno.aluno_id_egali,
            )


# ---------------------------------------------------------------- fluxo prévia -> confirmação


def _processar(linhas_brutas, coletor, importacao_id, _parametros) -> dict:
    return _sincronizar(interpretar(linhas_brutas, coletor), coletor, importacao_id)


def criar_previa(linhas_brutas, arquivo_nome=None, arquivo_hash=None, usuario_id=None) -> Importacao:
    return comum.criar_previa(
        TipoImportacao.BASE_ALUNOS, comum.so_colunas(linhas_brutas, COLUNAS_USADAS), _processar,
        arquivo_nome=arquivo_nome, arquivo_hash=arquivo_hash, usuario_id=usuario_id,
    )


def confirmar(importacao: Importacao) -> Importacao:
    return comum.confirmar(importacao, TipoImportacao.BASE_ALUNOS, _processar, CONTAGENS)


descartar = comum.descartar


def importar_arquivo(caminho: str, usuario_id: int | None = None) -> Importacao:
    """Lê a planilha pelo Excel e cria a prévia."""
    from app.importacao.leitor_excel import ler_planilha

    linhas_brutas = ler_planilha(caminho, NOME_ABA, colunas_texto=(COL_COMPRAS,))
    return criar_previa(linhas_brutas, os.path.basename(caminho), comum.hash_arquivo(caminho), usuario_id)
