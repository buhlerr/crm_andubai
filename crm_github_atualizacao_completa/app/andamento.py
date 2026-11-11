"""Andamento do programa até o embarque (porcentagem de procedimentos finalizados).

O sistema só conhece os itens que estavam em aberto nos CSVs importados, e a Egali
cria os procedimentos aos poucos, conforme o processo anda. Por isso a conta é uma
estimativa que usa o catálogo como roteiro:

- Trilhas do programa: a Geral (menos nos programas só de visto) e toda trilha em que
  o programa tem pelo menos uma tarefa.
- A Geral termina no "contato de relacionamento pré-embarque", o último procedimento
  antes do embarque. O que vem depois (pós-embarque) fica fora.
- Procedimento com tarefa aberta: em aberto. Com tarefa concluída ou "não se aplica": finalizado.
- Procedimento sem tarefa: se vem antes do primeiro procedimento em aberto da trilha, já
  passou (finalizado na Egali antes de chegar aqui; marcado como estimado). Se vem
  depois, ainda não foi criado pela Egali: fica pendente como informação (fora do percentual).
- Trilha sem nada em aberto: finalizado até o último procedimento concluído; o resto, pendente.
  Se o aluno já embarcou, o que não está em aberto conta como finalizado.
- Procedimentos que só valem para parte dos alunos (SO_PARA_ALGUNS: CAQ só para visto
  Canadá - Quebec, Canada Leap só para quem comprou, teste de nivelamento só quando a Egali
  cria) ficam fora de quem não se encaixa.
"""

import enum
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from app.extensions import db
from app.models import EtapaModelo, Programa, StatusTarefa, Tarefa, TipoPrograma, Trilha
from app.texto import normalizar_texto


def _simples(texto: str | None) -> str:
    """Minúsculas e sem acentos, para achar trechos do nome ("pré-embarque" = "pre-embarque")."""
    decomposto = unicodedata.normalize("NFD", normalizar_texto(texto))
    return "".join(c for c in decomposto if not unicodedata.combining(c))

GERAL = "GERAL"
ULTIMO_ANTES_DO_EMBARQUE = "contato de relacionamento pre"  # "Realizar contato de relacionamento pré - embarque"
DEPOIS_DO_EMBARQUE = "pos embarque"

# Procedimentos que só existem para parte dos alunos (trecho do nome da etapa -> quando vale).
# Sem isso, um procedimento que não se aplica contaria como "finalizado" ou "pendente".
def _comprou(programa: Programa, servico: str) -> bool:
    """O serviço está na planilha (servico_name) ou em alguma compra do checklist?"""
    textos = [programa.servicos_egali] + [c.servico for c in programa.compras]
    return any(servico in _simples(t) for t in textos if t)


SO_PARA_ALGUNS = {
    "aplicacao do caq": lambda p: "quebec" in _simples(p.visto_normalizado),  # só visto Canadá - Quebec
    "canada leap": lambda p: _comprou(p, "canada leap"),  # só quem comprou Canada Leap
    # Só algumas escolas pedem, e não há lista delas: entra só quando a Egali cria o procedimento para o aluno.
    "teste de nivelamento": lambda p: False,
}


def _vale_para(etapa: EtapaModelo, programa: Programa) -> bool:
    nome = _simples(etapa.nome)
    return all(regra(programa) for trecho, regra in SO_PARA_ALGUNS.items() if trecho in nome)


class Situacao(enum.StrEnum):
    FINALIZADO = "finalizado"
    FINALIZADO_ESTIMADO = "finalizado_estimado"  # não passou por este sistema, mas vem antes do que está em aberto
    NAO_SE_APLICA = "nao_se_aplica"
    EM_ABERTO = "em_aberto"
    PENDENTE = "pendente"  # ainda não criado pela Egali


FEITOS = {Situacao.FINALIZADO, Situacao.FINALIZADO_ESTIMADO, Situacao.NAO_SE_APLICA}
ROTULOS = {
    Situacao.FINALIZADO: "Finalizado",
    Situacao.FINALIZADO_ESTIMADO: "Finalizado (antes de entrar no sistema)",
    Situacao.NAO_SE_APLICA: "Não se aplica",
    Situacao.EM_ABERTO: "Em aberto",
    Situacao.PENDENTE: "Ainda não criado pela Egali",
}


@dataclass
class Passo:
    etapa: EtapaModelo
    situacao: Situacao
    tarefa: Tarefa | None = None

    @property
    def feito(self) -> bool:
        return self.situacao in FEITOS


@dataclass
class Andamento:
    passos: list[Passo] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(p.situacao != Situacao.PENDENTE for p in self.passos)

    @property
    def feitos(self) -> int:
        return sum(p.feito for p in self.passos)

    @property
    def porcentagem(self) -> int:
        return round(100 * self.feitos / self.total) if self.total else 0

    @property
    def estimado(self) -> bool:
        return any(p.situacao == Situacao.FINALIZADO_ESTIMADO for p in self.passos)


