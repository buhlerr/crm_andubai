"""Importação do checklist da Egali (checklistServicoNew.csv). É ela que cria as tarefas.

Cada linha é um item pendente no sistema Egali, identificado pela coluna "#".
- Item novo: cria a tarefa.
- Item que já existe: atualiza o que vem da Egali (prazo, NEG, procedimento,
  programa). O trabalho da equipe (status, responsável, prazo manual,
  anotações) nunca é tocado.
- Item que sumiu: foi finalizado ou cancelado na Egali. A tarefa é encerrada.
  Com exportação por período, só vale para prazos dentro do período.
- Item encerrado que reaparece: a tarefa é reaberta.

Fluxo: criar_previa() -> a equipe confere o resumo -> confirmar() ou descartar().
"""

import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from app import publico_teen
from app.extensions import db
from app.importacao import ErroImportacao, comum
from app.importacao.comum import Coletor
from app.importacao.consultores import ResolvedorConsultor
from app.importacao.valores import IdInvalido, normalizar_id_egali, para_data, para_texto
from app.models import (
    PONTUACAO_VIP,
    Aluno,
    ApelidoEtapa,
    CategoriaServico,
    Compra,
    EtapaModelo,
    Gravidade,
    HistoricoTarefa,
    Importacao,
    OcorrenciaImportacao,
    MotivoEncerramento,
    OrigemCompra,
    Programa,
    ServicoEgali,
    SituacaoImportacao,
    StatusTarefa,
    Tarefa,
    TipoImportacao,
    TipoOcorrencia,
    TipoPrograma,
    Trilha,
)
from app.models.base import agora, hora_local
from app.texto import normalizar_texto

COL_ITEM = "#"
COL_COMPRA = "id da compra"
COL_ALUNO = "id aluno"
COL_NOME = "aluno"
COL_NEG = "neg"
COL_CONSULTOR = "consultor"
COL_DATA = "data"
COL_STATUS = "status"
COL_PROCEDIMENTO = "procedimento"
COL_SERVICO = "serviço"
COL_PAIS = "país"
COL_EMBARQUE = "embarque"
COL_TAGS = "tags"  # usada para marcar o público teen (tag "summer")
COLUNAS_OBRIGATORIAS = (COL_ITEM, COL_COMPRA, COL_ALUNO, COL_PROCEDIMENTO, COL_DATA)
COLUNAS_USADAS = frozenset(COLUNAS_OBRIGATORIAS) | {
    COL_NOME, COL_NEG, COL_CONSULTOR, COL_STATUS, COL_SERVICO, COL_PAIS, COL_EMBARQUE, COL_TAGS,
}

# Aviso de segurança: encerrar a maior parte das tarefas de uma vez costuma ser arquivo errado.
LIMITE_ENCERRAMENTO_MINIMO = 20
LIMITE_ENCERRAMENTO_FRACAO = 0.5

CONTAGENS = (
    "tarefas_novas", "tarefas_atualizadas", "tarefas_sem_mudanca", "tarefas_reabertas",
    "tarefas_finalizadas", "tarefas_canceladas", "tarefas_fora_do_periodo",
    "compras_juntadas", "programas_so_visto_criados", "alunos_criados",
    "itens_ignorados", "itens_sem_programa", "etapas_criadas",
)


@dataclass
class LinhaChecklist:
    linha: int
    item: str
    compra_id: str
    aluno_id: str
    nome: str | None
    procedimento: str
    prazo: date | None
    neg: str | None
    status: str | None
    consultor: str | None
    servico: str | None
    pais: str | None
    embarque: date | None
    tags: str | None = None


# ---------------------------------------------------------------- leitura


