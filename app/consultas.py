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
from datetime import date, datetime

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import aliased, contains_eager, joinedload, selectinload

from app.extensions import db
from app.models import (
    ROTULOS_STATUS,
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


class Organizar(enum.StrEnum):
    """"Organizar por" da lista (agrupa as tarefas) e do quadro (ordena os alunos)."""

    DATA = "data"  # data prevista (planejada, senão a do procedimento)
    PROCEDIMENTO = "procedimento"
    VISTO = "visto"
    EMBARQUE = "embarque"
    RESPONSAVEL = "responsavel"
    STATUS = "status"


ROTULOS_ORGANIZAR = {
    Organizar.DATA: "Data prevista",
    Organizar.PROCEDIMENTO: "Procedimento",
    Organizar.VISTO: "Tipo de visto",
    Organizar.EMBARQUE: "Data de embarque",
    Organizar.RESPONSAVEL: "Responsável",
    Organizar.STATUS: "Status",
}
# No quadro, um cartão por aluno: procedimento e status não ordenam alunos.
ORGANIZAR_QUADRO = (Organizar.EMBARQUE, Organizar.DATA, Organizar.VISTO, Organizar.RESPONSAVEL)
ORDEM_STATUS = {StatusTarefa.A_FAZER: 0, StatusTarefa.EM_ANDAMENTO: 1, StatusTarefa.AGUARDANDO_ALUNO: 2,
                StatusTarefa.CONCLUIDA: 3, StatusTarefa.NAO_SE_APLICA: 4}
SEM_VISTO = "sem"  # valor do filtro de visto para "sem visto informado"

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
    visto: str | None = None  # um visto como está na planilha ("Turista - EUA") ou SEM_VISTO
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

    consulta = _filtros_comuns(consulta, f)

    atrasada = PRAZO_EGALI < f.hoje
    if f.atraso == FiltroAtraso.ATRASADAS:
        consulta = consulta.where(atrasada)
    elif f.atraso == FiltroAtraso.SEM_JUSTIFICATIVA:
        consulta = consulta.where(atrasada, ~TEM_NEG)
    elif f.atraso == FiltroAtraso.COM_JUSTIFICATIVA:
        consulta = consulta.where(atrasada, TEM_NEG)
    elif f.atraso == FiltroAtraso.NO_PRAZO:
        consulta = consulta.where(or_(PRAZO_EGALI.is_(None), PRAZO_EGALI >= f.hoje))
    if f.prazo_de:
        consulta = consulta.where(DATA_PREVISTA >= f.prazo_de)
    if f.prazo_ate:
        consulta = consulta.where(DATA_PREVISTA <= f.prazo_ate)
    return consulta


def _filtros_comuns(consulta, f: Filtros):
    """Pessoa, trilha, procedimento, visto, público e busca: valem também para Concluídas e Para lançar."""
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
    if f.visto == SEM_VISTO:
        consulta = consulta.where(or_(Programa.visto_normalizado.is_(None), Programa.visto_normalizado == "",
                                      Programa.visto_normalizado == "Sem visto informado"))
    elif f.visto:
        # A célula pode ter vários vistos separados por vírgula: procura o item inteiro.
        celula = literal(",").concat(func.replace(func.coalesce(Programa.visto_normalizado, ""), ", ", ",")).concat(",")
        consulta = consulta.where(celula.like(f"%,{f.visto},%"))
    if f.publico == FiltroPublico.SUPORTE:
        consulta = consulta.where(Aluno.teen.is_(False))
    elif f.publico == FiltroPublico.TEEN:
        consulta = consulta.where(Aluno.teen.is_(True))

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


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
SEM_VISTO_TEXTO = ("", "Sem visto informado")


def _ordem(consulta, organizar: Organizar):
    """Ordem das tarefas para cada "Organizar por" (sempre desempata pela data prevista)."""
    por_data = (DATA_PREVISTA.is_(None), DATA_PREVISTA, Aluno.nome, Tarefa.id)
    if organizar == Organizar.PROCEDIMENTO:
        return consulta.order_by(Trilha.ordem, EtapaModelo.ordem, EtapaModelo.id, *por_data)
    if organizar == Organizar.VISTO:
        sem = or_(Programa.visto_normalizado.is_(None), Programa.visto_normalizado.in_(SEM_VISTO_TEXTO))
        return consulta.order_by(sem, Programa.visto_normalizado, *por_data)
    if organizar == Organizar.EMBARQUE:
        return consulta.order_by(*_ordem_de_embarque(), Aluno.nome, *por_data)
    if organizar == Organizar.RESPONSAVEL:
        quem = aliased(Usuario)
        return consulta.outerjoin(quem, quem.id == RESPONSAVEL).order_by(quem.nome.is_(None), quem.nome, *por_data)
    if organizar == Organizar.STATUS:
        return consulta.order_by(case(*[(Tarefa.status == s, n) for s, n in ORDEM_STATUS.items()]), *por_data)
    return consulta.order_by(*por_data)


def _ordem_de_embarque():
    """Próximos embarques primeiro (do mais perto ao mais longe); depois os que já passaram
    (do mais recente ao mais antigo); sem data no fim."""
    hoje = date.today()
    passou = Programa.data_embarque < hoje
    return (Programa.data_embarque.is_(None), passou,
            case((passou, None), else_=Programa.data_embarque), case((passou, Programa.data_embarque)).desc())


def _mes_de_embarque(programa: Programa) -> str:
    d = programa.data_embarque
    if not d:
        return "Sem data de embarque"
    if d < date.today():
        return "Embarque já passou"
    return f"Embarque em {MESES[d.month - 1]} de {d.year}"


def rotulo_do_grupo(tarefa: Tarefa, organizar: Organizar) -> str | None:
    """Título do grupo da tarefa na lista (None = sem grupos)."""
    from app import vistos

    if organizar == Organizar.PROCEDIMENTO:
        return f"{tarefa.etapa.trilha.nome} · {tarefa.etapa.nome}"
    if organizar == Organizar.VISTO:
        return vistos.texto_de_visto(tarefa.programa)
    if organizar == Organizar.EMBARQUE:
        return _mes_de_embarque(tarefa.programa)
    if organizar == Organizar.RESPONSAVEL:
        return tarefa.responsavel.nome if tarefa.responsavel else "Sem responsável"
    if organizar == Organizar.STATUS:
        return ROTULOS_STATUS[tarefa.status]
    return None


def agrupar(tarefas_: list[Tarefa], organizar: Organizar) -> list[tuple[str | None, list[Tarefa]]]:
    grupos: list[tuple[str | None, list[Tarefa]]] = []
    for t in tarefas_:
        rotulo = rotulo_do_grupo(t, organizar)
        if not grupos or grupos[-1][0] != rotulo:
            grupos.append((rotulo, []))
        grupos[-1][1].append(t)
    return grupos


def tarefas(f: Filtros, pagina: int = 1, por_pagina: int = 100,
            organizar: Organizar = Organizar.DATA) -> tuple[list[Tarefa], int]:
    """Tarefas da fila na ordem do "Organizar por" (padrão: prazo mais antigo primeiro). Devolve (página, total)."""
    consulta = _filtrar(_base(), f)
    total = db.session.execute(select(func.count()).select_from(consulta.subquery())).scalar_one()
    consulta = _ordem(consulta.options(
        contains_eager(Tarefa.programa).contains_eager(Programa.aluno),
        contains_eager(Tarefa.etapa).contains_eager(EtapaModelo.trilha),
        selectinload(Tarefa.anotacoes).joinedload(Anotacao.autor),  # a lista mostra a última observação
        contains_eager(Tarefa.programa).selectinload(Programa.compras),  # tipo de visto dos programas só de visto
    ), organizar).offset((pagina - 1) * por_pagina).limit(por_pagina)
    return list(db.session.execute(consulta).scalars().unique()), total


def vistos_na_fila(incluir: str | None = None) -> list[tuple[str, str]]:
    """Opções do filtro de visto: (valor como na planilha, rótulo "Visto - País - Tipo")."""
    from app import vistos

    celulas = db.session.execute(
        select(Programa.visto_normalizado).distinct().where(Programa.situacao == SituacaoPrograma.ATIVO)
    ).scalars()
    valores = {t for c in celulas for t in vistos.tokens(c)}
    if incluir and incluir != SEM_VISTO:
        valores.add(incluir)
    return sorted(((v, vistos.rotulo(v)) for v in valores), key=lambda par: par[1])


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
    grupo: str | None = None  # título do grupo (ex.: "Embarque em outubro de 2026")

    @property
    def atrasadas(self) -> int:
        return sum(1 for t in self.tarefas if t.atrasada())

    @property
    def proxima(self) -> date | None:
        datas = [t.data_prevista for t in self.tarefas if t.data_prevista]
        return min(datas) if datas else None


def _grupo_do_cartao(programa: Programa, organizar: Organizar) -> str | None:
    from app import vistos

    if organizar == Organizar.EMBARQUE:
        return _mes_de_embarque(programa)
    if organizar == Organizar.VISTO:
        return vistos.texto_de_visto(programa)
    if organizar == Organizar.RESPONSAVEL:
        return programa.consultor.nome if programa.consultor else "Sem consultor"
    return None


def quadro_por_aluno(f: Filtros, pagina: int = 1, por_pagina: int = 30,
                     organizar: Organizar = Organizar.EMBARQUE) -> tuple[list[CartaoAluno], int]:
    """Um cartão por programa (aluno) com as tarefas que passam nos filtros. Padrão: embarque mais
    próximo primeiro; "data" = aluno com a tarefa mais urgente primeiro. Devolve (página, total de alunos)."""
    base = _filtrar(_base(), f)
    urgencia = func.min(func.coalesce(DATA_PREVISTA, date.max))
    por_programa = base.with_only_columns(Programa.id, urgencia.label("urgencia")).group_by(Programa.id).subquery()
    total = db.session.execute(select(func.count()).select_from(por_programa)).scalar_one()
    consulta = (select(por_programa.c.id)
                .join(Programa, Programa.id == por_programa.c.id)
                .join(Aluno, Aluno.id == Programa.aluno_id))
    embarque = _ordem_de_embarque()
    if organizar == Organizar.DATA:
        consulta = consulta.order_by(por_programa.c.urgencia, Aluno.nome)
    elif organizar == Organizar.VISTO:
        sem = or_(Programa.visto_normalizado.is_(None), Programa.visto_normalizado.in_(SEM_VISTO_TEXTO))
        consulta = consulta.order_by(sem, Programa.visto_normalizado, *embarque, Aluno.nome)
    elif organizar == Organizar.RESPONSAVEL:
        consultor = aliased(Usuario)
        consulta = (consulta.outerjoin(consultor, consultor.id == Programa.consultor_id)
                    .order_by(consultor.nome.is_(None), consultor.nome, *embarque, Aluno.nome))
    else:
        consulta = consulta.order_by(*embarque, Aluno.nome)
    ids = db.session.execute(consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)).scalars().all()
    if not ids:
        return [], total
    tarefas_da_pagina = db.session.execute(_ordenadas(base.where(Programa.id.in_(ids)))).scalars().unique()
    por_id: dict[int, CartaoAluno] = {}
    for tarefa in tarefas_da_pagina:
        por_id.setdefault(tarefa.programa_id, CartaoAluno(tarefa.programa, [])).tarefas.append(tarefa)
    cartoes = [por_id[i] for i in ids if i in por_id]
    for c in cartoes:
        c.grupo = _grupo_do_cartao(c.programa, organizar)
    return cartoes, total


