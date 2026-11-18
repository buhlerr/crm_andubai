"""Importação do checklist da Egali (relatório do TM, checklistServicoNew.csv).

É a única importação do sistema: cria e atualiza alunos, programas, compras e tarefas,
e alimenta o painel RSA - Checklist do Suporte (app/importacao/rsa_checklist.py).

Alunos e programas (sem a planilha semanal):
- O aluno vem da coluna ID Aluno; o programa é um por aluno, com todas as compras dele.
  Programas que já existem (da época da planilha) continuam e recebem as compras novas.
- Só compras de visto: programa "só de visto". Chegou uma compra de curso: vira programa normal.
- O cadastro do programa vem do próprio checklist: consultor, embarque, tipo de visto, país,
  cidade, escola, grupo, serviços e tags. VIP: procedimento "SA - VIP - ..." ou tag VIP.

Cada linha é um item do checklist, identificado pela coluna "#".
- Status "Finalizado" (ou Data da Finalização preenchida): a tarefa fica concluída
  ("concluída na Egali"); se não existia, entra já concluída. Não aparece nas filas.
- Status cancelado: a tarefa é encerrada como cancelada.
- Os demais estão em aberto.
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
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from app import publico_teen
from app.extensions import db
from app.importacao import ErroImportacao, comum, rsa_checklist
from app.importacao.comum import Coletor
from app.importacao.consultores import ResolvedorConsultor
from app.importacao.rsa_checklist import codigo_da_trilha
from app.importacao.valores import IdInvalido, normalizar_id_egali, para_data, para_texto
from app.models import (
    Aluno,
    ApelidoEtapa,
    CategoriaServico,
    Compra,
    EtapaModelo,
    HistoricoTarefa,
    Importacao,
    MotivoEncerramento,
    OrigemCompra,
    Programa,
    ServicoEgali,
    SituacaoPrograma,
    SituacaoImportacao,
    StatusTarefa,
    Tarefa,
    TipoImportacao,
    TipoOcorrencia,
    TipoPrograma,
    Trilha,
)
from app.models.base import agora
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
COL_TAGS = "tags"  # usada para marcar o público teen (tag "summer") e o VIP
COL_FINALIZACAO = "data da finalização"
COL_EXECUTOR = "atualizado por:"
COL_TIPO_VISTO = "tipo de visto"
COL_ESCOLA = "escola"
COL_CIDADE = "cidade"
COL_GRUPO = "grupo"
COL_EMPRESA = "empresa"
COLUNAS_OBRIGATORIAS = (COL_ITEM, COL_COMPRA, COL_ALUNO, COL_PROCEDIMENTO, COL_DATA)
COLUNAS_USADAS = frozenset(COLUNAS_OBRIGATORIAS) | {
    COL_NOME, COL_NEG, COL_CONSULTOR, COL_STATUS, COL_SERVICO, COL_PAIS, COL_EMBARQUE, COL_TAGS,
    COL_FINALIZACAO, COL_EXECUTOR, COL_TIPO_VISTO, COL_ESCOLA, COL_CIDADE, COL_GRUPO, COL_EMPRESA,
}
TAG_VIP = "vip"

# Aviso de segurança: encerrar a maior parte das tarefas de uma vez costuma ser arquivo errado.
LIMITE_ENCERRAMENTO_MINIMO = 20
LIMITE_ENCERRAMENTO_FRACAO = 0.5

CONTAGENS = (
    "tarefas_novas", "tarefas_concluidas_novas", "tarefas_atualizadas", "tarefas_sem_mudanca", "tarefas_reabertas",
    "tarefas_finalizadas", "tarefas_canceladas", "tarefas_fora_do_periodo", "itens_cancelados",
    "compras_juntadas", "programas_criados", "programas_so_visto_criados", "programas_viraram_normais",
    "programas_atualizados", "alunos_criados", "itens_ignorados", "itens_sem_programa", "etapas_criadas",
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
    finalizado: bool = False
    cancelado: bool = False
    finalizacao: date | None = None
    tipo_visto: str | None = None
    escola: str | None = None
    cidade: str | None = None
    grupo: str | None = None


# ---------------------------------------------------------------- leitura


def _data_do_tm(texto) -> date | None:
    """"15/10/2026 14:03:22" (Data da Finalização) -> date; vazio ou inválido -> None."""
    texto = para_texto(texto)
    if not texto:
        return None
    try:
        return para_data(texto.split()[0])
    except ValueError:
        return None


def visto_do_checklist(tipo_de_visto: str | None) -> str | None:
    """"EUA (Turista)" -> "Turista - EUA", o formato de Programa.visto_normalizado (app/vistos.py)."""
    texto = para_texto(tipo_de_visto)
    if not texto or normalizar_texto(texto) in ("sem visto vinculado", "sem visto informado"):
        return None
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", texto)
    return f"{m.group(2).strip()} - {m.group(1).strip()}" if m else texto


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
        status = para_texto(v.get(COL_STATUS))
        finalizacao = _data_do_tm(v.get(COL_FINALIZACAO))
        cancelado = "cancel" in normalizar_texto(status)
        resultado.append(LinhaChecklist(
            n, item, compra_id, aluno_id, para_texto(v.get(COL_NOME)), procedimento, prazo, neg,
            status, para_texto(v.get(COL_CONSULTOR)), para_texto(v.get(COL_SERVICO)),
            para_texto(v.get(COL_PAIS)), embarque, para_texto(v.get(COL_TAGS)),
            finalizado=not cancelado and (normalizar_texto(status) == "finalizado" or finalizacao is not None),
            cancelado=cancelado, finalizacao=finalizacao,
            tipo_visto=para_texto(v.get(COL_TIPO_VISTO)), escola=para_texto(v.get(COL_ESCOLA)),
            cidade=para_texto(v.get(COL_CIDADE)), grupo=para_texto(v.get(COL_GRUPO)),
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
        # Programa de cada aluno (um por aluno): o ativo antes do cancelado; entre eles, o normal mais recente;
        # sem normal, o só de visto. Assim uma compra nova não revive um programa cancelado se há um ativo.
        self.programa_do_aluno: dict[str, Programa] = {}
        self.programas_novos: set[int] = set()  # id() dos criados nesta importação (não contam como "atualizados")
        ordem = lambda p: (p.situacao != SituacaoPrograma.CANCELADO, p.tipo == TipoPrograma.NORMAL, p.id)  # noqa: E731
        for p in sorted(programas, key=ordem):
            if p.situacao != SituacaoPrograma.INCORPORADO:
                self.programa_do_aluno[p.aluno.aluno_id_egali] = p
        self.linhas_do_programa: dict[int, list[LinhaChecklist]] = defaultdict(list)
        self.programas_por_chave: dict[int, Programa] = {}
        self.compras = {c.compra_id_egali: c for c in db.session.execute(db.select(Compra)).scalars()}
        self.tarefas = {t.item_checklist_egali: t for t in db.session.execute(db.select(Tarefa)).scalars()}
        self.abertas_antes = sum(1 for t in self.tarefas.values() if t.encerrada_egali_em is None)
        self.resolvedor = ResolvedorConsultor()
        self.consultores_antes = {p.id: p.consultor_texto for p in programas}

        # Problemas agrupados, para não gerar uma ocorrência por linha.
        self.sem_programa: dict[tuple, dict] = {}  # (tipo, compra) -> dados
        self.servico_pendente: Counter = Counter()

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

    def _reativar(self, programa: Programa):
        if programa.situacao == SituacaoPrograma.CANCELADO:
            programa.situacao = SituacaoPrograma.ATIVO  # item em aberto ou finalizado no checklist: o aluno voltou
            programa.reativado_em = self.momento

    def _ajustar_tipo(self, programa: Programa, categoria: CategoriaServico):
        # Mesma regra da criação, para não depender da ordem das linhas: só visto é quem só tem visto.
        if programa.tipo == TipoPrograma.SO_VISTO and categoria not in (CategoriaServico.VISTO, CategoriaServico.IGNORADO):
            programa.tipo = TipoPrograma.NORMAL
            self.cont["programas_viraram_normais"] += 1

    def _programa_do_aluno(self, linha: LinhaChecklist, categoria: CategoriaServico) -> Programa:
        """O programa do aluno (um por aluno). Sem nenhum, cria: só de visto se a compra for de visto."""
        programa = self.programa_do_aluno.get(linha.aluno_id)
        if programa is not None:
            self._reativar(programa)
        if programa is None:
            aluno = self.alunos.get(linha.aluno_id)
            if aluno is None:
                aluno = Aluno(aluno_id_egali=linha.aluno_id, nome=linha.nome or f"Aluno {linha.aluno_id}")
                db.session.add(aluno)
                self.alunos[linha.aluno_id] = aluno
                self.cont["alunos_criados"] += 1
            so_visto = categoria == CategoriaServico.VISTO
            programa = Programa(aluno=aluno, tipo=TipoPrograma.SO_VISTO if so_visto else TipoPrograma.NORMAL)
            db.session.add(programa)
            db.session.flush()
            self.programa_do_aluno[linha.aluno_id] = programa
            self.programas_novos.add(id(programa))
            self.cont["programas_so_visto_criados" if so_visto else "programas_criados"] += 1
            if so_visto:
                self.detalhes["programas_so_visto_criados"].append({"aluno_id": linha.aluno_id, "aluno": aluno.nome})
        self._ajustar_tipo(programa, categoria)
        return programa

    def programa_e_compra(self, linha: LinhaChecklist) -> tuple[Programa, Compra] | None:
        compra = self.compras.get(linha.compra_id)
        servico = self.servico(linha.servico)
        categoria = servico.categoria if servico else CategoriaServico.NAO_CLASSIFICADO
        if compra is not None and compra.programa is not None:
            programa = compra.programa
            if programa.aluno.aluno_id_egali != linha.aluno_id:
                self.coletor.erro(
                    TipoOcorrencia.DIVERGENCIA_ALUNO,
                    f"Item {linha.item}: o ID Aluno do checklist ({linha.aluno_id}) é diferente do aluno do programa "
                    f"{programa.rotulo} ({programa.aluno.aluno_id_egali}). Não foi importado.",
                    linha.linha, linha.item,
                )
                return None
            if compra.servico != linha.servico and linha.servico:
                compra.servico = linha.servico
            self._reativar(programa)  # compra antiga que voltou ao checklist
            self._ajustar_tipo(programa, categoria)
            return programa, compra

        if categoria == CategoriaServico.IGNORADO:
            self.cont["itens_ignorados"] += 1
            return None
        if categoria == CategoriaServico.NAO_CLASSIFICADO:
            self.servico_pendente[linha.servico or "(sem serviço)"] += 1  # importa assim mesmo; só avisa
        destino = self._programa_do_aluno(linha, categoria)
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

    def guardar_para_o_cadastro(self, programa: Programa, linha: LinhaChecklist):
        self.programas_por_chave[id(programa)] = programa
        self.linhas_do_programa[id(programa)].append(linha)

    def atualizar_cadastros(self):
        """O cadastro do programa vem do checklist: o valor que mais aparece nas linhas do aluno.
        Campo vazio no arquivo não apaga o que já estava gravado."""
        def mais_comum(valores):
            valores = [v for v in valores if v]
            return Counter(valores).most_common(1)[0][0] if valores else None

        def em_ordem(valores):
            return list(dict.fromkeys(v for v in valores if v))

        for chave, linhas in self.linhas_do_programa.items():
            programa = self.programas_por_chave[chave]
            antes = (programa.data_embarque, programa.visto_normalizado, programa.pais, programa.cidade, programa.escola,
                     programa.grupo, programa.servicos_egali, programa.vip_egali)
            embarque = mais_comum(l.embarque for l in linhas)
            if embarque:
                programa.data_embarque = embarque
                programa.mes_embarque = embarque.replace(day=1)
            vistos = em_ordem(visto_do_checklist(l.tipo_visto) for l in linhas)
            if vistos:
                programa.visto_normalizado = ",".join(vistos)[:200]
            for campo, valor in (("pais", mais_comum(l.pais for l in linhas)), ("cidade", mais_comum(l.cidade for l in linhas)),
                                 ("escola", mais_comum(l.escola for l in linhas)), ("grupo", mais_comum(l.grupo for l in linhas))):
                if valor:
                    setattr(programa, campo, valor[:300])
            # Junta com o que já estava (ex.: serviços da época da planilha): sem isso, um aluno
            # deixaria de ser teen só porque o serviço teen não teve item neste arquivo.
            servicos = em_ordem([s.strip() for s in (programa.servicos_egali or "").split(",")] + [l.servico for l in linhas])
            if servicos:
                programa.servicos_egali = ", ".join(servicos)
            tags = {normalizar_texto(t) for l in linhas for t in (l.tags or "").split(",")}
            # Como os serviços: um arquivo por período sem a linha VIP do aluno não tira o VIP dele.
            programa.vip_egali = (bool(programa.vip_egali) or TAG_VIP in tags
                                  or any(codigo_da_trilha(l.procedimento) == "VIP" for l in linhas))
            nome = mais_comum(l.nome for l in linhas)
            if nome and programa.aluno.nome != nome:
                programa.aluno.nome = nome
            if chave not in self.programas_novos and antes != (programa.data_embarque, programa.visto_normalizado, programa.pais,
                                                     programa.cidade, programa.escola, programa.grupo,
                                                     programa.servicos_egali, programa.vip_egali):
                self.cont["programas_atualizados"] += 1

    def atualizar_consultor(self, programa: Programa, linha: LinhaChecklist):
        """O consultor vem do checklist (o da última linha do aluno, quando preenchido)."""
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

    def _concluida_em(self, linha: LinhaChecklist) -> datetime:
        if linha.finalizacao:
            return datetime.combine(linha.finalizacao, time(12), tzinfo=timezone.utc)
        return self.momento

    def gravar_tarefa(self, linha: LinhaChecklist, programa: Programa, compra: Compra, etapa: EtapaModelo):
        tarefa = self.tarefas.get(linha.item)
        if tarefa is None:
            tarefa = Tarefa(
                item_checklist_egali=linha.item, programa=programa, compra=compra, etapa=etapa,
                prazo_egali=linha.prazo, status_egali=linha.status, obs_egali=linha.neg,
                obs_egali_atualizada_em=self.momento if linha.neg else None,
                ultima_importacao_id=self.importacao_id,
            )
            if linha.finalizado:  # já finalizado na Egali: entra concluído, fora das filas
                tarefa.status = StatusTarefa.CONCLUIDA
                tarefa.concluida_em = self._concluida_em(linha)
                tarefa.encerrada_egali_em = self.momento
                tarefa.motivo_encerramento = MotivoEncerramento.FINALIZADO
            db.session.add(tarefa)
            self.tarefas[linha.item] = tarefa
            self.cont["tarefas_concluidas_novas" if linha.finalizado else "tarefas_novas"] += 1
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
        if linha.finalizado:
            if tarefa.encerrada_egali_em is None:  # estava aberta aqui e foi finalizada na Egali
                tarefa.encerrada_egali_em = self.momento
                tarefa.motivo_encerramento = MotivoEncerramento.FINALIZADO
                if tarefa.aberta:
                    self._historico(tarefa, "status", tarefa.status.value, StatusTarefa.CONCLUIDA.value)
                    tarefa.status = StatusTarefa.CONCLUIDA
                    tarefa.concluida_em = self._concluida_em(linha)
                self.cont["tarefas_finalizadas"] += 1
                self.detalhes["tarefas_encerradas"].append({
                    "item": linha.item, "aluno": programa.aluno.nome, "etapa": etapa.texto_egali, "motivo": "finalizado",
                })
            elif tarefa.motivo_encerramento != MotivoEncerramento.FINALIZADO:
                # Já encerrada (ex.: cancelada antes) e agora finalizada na Egali: vale o motivo de agora.
                self._historico(tarefa, "motivo_encerramento", tarefa.motivo_encerramento, MotivoEncerramento.FINALIZADO.value)
                tarefa.motivo_encerramento = MotivoEncerramento.FINALIZADO
        elif tarefa.encerrada_egali_em is not None:
            # Tinha sumido do checklist (ou estava finalizada) e voltou em aberto.
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

    # -- itens que sumiram

    def encerrar_ausentes(self, no_arquivo: set[str], cancelados: set[str] = frozenset()):
        abertas_antes = self.abertas_antes
        # Só as encerradas porque sumiram do arquivo; as finalizadas ou canceladas pelo próprio arquivo não contam.
        sumiram = 0
        for item, tarefa in self.tarefas.items():
            if item in cancelados and item not in no_arquivo:
                tarefa.ultima_importacao_id = self.importacao_id
                if tarefa.encerrada_egali_em is None:  # cancelado na Egali
                    tarefa.encerrada_egali_em = self.momento
                    tarefa.motivo_encerramento = MotivoEncerramento.CANCELADO
                    if tarefa.aberta:
                        self._historico(tarefa, "status", tarefa.status.value, StatusTarefa.CONCLUIDA.value)
                        tarefa.status = StatusTarefa.CONCLUIDA
                        tarefa.concluida_em = self.momento
                    self.cont["tarefas_canceladas"] += 1
                    self.detalhes["tarefas_encerradas"].append({
                        "item": item, "aluno": tarefa.programa.aluno.nome, "etapa": tarefa.etapa.texto_egali,
                        "motivo": MotivoEncerramento.CANCELADO.value,
                    })
                elif tarefa.motivo_encerramento != MotivoEncerramento.CANCELADO:
                    # Já encerrada (ex.: sumiu de um arquivo parcial e foi dada como finalizada) e agora
                    # o arquivo diz que foi cancelada na Egali: vale o cancelamento.
                    self._historico(tarefa, "motivo_encerramento", tarefa.motivo_encerramento,
                                    MotivoEncerramento.CANCELADO.value)
                    tarefa.motivo_encerramento = MotivoEncerramento.CANCELADO
                    self.cont["tarefas_canceladas"] += 1
                continue
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
            sumiram += 1
            self.detalhes["tarefas_encerradas"].append({
                "item": item, "aluno": tarefa.programa.aluno.nome, "etapa": tarefa.etapa.texto_egali,
                "motivo": tarefa.motivo_encerramento.value,
            })

        if abertas_antes and sumiram >= LIMITE_ENCERRAMENTO_MINIMO and sumiram / abertas_antes > LIMITE_ENCERRAMENTO_FRACAO:
            self.coletor.aviso(
                TipoOcorrencia.CANCELAMENTO_EM_MASSA,
                f"Atenção: {sumiram} de {abertas_antes} tarefas ({sumiram / abertas_antes:.0%}) seriam encerradas "
                "porque não estão no arquivo. Confira se é a exportação certa e se o período está correto.",
            )

    # -- ocorrências agrupadas

    def registrar_ocorrencias(self):
        for (tipo, compra_id), d in self.sem_programa.items():
            if tipo == TipoOcorrencia.ALUNO_COM_VARIOS_PROGRAMAS:
                mensagem = (
                    f"Compra {compra_id} ({d['servico']}) de {d['aluno']}: o aluno tem mais de um programa no sistema. "
                    f"Escolha à mão a qual programa ela pertence. {d['itens']} item(ns) não importado(s)."
                )
            else:
                mensagem = (
                    f"Compra {compra_id} ({d['servico']}) de {d['aluno']} (ID {d['aluno_id']}) não está em nenhum "
                    f"programa: {d['motivo']}. {d['itens']} item(ns) não importado(s). "
                    "Confira o cadastro do aluno na Egali e importe o checklist de novo."
                )
            self.coletor.erro(tipo, mensagem, d["linha"], compra_id)
            self.detalhes["itens_sem_programa"].append(d)
        for servico, itens in self.servico_pendente.items():
            self.coletor.aviso(
                TipoOcorrencia.SERVICO_NAO_CLASSIFICADO,
                f"Serviço \"{servico}\" sem classificação (curso, visto, avulso ou ignorado). {itens} item(ns) entraram no "
                "programa do aluno assim mesmo. Classifique o serviço em Cadastros → Serviços: é isso que diz se o aluno "
                "é \"só de visto\" e o que deve ser ignorado.",
                chave=servico,
            )


def _sincronizar(linhas, coletor, importacao_id, periodo_inicio=None, periodo_fim=None) -> dict:
    s = _Sincronizacao(coletor, importacao_id, periodo_inicio, periodo_fim)
    cancelados = {linha.item for linha in linhas if linha.cancelado}
    s.cont["itens_cancelados"] = len(cancelados)
    for linha in linhas:
        if linha.cancelado:
            continue
        etapa = s.etapa(linha)
        if etapa is None:
            continue
        resultado = s.programa_e_compra(linha)
        if resultado is None:
            continue
        programa, compra = resultado
        s.atualizar_consultor(programa, linha)
        s.guardar_para_o_cadastro(programa, linha)
        s.gravar_tarefa(linha, programa, compra, etapa)
    s.atualizar_cadastros()

    # Item que está no arquivo mas não pôde ser importado (ex.: compra órfã) não é encerrado.
    s.encerrar_ausentes({linha.item for linha in linhas if not linha.cancelado}, cancelados)
    s.registrar_ocorrencias()

    # Tags de cada aluno neste arquivo (a tag "summer" marca o público teen).
    tags_por_aluno: dict[str, set[str]] = defaultdict(set)
    for linha in linhas:
        tags_por_aluno[linha.aluno_id].update(t.strip() for t in (linha.tags or "").split(",") if t.strip())
    for aluno_id, tags in tags_por_aluno.items():
        aluno = s.alunos.get(aluno_id)
        # Campo vazio no arquivo (ou coluna Tags ausente) não apaga o que já estava: sem isso, o aluno perderia a tag summer.
        if aluno is not None and tags:
            aluno.tags_egali = ", ".join(sorted(tags))[:500]
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


def _cobre(novo: dict, atual: dict) -> bool:
    """A base nova vai pelo menos do início ao fim da que está no painel?"""
    def data(texto):
        try:
            return datetime.strptime(texto, "%d/%m/%Y").date()
        except (TypeError, ValueError):
            return None

    ini_atual, fim_atual = data(atual.get("ini")), data(atual.get("fim"))
    if ini_atual is None or fim_atual is None:
        return True
    ini_novo, fim_novo = data(novo.get("ini")), data(novo.get("fim"))
    return ini_novo is not None and fim_novo is not None and ini_novo <= ini_atual and fim_novo >= fim_atual


def _processar(linhas_brutas, coletor, importacao_id, parametros) -> dict:
    resumo = _sincronizar(
        interpretar(linhas_brutas, coletor), coletor, importacao_id,
        parametros.get("periodo_inicio"), parametros.get("periodo_fim"),
    )
    # Painel RSA: mesma base, montada com as regras do app (público teen fora, atraso por dia...).
    try:
        base, resumo_rsa = rsa_checklist.montar_base(linhas_brutas, Coletor())
    except ErroImportacao:
        # Exportação sem Status/Data da Finalização (só os em aberto): as tarefas entram, o RSA fica como estava.
        resumo["rsa_nao_atualizado"] = 1
        return resumo
    # Arquivo de um período menor que o do painel (ex.: só outubro) não substitui a base do ano:
    # as tarefas entram, o painel fica como estava. Exportação completa (sem período) sempre substitui.
    atual = rsa_checklist.base_guardada()
    if atual and parametros.get("periodo_inicio") is not None and not _cobre(base["meta"], atual.get("meta", {})):
        resumo["rsa_periodo_menor"] = 1
        return resumo
    resumo.update(rsa_procedimentos=resumo_rsa["linhas_na_base"], rsa_em_aberto=resumo_rsa["em_aberto"],
                  rsa_alunos_teen=resumo_rsa["alunos_teen_excluidos"])
    if importacao_id is not None:  # confirmação: o arquivo só é gravado depois do commit (ver confirmar)
        parametros["_base_rsa"] = base
    return resumo


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
    importacao = comum.criar_previa(
        TipoImportacao.CHECKLIST, linhas_brutas, _processar,
        parametros={"periodo_inicio": periodo_inicio, "periodo_fim": periodo_fim},
        arquivo_nome=arquivo_nome, arquivo_hash=arquivo_hash, usuario_id=usuario_id,
    )
    return importacao


def confirmar(importacao: Importacao) -> Importacao:
    parametros = {"periodo_inicio": importacao.periodo_inicio, "periodo_fim": importacao.periodo_fim}
    importacao = comum.confirmar(importacao, TipoImportacao.CHECKLIST, _processar, CONTAGENS, parametros)
    # Base do painel RSA só depois do commit: se a confirmação falhar, o painel fica como estava.
    if "_base_rsa" in parametros:
        rsa_checklist.guardar_base(parametros["_base_rsa"], importacao.id, importacao.arquivo_nome)
    return importacao


descartar = comum.descartar


def importar_arquivo(caminho: str, usuario_id: int | None = None, **periodo) -> Importacao:
    from app.importacao.leitor_csv import ler_csv

    return criar_previa(
        ler_csv(caminho), arquivo_nome=os.path.basename(caminho), arquivo_hash=comum.hash_arquivo(caminho),
        usuario_id=usuario_id, **periodo,
    )