def interpretar(linhas_brutas: list[dict], coletor: Coletor) -> list[LinhaChecklist]:
    if not linhas_brutas:
        raise ErroImportacao("O arquivo não tem nenhuma linha de dados.")
    colunas = set().union(*(b["valores"].keys() for b in linhas_brutas))
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in colunas]
    if faltando:
        raise ErroImportacao(
            f"O arquivo não tem a(s) coluna(s): {', '.join(faltando)}. "
            "Confira se é a exportação de checklist (checklistServicoNew.csv)."
        )

    primeira_linha: dict[str, int] = {}
    resultado = []
    for bruta in linhas_brutas:
        n, v = bruta["linha"], bruta["valores"]
        if all(para_texto(v.get(c)) is None for c in (COL_ITEM, COL_COMPRA, COL_ALUNO, COL_PROCEDIMENTO)):
            coletor.linhas_ignoradas += 1
            continue
        try:
            item = normalizar_id_egali(v.get(COL_ITEM))
            compra_id = normalizar_id_egali(v.get(COL_COMPRA))
            aluno_id = normalizar_id_egali(v.get(COL_ALUNO))
        except IdInvalido as erro:
            coletor.erro(TipoOcorrencia.LINHA_INVALIDA, f"ID que não é um número: {erro.args[0]!r}. A linha não foi importada.", n)
            continue
        procedimento = para_texto(v.get(COL_PROCEDIMENTO))
        faltou = [nome for nome, valor in (("#", item), ("Id da Compra", compra_id), ("Procedimento", procedimento)) if not valor]
        if faltou:
            coletor.erro(TipoOcorrencia.LINHA_INVALIDA, f"Linha sem {', '.join(faltou)}. Não foi importada.", n, item)
            continue
        if not aluno_id:
            coletor.erro(TipoOcorrencia.SEM_ALUNO_ID, "Linha sem ID Aluno. Não foi importada.", n, item)
            continue
        if item in primeira_linha:
            coletor.erro(
                TipoOcorrencia.LINHA_INVALIDA,
                f"O item {item} aparece de novo (já estava na linha {primeira_linha[item]}). Esta linha não foi importada.",
                n, item,
            )
            continue
        try:
            prazo = para_data(v.get(COL_DATA))
        except ValueError:
            coletor.aviso(TipoOcorrencia.LINHA_INVALIDA, f"Data inválida ({v.get(COL_DATA)!r}). A tarefa fica sem prazo.", n, item)
            prazo = None
        try:
            embarque = para_data(v.get(COL_EMBARQUE))
        except ValueError:
            embarque = None

        primeira_linha[item] = n
        neg = (v.get(COL_NEG) or "").strip() or None
        resultado.append(LinhaChecklist(
            n, item, compra_id, aluno_id, para_texto(v.get(COL_NOME)), procedimento, prazo, neg,
            para_texto(v.get(COL_STATUS)), para_texto(v.get(COL_CONSULTOR)), para_texto(v.get(COL_SERVICO)),
            para_texto(v.get(COL_PAIS)), embarque, para_texto(v.get(COL_TAGS)),
        ))
    return resultado


def periodo_do_arquivo(linhas_brutas: list[dict]) -> tuple[date | None, date | None]:
    """Menor e maior prazo do arquivo: sugestão de período da exportação."""
    prazos = []
    for bruta in linhas_brutas:
        try:
            prazo = para_data(bruta["valores"].get(COL_DATA))
        except ValueError:
            continue
        if prazo:
            prazos.append(prazo)
    return (min(prazos), max(prazos)) if prazos else (None, None)


# ---------------------------------------------------------------- sincronização