def _situacao_da_tarefa(tarefas: list[Tarefa]) -> tuple[Situacao, Tarefa]:
    abertas = [t for t in tarefas if t.aberta]
    if abertas:
        return Situacao.EM_ABERTO, abertas[0]
    concluidas = [t for t in tarefas if t.status == StatusTarefa.CONCLUIDA]
    if concluidas:
        return Situacao.FINALIZADO, concluidas[0]
    return Situacao.NAO_SE_APLICA, tarefas[0]


def _tem_etapa_especifica(trilha: Trilha, programa: Programa) -> bool:
    """A trilha tem um procedimento de SO_PARA_ALGUNS que vale para este aluno (ex.: CAQ para visto Quebec)?"""
    return any(trecho in _simples(e.nome) and regra(programa)
               for e in trilha.etapas if e.ativa for trecho, regra in SO_PARA_ALGUNS.items())


def calcular(programa: Programa, hoje: date | None = None) -> Andamento:
    hoje = hoje or date.today()
    ja_embarcou = programa.data_embarque is not None and programa.data_embarque < hoje
    tarefas_por_etapa: dict[int, list[Tarefa]] = {}
    for t in programa.tarefas:
        tarefas_por_etapa.setdefault(t.etapa_id, []).append(t)
    trilhas_com_tarefa = {t.etapa.trilha_id for t in programa.tarefas}

    trilhas = db.session.execute(db.select(Trilha).order_by(Trilha.ordem)).scalars().all()
    andamento = Andamento()
    for trilha in trilhas:
        geral = trilha.codigo == GERAL and programa.tipo != TipoPrograma.SO_VISTO
        if trilha.id not in trilhas_com_tarefa and not geral and not _tem_etapa_especifica(trilha, programa):
            continue
        # Etapa com tarefa do programa sempre entra; sem tarefa, só se estiver ativa e valer para este aluno.
        etapas = [e for e in trilha.etapas
                  if e.id in tarefas_por_etapa or (e.ativa and _vale_para(e, programa))]
        etapas = [e for e in etapas if DEPOIS_DO_EMBARQUE not in _simples(e.nome)]
        if trilha.codigo == GERAL:
            fim = next((i for i, e in enumerate(etapas) if ULTIMO_ANTES_DO_EMBARQUE in _simples(e.nome)), None)
            if fim is not None:
                etapas = etapas[:fim + 1]

        conhecidas = {e.id: _situacao_da_tarefa(tarefas_por_etapa[e.id]) for e in etapas if e.id in tarefas_por_etapa}
        posicoes_abertas = [i for i, e in enumerate(etapas) if e.id in conhecidas and conhecidas[e.id][0] == Situacao.EM_ABERTO]
        posicoes_feitas = [i for i, e in enumerate(etapas) if e.id in conhecidas and conhecidas[e.id][0] in FEITOS]
        # Até onde o processo já passou: antes do primeiro em aberto; sem nada aberto, até o último feito
        # (ou tudo, se o aluno já embarcou).
        if posicoes_abertas:
            limite = posicoes_abertas[0]
        elif ja_embarcou:
            limite = len(etapas)
        else:
            limite = posicoes_feitas[-1] + 1 if posicoes_feitas else 0

        for i, etapa in enumerate(etapas):
            if etapa.id in conhecidas:
                situacao, tarefa = conhecidas[etapa.id]
                andamento.passos.append(Passo(etapa, situacao, tarefa))
            elif i < limite:
                andamento.passos.append(Passo(etapa, Situacao.FINALIZADO_ESTIMADO))
            else:
                andamento.passos.append(Passo(etapa, Situacao.PENDENTE))
    return andamento


# ---------------------------------------------------------------- andamento do processo de visto
# O processo de visto termina no procedimento "Documentação OK" (envio para a embaixada/consulado):
# finalizado ele, o andamento é 100%. O que vem depois (biometria, status, cópia do visto) fica fora.
TRILHAS_DE_VISTO = ("VISTOS",)  # Canadá e demais países
# Vistos que ficam fora da tela (decisão da equipe, 04/11/2026): todos os dos EUA e o eTA do Canadá.
PAISES_FORA = {"eua", "estados unidos"}
TIPOS_FORA = {"eta"}
DOCUMENTACAO_OK = "documentacao ok"