# ---------------------------------------------------------------- concluídas


@dataclass
class LinhaConcluida:
    tarefa: Tarefa
    quando: datetime | None
    origem: str  # "Neste sistema", "Saiu do checklist da Egali", "Encerrada à mão"
    quem: str | None  # nome de quem concluiu no sistema (ou de quem encerrou à mão)

    @property
    def dias_depois_do_prazo(self) -> int | None:
        """Dias entre a data do procedimento e a conclusão (0 = no prazo; None = sem data)."""
        from app.models.base import hora_local

        if not (self.quando and self.tarefa.prazo_egali):
            return None
        return max(0, (hora_local(self.quando).date() - self.tarefa.prazo_egali).days)


QUANDO_CONCLUIU = func.coalesce(Tarefa.concluida_em, Tarefa.encerrada_egali_em, Tarefa.atualizado_em)


def concluidas(f: Filtros, de: date | None = None, ate: date | None = None,
               pagina: int = 1, por_pagina: int = 100) -> tuple[list[LinhaConcluida], int]:
    """Tarefas concluídas ou "não se aplica", de qualquer programa, a mais recente primeiro."""
    from app.models import HistoricoTarefa

    consulta = _filtros_comuns(
        select(Tarefa).join(Tarefa.programa).join(Programa.aluno).join(Tarefa.etapa).join(EtapaModelo.trilha)
        .where(Tarefa.status.in_((StatusTarefa.CONCLUIDA, StatusTarefa.NAO_SE_APLICA))), f)
    if f.status in (StatusTarefa.CONCLUIDA, StatusTarefa.NAO_SE_APLICA):
        consulta = consulta.where(Tarefa.status == f.status)
    if de:
        consulta = consulta.where(func.date(QUANDO_CONCLUIU) >= de)
    if ate:
        consulta = consulta.where(func.date(QUANDO_CONCLUIU) <= ate)
    total = db.session.execute(select(func.count()).select_from(consulta.subquery())).scalar_one()
    pagina_ = list(db.session.execute(
        consulta.options(contains_eager(Tarefa.programa).contains_eager(Programa.aluno),
                         contains_eager(Tarefa.etapa).contains_eager(EtapaModelo.trilha))
        .order_by(QUANDO_CONCLUIU.desc(), Tarefa.id.desc())
        .offset((pagina - 1) * por_pagina).limit(por_pagina)
    ).scalars().unique())

    # Quem concluiu (último status concluída/não se aplica feito por uma pessoa) e quem encerrou à mão.
    ids = [t.id for t in pagina_]
    quem: dict[int, str] = {}
    a_mao: set[int] = set()
    if ids:
        for tarefa_id, campo, valor, nome in db.session.execute(
            select(HistoricoTarefa.tarefa_id, HistoricoTarefa.campo, HistoricoTarefa.valor_novo, Usuario.nome)
            .join(Usuario, Usuario.id == HistoricoTarefa.usuario_id)
            .where(HistoricoTarefa.tarefa_id.in_(ids), HistoricoTarefa.campo.in_(("status", "encerramento")))
            .order_by(HistoricoTarefa.quando)
        ):
            if campo == "encerramento":
                a_mao.add(tarefa_id)
                quem[tarefa_id] = nome
            elif valor in (StatusTarefa.CONCLUIDA.value, StatusTarefa.NAO_SE_APLICA.value):
                quem[tarefa_id] = nome
    linhas = []
    for t in pagina_:
        if t.id in a_mao:
            origem = "Encerrada à mão"
        elif t.encerrada_egali_em and (t.concluida_em is None or t.concluida_em >= t.encerrada_egali_em):
            origem = "Saiu do checklist da Egali"
        else:
            origem = "Neste sistema"
        linhas.append(LinhaConcluida(t, t.concluida_em or t.encerrada_egali_em or t.atualizado_em, origem,
                                     quem.get(t.id) if origem != "Saiu do checklist da Egali" else None))
    return linhas, total