class _Sincronizacao:
    def __init__(self, coletor: Coletor, importacao_id: int | None, periodo_inicio, periodo_fim):
        self.coletor = coletor
        self.importacao_id = importacao_id
        self.periodo = (periodo_inicio, periodo_fim) if periodo_inicio else None
        self.momento = agora()
        self.cont = Counter({c: 0 for c in CONTAGENS})
        self.detalhes = defaultdict(list)
        self.campos_atualizados = Counter()

        # Tudo carregado de uma vez; as buscas por linha usam o que já está na memória.
        self.trilhas = {t.codigo: t for t in db.session.execute(db.select(Trilha)).scalars()}
        db.session.execute(db.select(EtapaModelo)).scalars().all()
        self.etapas = {a.texto_normalizado: a.etapa for a in db.session.execute(db.select(ApelidoEtapa)).scalars()}
        self.servicos = {s.nome_normalizado: s for s in db.session.execute(db.select(ServicoEgali)).scalars()}
        self.alunos = {a.aluno_id_egali: a for a in db.session.execute(db.select(Aluno)).scalars()}
        programas = db.session.execute(db.select(Programa)).scalars().all()
        self.so_visto = {p.aluno_id: p for p in programas if p.tipo == TipoPrograma.SO_VISTO and p.ativo}
        self.compras = {c.compra_id_egali: c for c in db.session.execute(db.select(Compra)).scalars()}
        self.tarefas = {t.item_checklist_egali: t for t in db.session.execute(db.select(Tarefa)).scalars()}
        self.abertas_antes = sum(1 for t in self.tarefas.values() if t.encerrada_egali_em is None)
        self.resolvedor = ResolvedorConsultor()
        self.consultores_antes = {p.id: p.consultor_texto for p in programas}

        # Problemas agrupados, para não gerar uma ocorrência por linha.
        self.sem_programa: dict[tuple, dict] = {}  # (tipo, compra) -> dados
        self.servico_pendente: Counter = Counter()
        self.consultor_divergente: Counter = Counter()
        self.vip_abaixo: dict[int, Programa] = {}

    # -- etapa

    def etapa(self, linha: LinhaChecklist) -> EtapaModelo | None:
        chave = normalizar_texto(linha.procedimento)
        if chave in self.etapas:
            return self.etapas[chave]
        partes = [p.strip() for p in linha.procedimento.split(" - ", 2)]
        if len(partes) != 3 or partes[0].upper() != "SA" or not partes[1] or not partes[2]:
            self.coletor.erro(
                TipoOcorrencia.LINHA_INVALIDA,
                f"Procedimento fora do formato \"SA - <trilha> - <etapa>\": {linha.procedimento}. Não foi importado.",
                linha.linha, linha.item,
            )
            return None
        from app.catalogo_inicial import trilha_do_codigo

        codigo, nome = trilha_do_codigo(partes[1].upper()), partes[2]  # ex.: CAN faz parte de VISTOS
        trilha = self.trilhas.get(codigo)
        if trilha is None:
            trilha = Trilha(codigo=codigo, nome=codigo, ordem=max((t.ordem for t in self.trilhas.values()), default=0) + 1)
            db.session.add(trilha)
            self.trilhas[codigo] = trilha
            self.coletor.aviso(TipoOcorrencia.PROCEDIMENTO_NOVO, f"Trilha nova incluída: {codigo}. Dê um nome a ela na tela do catálogo.", chave=codigo)
        etapa = next((e for e in trilha.etapas if normalizar_texto(e.nome) == normalizar_texto(nome)), None)
        if etapa is None:
            etapa = EtapaModelo(trilha=trilha, nome=nome, texto_egali=linha.procedimento, ordem=1000, criada_automaticamente=True)
            db.session.add(etapa)
            self.cont["etapas_criadas"] += 1
            self.detalhes["etapas_criadas"].append(linha.procedimento)
            self.coletor.aviso(
                TipoOcorrencia.PROCEDIMENTO_NOVO,
                f"Procedimento novo incluído no catálogo: {linha.procedimento}. Complete as orientações na tela do catálogo.",
                chave=linha.item,
            )
        db.session.add(ApelidoEtapa(etapa=etapa, texto=linha.procedimento, texto_normalizado=chave))
        self.etapas[chave] = etapa
        return etapa

    # -- programa e compra

    def servico(self, nome: str | None) -> ServicoEgali | None:
        if not nome:
            return None
        chave = normalizar_texto(nome)
        if chave not in self.servicos:
            self.servicos[chave] = ServicoEgali(nome=nome, nome_normalizado=chave, categoria=CategoriaServico.NAO_CLASSIFICADO)
            db.session.add(self.servicos[chave])
        return self.servicos[chave]

    def _sem_programa(self, tipo, linha: LinhaChecklist, motivo: str):
        self.cont["itens_sem_programa"] += 1
        dados = self.sem_programa.setdefault(
            (tipo, linha.compra_id),
            {"compra_id": linha.compra_id, "aluno_id": linha.aluno_id, "aluno": linha.nome, "servico": linha.servico,
             "motivo": motivo, "itens": 0, "linha": linha.linha},
        )
        dados["itens"] += 1

    def programa_e_compra(self, linha: LinhaChecklist) -> tuple[Programa, Compra] | None:
        compra = self.compras.get(linha.compra_id)
        if compra is not None and compra.programa is not None:
            programa = compra.programa
            if programa.aluno.aluno_id_egali != linha.aluno_id:
                self.coletor.erro(
                    TipoOcorrencia.DIVERGENCIA_ALUNO,
                    f"Item {linha.item}: o ID Aluno do checklist ({linha.aluno_id}) é diferente do aluno do programa "
                    f"{programa.programa_id_egali or '(só de visto)'} ({programa.aluno.aluno_id_egali}). Não foi importado.",
                    linha.linha, linha.item,
                )
                return None
            if compra.servico != linha.servico and linha.servico:
                compra.servico = linha.servico
            return programa, compra

        # Compra que não está em nenhum programa da planilha.
        servico = self.servico(linha.servico)
        categoria = servico.categoria if servico else CategoriaServico.NAO_CLASSIFICADO
        if categoria == CategoriaServico.IGNORADO:
            self.cont["itens_ignorados"] += 1
            return None
        if categoria == CategoriaServico.NAO_CLASSIFICADO:
            self.servico_pendente[linha.servico or "(sem serviço)"] += 1
            self.cont["itens_sem_programa"] += 1
            return None
        aluno = self.alunos.get(linha.aluno_id)
        normais = [p for p in aluno.programas if p.tipo == TipoPrograma.NORMAL and p.ativo] if aluno else []
        if categoria == CategoriaServico.CURSO:
            if normais:
                motivo = (
                    f"o aluno está na planilha (programa {', '.join(p.programa_id_egali for p in normais)}), mas esta "
                    "compra de curso não está na coluna compra_id: pode ser um segundo programa ou uma compra "
                    "mais nova que a planilha"
                )
            else:
                motivo = "o aluno não está na planilha: venda mais nova que a planilha ou programa que ficou de fora"
            self._sem_programa(TipoOcorrencia.PROGRAMA_FALTANDO_NA_PLANILHA, linha, motivo)
            return None
        if len(normais) > 1:
            self._sem_programa(TipoOcorrencia.ALUNO_COM_VARIOS_PROGRAMAS, linha, f"aluno com {len(normais)} programas")
            return None
        if normais:
            destino = normais[0]
        elif aluno is not None and aluno.id in self.so_visto:
            destino = self.so_visto[aluno.id]
        elif categoria == CategoriaServico.VISTO:
            if aluno is None:
                aluno = Aluno(aluno_id_egali=linha.aluno_id, nome=linha.nome or f"Aluno {linha.aluno_id}")
                db.session.add(aluno)
                self.alunos[linha.aluno_id] = aluno
                self.cont["alunos_criados"] += 1
            destino = Programa(aluno=aluno, tipo=TipoPrograma.SO_VISTO)
            db.session.add(destino)
            db.session.flush()
            self.so_visto[aluno.id] = destino
            self.cont["programas_so_visto_criados"] += 1
            self.detalhes["programas_so_visto_criados"].append({"aluno_id": linha.aluno_id, "aluno": aluno.nome})
        else:  # avulso (ex.: transfer) sem nenhum programa do aluno
            self._sem_programa(TipoOcorrencia.PROGRAMA_FALTANDO_NA_PLANILHA, linha, "serviço avulso sem programa do aluno")
            return None

        if compra is None:
            compra = Compra(compra_id_egali=linha.compra_id, origem=OrigemCompra.CHECKLIST)
            db.session.add(compra)
            self.compras[linha.compra_id] = compra
        compra.programa = destino
        compra.origem = OrigemCompra.CHECKLIST
        compra.servico = linha.servico
        compra.ligada_em = self.momento
        compra.desligada_em = None
        self.cont["compras_juntadas"] += 1
        return destino, compra

    def atualizar_so_visto(self, programa: Programa, linha: LinhaChecklist):
        """Programas só de visto não estão na planilha: o cadastro vem do checklist."""
        self.atualizar_consultor(programa, linha)
        programa.pais = linha.pais
        programa.data_embarque = linha.embarque
        if linha.nome and programa.aluno.nome != linha.nome and not any(
            p.tipo == TipoPrograma.NORMAL for p in programa.aluno.programas
        ):
            programa.aluno.nome = linha.nome

    def atualizar_consultor(self, programa: Programa, linha: LinhaChecklist):
        """O consultor informado pelo checklist prevalece quando estiver preenchido."""
        if not linha.consultor:
            return
        consultor_id, _ = self.resolvedor.resolver(linha.consultor)
        programa.consultor_texto = linha.consultor
        programa.consultor_id = consultor_id
        programa.consultor_do_checklist = True

    # -- tarefa

    def _historico(self, tarefa: Tarefa, campo: str, anterior, novo):
        if tarefa.id is not None:
            db.session.add(HistoricoTarefa(
                tarefa_id=tarefa.id, importacao_id=self.importacao_id, campo=campo,
                valor_anterior=None if anterior is None else str(anterior),
                valor_novo=None if novo is None else str(novo),
            ))

    def gravar_tarefa(self, linha: LinhaChecklist, programa: Programa, compra: Compra, etapa: EtapaModelo):
        tarefa = self.tarefas.get(linha.item)
        if tarefa is None:
            tarefa = Tarefa(
                item_checklist_egali=linha.item, programa=programa, compra=compra, etapa=etapa,
                prazo_egali=linha.prazo, status_egali=linha.status, obs_egali=linha.neg,
                obs_egali_atualizada_em=self.momento if linha.neg else None,
                ultima_importacao_id=self.importacao_id,
            )
            db.session.add(tarefa)
            self.tarefas[linha.item] = tarefa
            self.cont["tarefas_novas"] += 1
            return

        mudou = []
        if tarefa.programa is not programa:
            self._historico(tarefa, "programa", tarefa.programa_id, programa.id)
            tarefa.programa = programa
            mudou.append("programa")
        if tarefa.compra is not compra:
            tarefa.compra = compra
        if tarefa.etapa is not etapa:
            self._historico(tarefa, "procedimento", tarefa.etapa.texto_egali, etapa.texto_egali)
            tarefa.etapa = etapa
            mudou.append("procedimento")
        if tarefa.prazo_egali != linha.prazo:
            self._historico(tarefa, "prazo_egali", tarefa.prazo_egali, linha.prazo)
            tarefa.prazo_egali = linha.prazo
            mudou.append("prazo")
        if tarefa.obs_egali != linha.neg:
            self._historico(tarefa, "obs_egali", tarefa.obs_egali, linha.neg)
            tarefa.obs_egali = linha.neg
            tarefa.obs_egali_atualizada_em = self.momento
            mudou.append("NEG")
        if tarefa.status_egali != linha.status:
            tarefa.status_egali = linha.status
            mudou.append("status na Egali")
        if tarefa.encerrada_egali_em is not None:
            # Tinha sumido do checklist e voltou.
            tarefa.encerrada_egali_em = None
            tarefa.motivo_encerramento = None
            if tarefa.status == StatusTarefa.CONCLUIDA:
                self._historico(tarefa, "status", tarefa.status.value, StatusTarefa.A_FAZER.value)
                tarefa.status = StatusTarefa.A_FAZER
                tarefa.concluida_em = None
            self.cont["tarefas_reabertas"] += 1
        tarefa.ultima_importacao_id = self.importacao_id

        if mudou:
            self.cont["tarefas_atualizadas"] += 1
            self.campos_atualizados.update(mudou)
        else:
            self.cont["tarefas_sem_mudanca"] += 1

    # -- conferências

    def conferir(self, linha: LinhaChecklist, programa: Programa, etapa: EtapaModelo):
        if (
            programa.tipo == TipoPrograma.NORMAL
            and linha.consultor
            and normalizar_texto(linha.consultor) != normalizar_texto(self.consultores_antes.get(programa.id))
        ):
            consultor_anterior = self.consultores_antes.get(programa.id) or "(vazio)"
            self.consultor_divergente[(linha.consultor, consultor_anterior)] += 1
        if etapa.trilha.codigo == "VIP" and programa.pontuacao is not None and programa.pontuacao < PONTUACAO_VIP:
            self.vip_abaixo[id(programa)] = programa

    # -- itens que sumiram

    def encerrar_ausentes(self, no_arquivo: set[str]):
        abertas_antes = self.abertas_antes
        for item, tarefa in self.tarefas.items():
            if item in no_arquivo:
                # Estava no arquivo, mesmo que a linha não tenha sido importada (ex.: divergência):
                # marca como vista, para não aparecer como "fora do período".
                tarefa.ultima_importacao_id = self.importacao_id
                continue
            if tarefa.encerrada_egali_em is not None:
                continue
            if self.periodo and (tarefa.prazo_egali is None or not self.periodo[0] <= tarefa.prazo_egali <= self.periodo[1]):
                self.cont["tarefas_fora_do_periodo"] += 1
                continue
            cancelado = not tarefa.programa.ativo or tarefa.compra is None or tarefa.compra.programa is None
            tarefa.encerrada_egali_em = self.momento
            tarefa.motivo_encerramento = MotivoEncerramento.CANCELADO if cancelado else MotivoEncerramento.FINALIZADO
            if tarefa.aberta:
                self._historico(tarefa, "status", tarefa.status.value, StatusTarefa.CONCLUIDA.value)
                tarefa.status = StatusTarefa.CONCLUIDA
                tarefa.concluida_em = self.momento
            self.cont["tarefas_canceladas" if cancelado else "tarefas_finalizadas"] += 1
            self.detalhes["tarefas_encerradas"].append({
                "item": item, "aluno": tarefa.programa.aluno.nome, "etapa": tarefa.etapa.texto_egali,
                "motivo": tarefa.motivo_encerramento.value,
            })

        encerradas = self.cont["tarefas_finalizadas"] + self.cont["tarefas_canceladas"]
        if abertas_antes and encerradas >= LIMITE_ENCERRAMENTO_MINIMO and encerradas / abertas_antes > LIMITE_ENCERRAMENTO_FRACAO:
            self.coletor.aviso(
                TipoOcorrencia.CANCELAMENTO_EM_MASSA,
                f"Atenção: {encerradas} de {abertas_antes} tarefas ({encerradas / abertas_antes:.0%}) seriam encerradas "
                "porque não estão no arquivo. Confira se é a exportação certa e se o período está correto.",
            )

    # -- ocorrências agrupadas

    def registrar_ocorrencias(self):
        for (tipo, compra_id), d in self.sem_programa.items():
            if tipo == TipoOcorrencia.ALUNO_COM_VARIOS_PROGRAMAS:
                mensagem = (
                    f"Compra {compra_id} ({d['servico']}) de {d['aluno']}: o aluno tem mais de um programa na planilha. "
                    f"Escolha à mão a qual programa ela pertence. {d['itens']} item(ns) não importado(s)."
                )
            else:
                mensagem = (
                    f"Compra {compra_id} ({d['servico']}) de {d['aluno']} (ID {d['aluno_id']}) não está em nenhum "
                    f"programa da planilha: {d['motivo']}. {d['itens']} item(ns) não importado(s). "
                    "Atualize a planilha e importe de novo (primeiro a planilha, depois o checklist)."
                )
            self.coletor.erro(tipo, mensagem, d["linha"], compra_id)
            self.detalhes["itens_sem_programa"].append(d)
        for servico, itens in self.servico_pendente.items():
            self.coletor.erro(
                TipoOcorrencia.SERVICO_NAO_CLASSIFICADO,
                f"Serviço \"{servico}\" sem classificação (curso, visto, avulso ou ignorado). {itens} item(ns) de compras "
                "fora da planilha não foram importados. Classifique o serviço e importe de novo.",
                chave=servico,
            )
        for (csv, planilha), itens in self.consultor_divergente.items():
            self.coletor.aviso(
                TipoOcorrencia.CONSULTOR_DIVERGENTE,
                f"O checklist mostra \"{csv}\" em {itens} item(ns) de programas em que a planilha diz \"{planilha}\". "
                "O consultor informado pelo checklist foi preservado.",
                chave=csv,
            )
        for programa in self.vip_abaixo.values():
            self.coletor.aviso(
                TipoOcorrencia.VIP_ABAIXO_DA_PONTUACAO,
                f"{programa.aluno.nome} (programa {programa.programa_id_egali}) tem etapa VIP, mas a pontuação é "
                f"{programa.pontuacao} (VIP é a partir de {PONTUACAO_VIP}). Conferir e corrigir.",
                chave=programa.programa_id_egali,
            )