@dataclass
class AndamentoVisto:
    programa: Programa
    trilha: Trilha
    passos: list[Passo] = field(default_factory=list)

    @property
    def total(self) -> int:
        # Aqui o fim do processo é conhecido, então o que a Egali ainda não criou também entra no total.
        return len(self.passos)

    @property
    def feitos(self) -> int:
        return sum(p.feito for p in self.passos)

    @property
    def concluido(self) -> bool:
        """O "Documentação OK" (último passo) foi finalizado."""
        return bool(self.passos) and self.passos[-1].feito

    @property
    def porcentagem(self) -> int:
        if self.concluido:
            return 100
        # Sem o Documentação OK finalizado, nunca mostra 100%.
        return min(round(100 * self.feitos / self.total), 99) if self.total else 0

    @property
    def atual(self) -> Passo | None:
        """Procedimento em que o processo está: o primeiro em aberto; sem nenhum, o próximo ainda não criado."""
        if self.concluido:
            return self.passos[-1]
        return (next((p for p in self.passos if p.situacao == Situacao.EM_ABERTO), None)
                or next((p for p in self.passos if p.situacao == Situacao.PENDENTE), None))

    @property
    def neg(self) -> str | None:
        """NEG (observação da Egali) do procedimento atual."""
        passo = self.atual
        if passo and passo.tarefa and passo.tarefa.tem_justificativa:
            return passo.tarefa.obs_egali.strip()
        return None

    @property
    def estimado(self) -> bool:
        return any(p.situacao == Situacao.FINALIZADO_ESTIMADO for p in self.passos)


def visto_considerado(rotulo: str) -> bool:
    """"Visto - Canadá - Estudante" entra; "Visto - EUA - Turista" e "Visto - Canadá - eTA" ficam fora."""
    partes = {parte.strip() for parte in _simples(rotulo).split("-")}
    return not (partes & PAISES_FORA or partes & TIPOS_FORA)


def _trilhas_de_visto_do_programa(programa: Programa, trilhas: dict[str, Trilha]) -> list[Trilha]:
    """Pelo tipo de visto: entra se tiver algum visto considerado (nem EUA, nem eTA Canadá).
    Sem tipo de visto informado, entra se tiver tarefa na trilha de vistos."""
    from app.vistos import tipos_de_visto

    rotulos = tipos_de_visto(programa)
    if rotulos:
        entra = any(visto_considerado(r) for r in rotulos)
    else:
        entra = any(t.etapa.trilha.codigo in TRILHAS_DE_VISTO for t in programa.tarefas)
    return [trilhas[c] for c in TRILHAS_DE_VISTO if entra and c in trilhas]


def calcular_visto(programa: Programa, trilha: Trilha, hoje: date | None = None) -> AndamentoVisto:
    """Andamento do processo de visto do programa em uma trilha de visto, até o "Documentação OK"."""
    hoje = hoje or date.today()
    ja_embarcou = programa.data_embarque is not None and programa.data_embarque < hoje
    tarefas_por_etapa: dict[int, list[Tarefa]] = {}
    for t in programa.tarefas:
        tarefas_por_etapa.setdefault(t.etapa_id, []).append(t)

    etapas = [e for e in trilha.etapas if e.id in tarefas_por_etapa or (e.ativa and _vale_para(e, programa))]
    fim = next((i for i, e in enumerate(etapas) if DOCUMENTACAO_OK in _simples(e.nome)), None)
    if fim is not None:
        etapas = etapas[:fim + 1]

    conhecidas = {e.id: _situacao_da_tarefa(tarefas_por_etapa[e.id]) for e in etapas if e.id in tarefas_por_etapa}
    abertas = [i for i, e in enumerate(etapas) if e.id in conhecidas and conhecidas[e.id][0] == Situacao.EM_ABERTO]
    feitas = [i for i, e in enumerate(etapas) if e.id in conhecidas and conhecidas[e.id][0] in FEITOS]
    if abertas:
        limite = abertas[0]
    elif ja_embarcou:
        limite = len(etapas)
    else:
        limite = feitas[-1] + 1 if feitas else 0

    andamento = AndamentoVisto(programa, trilha)
    for i, etapa in enumerate(etapas):
        if etapa.id in conhecidas:
            situacao, tarefa = conhecidas[etapa.id]
            andamento.passos.append(Passo(etapa, situacao, tarefa))
        elif i < limite:
            andamento.passos.append(Passo(etapa, Situacao.FINALIZADO_ESTIMADO))
        else:
            andamento.passos.append(Passo(etapa, Situacao.PENDENTE))
    return andamento


def andamentos_de_visto(programas: list[Programa], hoje: date | None = None) -> list[AndamentoVisto]:
    """Uma linha por programa com processo de visto considerado."""
    trilhas = {t.codigo: t for t in db.session.execute(
        db.select(Trilha).where(Trilha.codigo.in_(TRILHAS_DE_VISTO))).scalars()}
    linhas = []
    for programa in programas:
        for trilha in _trilhas_de_visto_do_programa(programa, trilhas):
            linhas.append(calcular_visto(programa, trilha, hoje))
    return linhas
