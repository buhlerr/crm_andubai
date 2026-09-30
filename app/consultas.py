"""Consultas das filas de trabalho.

Regras:
- Na fila = tarefa aberta (A fazer, Em andamento, Aguardando aluno) de programa ativo.
- Responsável = o trocado à mão, senão o consultor do programa.
- Data do procedimento (Egali) = fixa, do CSV. Atrasada = essa data antes de hoje. Com justificativa = tem NEG.
- Data prevista = a planejada pelo consultor, senão a do procedimento. Ordena as filas, filtra por data
  e posiciona no calendário. Não muda o atraso.
"""

import enum
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import contains_eager, joinedload, selectinload

from app.extensions import db
from app.models import (
    STATUS_ABERTOS,
    Aluno,
    Anotacao,
    EtapaModelo,
    Programa,
    SituacaoPrograma,
    StatusTarefa,
    Tarefa,
    Trilha,
    Usuario,
)

RESPONSAVEL = func.coalesce(Tarefa.responsavel_manual_id, Programa.consultor_id)
PRAZO_EGALI = Tarefa.prazo_egali
DATA_PREVISTA = func.coalesce(Tarefa.data_planejada, Tarefa.prazo_egali)
TEM_NEG = and_(Tarefa.obs_egali.is_not(None), func.trim(Tarefa.obs_egali) != "")

NINGUEM = "nenhum"  # valor de filtro para "sem responsável" / "sem consultor"


class FiltroAtraso(enum.StrEnum):
    TODAS = ""
    ATRASADAS = "atrasadas"
    SEM_JUSTIFICATIVA = "sem_justificativa"
    COM_JUSTIFICATIVA = "com_justificativa"
    NO_PRAZO = "no_prazo"


class FiltroPublico(enum.StrEnum):
    TODOS = ""
    SUPORTE = "suporte"  # sem o público teen
    TEEN = "teen"


ROTULOS_PUBLICO = {
    FiltroPublico.TODOS: "Todos",
    FiltroPublico.SUPORTE: "Suporte (sem teen)",
    FiltroPublico.TEEN: "Só teen",
}

ROTULOS_ATRASO = {
    FiltroAtraso.TODAS: "Todas",
    FiltroAtraso.ATRASADAS: "Atrasadas",
    FiltroAtraso.SEM_JUSTIFICATIVA: "Atrasadas sem justificativa (sem NEG)",
    FiltroAtraso.COM_JUSTIFICATIVA: "Atrasadas com justificativa (com NEG)",
    FiltroAtraso.NO_PRAZO: "No prazo",
}


@dataclass
class Filtros:
    status: StatusTarefa | None = None  # None = todas as abertas
    responsavel: int | str | None = None  # id, NINGUEM ou None (todos)
    consultor: int | str | None = None
    trilha: str | None = None
    etapa: int | None = None  # procedimento (EtapaModelo.id)
    atraso: FiltroAtraso = FiltroAtraso.TODAS
    busca: str = ""
    prazo_de: date | None = None
    prazo_ate: date | None = None
    publico: FiltroPublico = FiltroPublico.TODOS
    hoje: date = field(default_factory=date.today)


def _base():
    return (
        select(Tarefa)
        .join(Tarefa.programa)
        .join(Programa.aluno)
        .join(Tarefa.etapa)
        .join(EtapaModelo.trilha)
        .where(Programa.situacao == SituacaoPrograma.ATIVO)
    )


def _filtrar(consulta, f: Filtros, com_status=True):
    if com_status:
        consulta = consulta.where(Tarefa.status == f.status) if f.status else consulta.where(Tarefa.status.in_(STATUS_ABERTOS))
    else:
        consulta = consulta.where(Tarefa.status.in_(STATUS_ABERTOS))

    if f.responsavel == NINGUEM:
        consulta = consulta.where(RESPONSAVEL.is_(None))
    elif f.responsavel:
        consulta = consulta.where(RESPONSAVEL == f.responsavel)
    if f.consultor == NINGUEM:
        consulta = consulta.where(Programa.consultor_id.is_(None))
    elif f.consultor:
        consulta = consulta.where(Programa.consultor_id == f.consultor)
    if f.trilha:
        consulta = consulta.where(Trilha.codigo == f.trilha)
    if f.etapa:
        consulta = consulta.where(EtapaModelo.id == f.etapa)

    atrasada = PRAZO_EGALI < f.hoje
    if f.atraso == FiltroAtraso.ATRASADAS:
        consulta = consulta.where(atrasada)
    elif f.atraso == FiltroAtraso.SEM_JUSTIFICATIVA:
        consulta = consulta.where(atrasada, ~TEM_NEG)
    elif f.atraso == FiltroAtraso.COM_JUSTIFICATIVA:
        consulta = consulta.where(atrasada, TEM_NEG)
    elif f.atraso == FiltroAtraso.NO_PRAZO:
        consulta = consulta.where(or_(PRAZO_EGALI.is_(None), PRAZO_EGALI >= f.hoje))
    if f.publico == FiltroPublico.SUPORTE:
        consulta = consulta.where(Aluno.teen.is_(False))
    elif f.publico == FiltroPublico.TEEN:
        consulta = consulta.where(Aluno.teen.is_(True))
    if f.prazo_de:
        consulta = consulta.where(DATA_PREVISTA >= f.prazo_de)
    if f.prazo_ate:
        consulta = consulta.where(DATA_PREVISTA <= f.prazo_ate)

    busca = f.busca.strip()
    if busca:
        consulta = consulta.where(or_(
            Aluno.nome.ilike(f"%{busca}%"),
            Aluno.aluno_id_egali == busca,
            Programa.programa_id_egali == busca,
            Tarefa.item_checklist_egali == busca,
        ))
    return consulta