def _sincronizar(linhas, coletor, importacao_id, periodo_inicio=None, periodo_fim=None) -> dict:
    s = _Sincronizacao(coletor, importacao_id, periodo_inicio, periodo_fim)
    for linha in linhas:
        etapa = s.etapa(linha)
        if etapa is None:
            continue
        resultado = s.programa_e_compra(linha)
        if resultado is None:
            continue
        programa, compra = resultado
        s.conferir(linha, programa, etapa)
        s.atualizar_consultor(programa, linha)
        if programa.tipo == TipoPrograma.SO_VISTO:
            s.atualizar_so_visto(programa, linha)
        s.gravar_tarefa(linha, programa, compra, etapa)

    # Item que está no arquivo mas não pôde ser importado (ex.: compra órfã) não é encerrado.
    s.encerrar_ausentes({linha.item for linha in linhas})
    s.registrar_ocorrencias()

    # Tags de cada aluno neste arquivo (a tag "summer" marca o público teen).
    tags_por_aluno: dict[str, set[str]] = defaultdict(set)
    for linha in linhas:
        tags_por_aluno[linha.aluno_id].update(t.strip() for t in (linha.tags or "").split(",") if t.strip())
    for aluno_id, tags in tags_por_aluno.items():
        aluno = s.alunos.get(aluno_id)
        if aluno is not None:
            aluno.tags_egali = ", ".join(sorted(tags))[:500] or None
    db.session.flush()
    publico_teen.recalcular()
    db.session.flush()
    detalhes = dict(s.detalhes)
    detalhes["campos_atualizados"] = dict(s.campos_atualizados)
    return {"linhas_importadas": len(linhas), **s.cont, "detalhes": detalhes}