# ---------------------------------------------------------------- para lançar na Egali

FEITAS = (StatusTarefa.CONCLUIDA, StatusTarefa.NAO_SE_APLICA)


def _base_lancar(usuario_id: int | None):
    consulta = (select(Tarefa).join(Tarefa.programa).join(Programa.aluno).join(Tarefa.etapa).join(EtapaModelo.trilha)
                .where(Programa.situacao == SituacaoPrograma.ATIVO, Tarefa.encerrada_egali_em.is_(None)))
    if usuario_id:
        consulta = consulta.where(RESPONSAVEL == usuario_id)
    return consulta.options(contains_eager(Tarefa.programa).contains_eager(Programa.aluno),
                            contains_eager(Tarefa.etapa).contains_eager(EtapaModelo.trilha))


def tarefas_para_lancar(usuario_id: int | None = None) -> list[Tarefa]:
    """Concluídas (ou "não se aplica") aqui, ainda abertas na Egali e não marcadas como lançadas."""
    return list(db.session.execute(
        _base_lancar(usuario_id).where(Tarefa.status.in_(FEITAS), Tarefa.lancada_egali_em.is_(None))
        .order_by(Tarefa.concluida_em, Tarefa.id)
    ).scalars().unique())


def lancadas_mas_abertas(usuario_id: int | None = None) -> list[Tarefa]:
    """Marcadas como lançadas, mas uma importação feita DEPOIS ainda trouxe o item aberto na Egali."""
    from app.models import Importacao

    return list(db.session.execute(
        _base_lancar(usuario_id).join(Importacao, Importacao.id == Tarefa.ultima_importacao_id)
        .where(Tarefa.status.in_(FEITAS), Tarefa.lancada_egali_em.is_not(None),
               Importacao.concluida_em > Tarefa.lancada_egali_em)
        .order_by(Tarefa.lancada_egali_em)
    ).scalars().unique())


def anotacoes_para_lancar(usuario_id: int | None = None) -> list[Anotacao]:
    """Observações feitas aqui que ainda não viraram NEG na Egali (nem foram dispensadas)."""
    consulta = (select(Anotacao).join(Anotacao.tarefa).join(Tarefa.programa).join(Programa.aluno).join(Tarefa.etapa)
                .where(Programa.situacao == SituacaoPrograma.ATIVO, Tarefa.encerrada_egali_em.is_(None),
                       Anotacao.lancada_egali_em.is_(None), Anotacao.nao_precisa_lancar.is_(False)))
    if usuario_id:
        consulta = consulta.where(or_(Anotacao.autor_id == usuario_id, RESPONSAVEL == usuario_id))
    return list(db.session.execute(consulta.order_by(Anotacao.criado_em)).scalars().unique())


def contar_para_lancar(usuario_id: int) -> int:
    return len(tarefas_para_lancar(usuario_id)) + len(anotacoes_para_lancar(usuario_id)) + len(lancadas_mas_abertas(usuario_id))


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