def procedimentos_na_fila(incluir: int | None = None) -> list[EtapaModelo]:
    """Procedimentos com tarefa aberta em programa ativo (para o filtro), na ordem das trilhas.
    `incluir` garante que o já escolhido continue na lista, mesmo sem tarefa aberta."""
    com_tarefa = select(Tarefa.etapa_id).join(Tarefa.programa).where(
        Programa.situacao == SituacaoPrograma.ATIVO, Tarefa.status.in_(STATUS_ABERTOS))
    condicao = EtapaModelo.id.in_(com_tarefa)
    if incluir:
        condicao = or_(condicao, EtapaModelo.id == incluir)
    return db.session.execute(
        select(EtapaModelo).join(EtapaModelo.trilha).options(contains_eager(EtapaModelo.trilha))
        .where(condicao).order_by(Trilha.ordem, EtapaModelo.ordem)
    ).scalars().all()


def tarefas(f: Filtros, pagina: int = 1, por_pagina: int = 100) -> tuple[list[Tarefa], int]:
    """Tarefas da fila, prazo mais antigo primeiro (sem prazo no fim). Devolve (página, total)."""
    consulta = _filtrar(_base(), f)
    total = db.session.execute(select(func.count()).select_from(consulta.subquery())).scalar_one()
    consulta = (
        consulta.options(
            contains_eager(Tarefa.programa).contains_eager(Programa.aluno),
            contains_eager(Tarefa.etapa).contains_eager(EtapaModelo.trilha),
            selectinload(Tarefa.anotacoes).joinedload(Anotacao.autor),  # a lista mostra a última observação
        )
        .order_by(DATA_PREVISTA.is_(None), DATA_PREVISTA, Aluno.nome, Tarefa.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )
    return list(db.session.execute(consulta).scalars().unique()), total


def contar(f: Filtros) -> int:
    return db.session.execute(select(func.count()).select_from(_filtrar(_base(), f).subquery())).scalar_one()


def contar_por_status(f: Filtros) -> dict[StatusTarefa, int]:
    """Quantas tarefas em cada status aberto, com os outros filtros aplicados."""
    consulta = _filtrar(_base(), f, com_status=False).with_only_columns(Tarefa.status, func.count()).group_by(Tarefa.status)
    contagem = {s: 0 for s in STATUS_ABERTOS}
    contagem.update(dict(db.session.execute(consulta).all()))
    return contagem


# ---------------------------------------------------------------- outras visualizações


def _ordenadas(consulta):
    return consulta.options(
        contains_eager(Tarefa.programa).contains_eager(Programa.aluno),
        contains_eager(Tarefa.etapa).contains_eager(EtapaModelo.trilha),
    ).order_by(DATA_PREVISTA.is_(None), DATA_PREVISTA, Aluno.nome, Tarefa.id)


@dataclass
class ColunaKanban:
    status: StatusTarefa
    tarefas: list[Tarefa]
    total: int


def kanban(f: Filtros, limite: int = 60) -> list[ColunaKanban]:
    """Uma coluna por status aberto (o filtro de status não se aplica). Cada coluna
    mostra até `limite` cartões, os de prazo mais antigo primeiro."""
    contagem = contar_por_status(f)
    colunas = []
    for status in (StatusTarefa.A_FAZER, StatusTarefa.EM_ANDAMENTO, StatusTarefa.AGUARDANDO_ALUNO):
        consulta = _filtrar(_base(), f, com_status=False).where(Tarefa.status == status)
        tarefas_coluna = list(db.session.execute(_ordenadas(consulta).limit(limite)).scalars().unique())
        colunas.append(ColunaKanban(status, tarefas_coluna, contagem[status]))
    return colunas


@dataclass
class CartaoAluno:
    programa: Programa
    tarefas: list[Tarefa]


def quadro_por_aluno(f: Filtros, pagina: int = 1, por_pagina: int = 30) -> tuple[list[CartaoAluno], int]:
    """Um cartão por programa (aluno) com as tarefas que passam nos filtros.
    O aluno com a tarefa mais urgente vem primeiro. Devolve (página, total de alunos)."""
    base = _filtrar(_base(), f)
    urgencia = func.min(func.coalesce(DATA_PREVISTA, date.max))
    por_programa = base.with_only_columns(Programa.id, urgencia.label("urgencia")).group_by(Programa.id).subquery()
    total = db.session.execute(select(func.count()).select_from(por_programa)).scalar_one()
    ids = db.session.execute(
        select(por_programa.c.id)
        .join(Programa, Programa.id == por_programa.c.id)
        .join(Aluno, Aluno.id == Programa.aluno_id)
        .order_by(por_programa.c.urgencia, Aluno.nome)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    if not ids:
        return [], total
    tarefas_da_pagina = db.session.execute(_ordenadas(base.where(Programa.id.in_(ids)))).scalars().unique()
    por_id: dict[int, CartaoAluno] = {}
    for tarefa in tarefas_da_pagina:
        por_id.setdefault(tarefa.programa_id, CartaoAluno(tarefa.programa, [])).tarefas.append(tarefa)
    return [por_id[i] for i in ids if i in por_id], total


@dataclass
class MesCalendario:
    inicio: date  # segunda-feira da primeira semana mostrada
    semanas: list[list[date]]
    por_dia: dict[date, list[Tarefa]]
    atrasadas_antes: int  # abertas com data prevista antes do primeiro dia mostrado (e antes de hoje)
    sem_prazo: int


def calendario(f: Filtros, ano: int, mes: int) -> MesCalendario:
    """Semanas completas (segunda a domingo) que cobrem o mês. Cada tarefa fica no
    dia da data prevista (a planejada pelo consultor, senão a do procedimento)."""
    import calendar as cal

    semanas = cal.Calendar(firstweekday=0).monthdatescalendar(ano, mes)
    inicio, fim = semanas[0][0], semanas[-1][-1]
    periodo = Filtros(**{**f.__dict__, "prazo_de": inicio, "prazo_ate": fim})
    por_dia: dict[date, list[Tarefa]] = {}
    for tarefa in db.session.execute(_ordenadas(_filtrar(_base(), periodo))).scalars().unique():
        por_dia.setdefault(tarefa.data_prevista, []).append(tarefa)

    def contar(consulta):
        return db.session.execute(select(func.count()).select_from(consulta.subquery())).scalar_one()

    atrasadas_antes = contar(_filtrar(_base(), f).where(DATA_PREVISTA < min(inicio, f.hoje)))
    sem_prazo = contar(_filtrar(_base(), f).where(DATA_PREVISTA.is_(None)))
    return MesCalendario(inicio, semanas, por_dia, atrasadas_antes, sem_prazo)


@dataclass
class LinhaConsultor:
    usuario: Usuario | None  # None = programas sem consultor
    programas: int = 0
    abertas: int = 0
    atrasadas: int = 0
    sem_justificativa: int = 0


def resumo_por_consultor(hoje: date | None = None, publico: FiltroPublico = FiltroPublico.TODOS) -> list[LinhaConsultor]:
    hoje = hoje or date.today()
    atrasada = PRAZO_EGALI < hoje
    tarefas_por_consultor = db.session.execute(
        _filtrar(_base(), Filtros(hoje=hoje, publico=publico))
        .with_only_columns(
            Programa.consultor_id,
            func.count(),
            func.count().filter(atrasada),
            func.count().filter(and_(atrasada, ~TEM_NEG)),
        )
        .group_by(Programa.consultor_id)
    ).all()
    programas_ativos = select(Programa.consultor_id, func.count()).join(Programa.aluno).where(Programa.situacao == SituacaoPrograma.ATIVO)
    if publico == FiltroPublico.SUPORTE:
        programas_ativos = programas_ativos.where(Aluno.teen.is_(False))
    elif publico == FiltroPublico.TEEN:
        programas_ativos = programas_ativos.where(Aluno.teen.is_(True))
    programas_por_consultor = dict(db.session.execute(programas_ativos.group_by(Programa.consultor_id)).all())

    linhas: dict[int | None, LinhaConsultor] = {}
    for usuario in db.session.execute(select(Usuario).where(Usuario.ativo).order_by(Usuario.nome)).scalars():
        linhas[usuario.id] = LinhaConsultor(usuario)
    for consultor_id, abertas, atrasadas, sem_justificativa in tarefas_por_consultor:
        linha = linhas.setdefault(consultor_id, LinhaConsultor(db.session.get(Usuario, consultor_id) if consultor_id else None))
        linha.abertas, linha.atrasadas, linha.sem_justificativa = abertas, atrasadas, sem_justificativa
    for consultor_id, quantidade in programas_por_consultor.items():
        linhas.setdefault(consultor_id, LinhaConsultor(db.session.get(Usuario, consultor_id) if consultor_id else None))
        linhas[consultor_id].programas = quantidade
    # Quem não tem programa nem tarefa (ex.: estagiária) não aparece; "sem consultor" vai para o fim.
    resultado = [l for l in linhas.values() if l.programas or l.abertas]
    return sorted(resultado, key=lambda l: (l.usuario is None, l.usuario.nome if l.usuario else ""))