# ---------------------------------------------------------------- encerramento à mão


def ultima_importacao_confirmada() -> Importacao | None:
    return db.session.execute(
        db.select(Importacao)
        .filter_by(tipo=TipoImportacao.CHECKLIST, situacao=SituacaoImportacao.CONFIRMADA)
        .order_by(Importacao.concluida_em.desc(), Importacao.id.desc())
    ).scalars().first()


def tarefas_fora_do_periodo(importacao: Importacao) -> list[Tarefa]:
    """Tarefas que não estavam no arquivo desta importação e não foram encerradas
    porque o prazo ficou fora do período da exportação.

    A importação confirmada grava o próprio id em toda tarefa que estava no
    arquivo; quem ficou com um id mais antigo (ou nenhum) não estava lá."""
    return db.session.execute(
        db.select(Tarefa)
        .join(Tarefa.programa).join(Programa.aluno)
        .where(
            Tarefa.encerrada_egali_em.is_(None),
            db.or_(Tarefa.ultima_importacao_id.is_(None), Tarefa.ultima_importacao_id < importacao.id),
        )
        .order_by(Tarefa.prazo_egali, Aluno.nome)
    ).scalars().all()


def encerrar_a_mao(importacao: Importacao, tarefa_ids: set[int], usuario) -> int:
    """Encerra, como se tivessem saído do checklist, as tarefas escolhidas entre
    as que ficaram fora do período. Só na importação de checklist mais recente."""
    if importacao.tipo != TipoImportacao.CHECKLIST or importacao.situacao != SituacaoImportacao.CONFIRMADA:
        raise ErroImportacao("Só dá para encerrar tarefas de uma importação de checklist gravada.")
    ultima = ultima_importacao_confirmada()
    if ultima is None or ultima.id != importacao.id:
        raise ErroImportacao(
            f"Use a importação de checklist mais recente (nº {ultima.id if ultima else '?'}): "
            "ela é que diz o que ainda está pendente na Egali."
        )
    momento = agora()
    encerradas = 0
    for tarefa in tarefas_fora_do_periodo(importacao):
        if tarefa.id not in tarefa_ids:
            continue
        cancelado = not tarefa.programa.ativo or tarefa.compra is None or tarefa.compra.programa is None
        tarefa.encerrada_egali_em = momento
        tarefa.motivo_encerramento = MotivoEncerramento.CANCELADO if cancelado else MotivoEncerramento.FINALIZADO
        db.session.add(HistoricoTarefa(
            tarefa_id=tarefa.id, usuario_id=usuario.id, importacao_id=importacao.id, campo="encerramento",
            valor_novo=f"encerrada à mão: não estava no checklist da importação nº {importacao.id} (prazo fora do período)",
        ))
        if tarefa.aberta:
            db.session.add(HistoricoTarefa(
                tarefa_id=tarefa.id, usuario_id=usuario.id, importacao_id=importacao.id, campo="status",
                valor_anterior=tarefa.status.value, valor_novo=StatusTarefa.CONCLUIDA.value,
            ))
            tarefa.status = StatusTarefa.CONCLUIDA
            tarefa.concluida_em = momento
        encerradas += 1
    db.session.commit()
    return encerradas


# ---------------------------------------------------------------- fluxo prévia -> confirmação


def _processar(linhas_brutas, coletor, importacao_id, parametros) -> dict:
    return _sincronizar(
        interpretar(linhas_brutas, coletor), coletor, importacao_id,
        parametros.get("periodo_inicio"), parametros.get("periodo_fim"),
    )


def criar_previa(linhas_brutas, periodo_inicio=None, periodo_fim=None, periodo_completo=False,
                 arquivo_nome=None, arquivo_hash=None, usuario_id=None) -> Importacao:
    """Sem período informado, usa o menor e o maior prazo do arquivo.
    periodo_completo=True: exportação sem filtro, todo item ausente é encerrado."""
    linhas_brutas = comum.so_colunas(linhas_brutas, COLUNAS_USADAS)
    if periodo_completo:
        periodo_inicio = periodo_fim = None
    elif periodo_inicio is None and periodo_fim is None:
        periodo_inicio, periodo_fim = periodo_do_arquivo(linhas_brutas)
    if (periodo_inicio is None) != (periodo_fim is None):
        raise ErroImportacao("Informe o início e o fim do período da exportação.")
    if periodo_inicio and periodo_inicio > periodo_fim:
        raise ErroImportacao("O início do período é depois do fim.")
    ultima_base = _conferir_planilha_importada()
    importacao = comum.criar_previa(
        TipoImportacao.CHECKLIST, linhas_brutas, _processar,
        parametros={"periodo_inicio": periodo_inicio, "periodo_fim": periodo_fim},
        arquivo_nome=arquivo_nome, arquivo_hash=arquivo_hash, usuario_id=usuario_id,
    )
    if ultima_base is not None and ultima_base.concluida_em is not None:
        dias = (agora() - hora_local(ultima_base.concluida_em)).days
        if dias > DIAS_PLANILHA_ANTIGA:
            importacao.ocorrencias.append(OcorrenciaImportacao(
                gravidade=Gravidade.AVISO, tipo=TipoOcorrencia.LINHA_INVALIDA,
                mensagem=f"A última planilha de alunos foi importada há {dias} dias "
                         f"({hora_local(ultima_base.concluida_em):%d/%m/%Y}). Importe a desta semana antes do checklist: "
                         "senão vendas novas aparecem como \"programa faltando\" e trocas de consultor como divergência.",
            ))
            importacao.resumo = {**importacao.resumo, "avisos": importacao.resumo["avisos"] + 1}
            db.session.commit()
    return importacao


DIAS_PLANILHA_ANTIGA = 7


def _conferir_planilha_importada() -> Importacao | None:
    """Sem a planilha, nenhum programa existe e todo visto viraria "só de visto"."""
    tem_programa = db.session.execute(
        db.select(Programa.id).filter_by(tipo=TipoPrograma.NORMAL).limit(1)
    ).first()
    if tem_programa is None:
        raise ErroImportacao(
            "Importe primeiro a planilha de alunos (base semanal) e depois o checklist. "
            "Sem a planilha, o sistema não sabe a que programa cada compra pertence."
        )
    return db.session.execute(
        db.select(Importacao)
        .filter_by(tipo=TipoImportacao.BASE_ALUNOS, situacao=SituacaoImportacao.CONFIRMADA)
        .order_by(Importacao.concluida_em.desc())
    ).scalars().first()


def confirmar(importacao: Importacao) -> Importacao:
    parametros = {"periodo_inicio": importacao.periodo_inicio, "periodo_fim": importacao.periodo_fim}
    return comum.confirmar(importacao, TipoImportacao.CHECKLIST, _processar, CONTAGENS, parametros)


descartar = comum.descartar


def importar_arquivo(caminho: str, usuario_id: int | None = None, **periodo) -> Importacao:
    from app.importacao.leitor_csv import ler_csv

    return criar_previa(
        ler_csv(caminho), arquivo_nome=os.path.basename(caminho), arquivo_hash=comum.hash_arquivo(caminho),
        usuario_id=usuario_id, **periodo,
    )
