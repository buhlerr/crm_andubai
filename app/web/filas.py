"""As três visões obrigatórias: Minha fila, Fila da equipe e Por consultor.

Minha fila e Fila da equipe podem ser vistas como lista, kanban (colunas por
status), quadro (um cartão por aluno) ou calendário (pelo prazo). A escolha
fica guardada no cadastro da pessoa.
"""

from datetime import date, timedelta

from flask import Blueprint, g, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from app import andamento, consultas
from app.consultas import (
    NINGUEM,
    ORGANIZAR_QUADRO,
    ROTULOS_ATRASO,
    ROTULOS_ORGANIZAR,
    ROTULOS_PUBLICO,
    SEM_VISTO,
    FiltroAtraso,
    FiltroPublico,
    Filtros,
    Organizar,
)
from app.extensions import db
from app.importacao.valores import para_data
from app.models import STATUS_ABERTOS, Aluno, Programa, SituacaoPrograma, StatusTarefa, Tarefa, Trilha, Usuario, VisaoFila
from app.texto import normalizar_texto
from app.web.auth import login_obrigatorio

bp = Blueprint("filas", __name__)

POR_PAGINA = 100
ALUNOS_POR_PAGINA = 30
CARTOES_POR_COLUNA = 60

ROTULOS_VISAO = {
    VisaoFila.LISTA: "Lista",
    VisaoFila.KANBAN: "Kanban",
    VisaoFila.QUADRO: "Quadro por aluno",
    VisaoFila.CALENDARIO: "Calendário",
}
MESES = consultas.MESES


def _id_ou_ninguem(valor: str | None):
    if valor == NINGUEM:
        return NINGUEM
    return int(valor) if valor and valor.isdigit() else None


def _data_ou_nada(valor: str | None) -> date | None:
    try:
        return para_data(valor) if valor else None
    except ValueError:
        return None


def _publico_da_url() -> FiltroPublico:
    valor = request.args.get("publico", "")
    return FiltroPublico(valor) if valor in {p.value for p in FiltroPublico} else FiltroPublico.TODOS


def _filtros_da_url() -> Filtros:
    status = request.args.get("status")
    atraso = request.args.get("atraso", "")
    return Filtros(
        publico=_publico_da_url(),
        status=StatusTarefa(status) if status in {s.value for s in STATUS_ABERTOS} else None,
        responsavel=_id_ou_ninguem(request.args.get("responsavel")),
        consultor=_id_ou_ninguem(request.args.get("consultor")),
        trilha=request.args.get("trilha") or None,
        etapa=request.args.get("procedimento", type=int),
        visto=request.args.get("visto") or None,
        atraso=FiltroAtraso(atraso) if atraso in {a.value for a in FiltroAtraso} else FiltroAtraso.TODAS,
        busca=request.args.get("busca", ""),
        prazo_de=_data_ou_nada(request.args.get("prazo_de")),
        prazo_ate=_data_ou_nada(request.args.get("prazo_ate")),
        hoje=date.today(),
    )


def _visao() -> VisaoFila:
    """A da URL (e passa a ser a preferida da pessoa) ou a última que ela usou.
    Com fixar=0 (ex.: "ver todas na lista" a partir do kanban), não troca a preferida."""
    pedida = request.args.get("visao")
    if pedida in {v.value for v in VisaoFila}:
        visao = VisaoFila(pedida)
        if g.usuario.visao_fila != visao and request.args.get("fixar") != "0":
            g.usuario.visao_fila = visao
            db.session.commit()
        return visao
    return g.usuario.visao_fila or VisaoFila.LISTA


def _organizar(visao: VisaoFila) -> Organizar:
    """"Organizar por" da URL (e passa a ser o preferido da pessoa para esta visão) ou o último usado."""
    campo, permitidos = ("organizar_quadro", ORGANIZAR_QUADRO) if visao == VisaoFila.QUADRO else ("organizar_lista", tuple(Organizar))
    pedido = request.args.get("organizar")
    if pedido in {o.value for o in permitidos}:
        if getattr(g.usuario, campo) != pedido and request.args.get("fixar") != "0":
            setattr(g.usuario, campo, pedido)
            db.session.commit()
        return Organizar(pedido)
    guardado = getattr(g.usuario, campo)
    padrao = Organizar.EMBARQUE if visao == VisaoFila.QUADRO else Organizar.DATA
    return Organizar(guardado) if guardado in {o.value for o in permitidos} else padrao


def _mes_da_url(hoje: date) -> tuple[int, int]:
    texto = request.args.get("mes", "")
    try:
        ano, mes = (int(p) for p in texto.split("-"))
        if 1 <= mes <= 12 and 2000 <= ano <= 2100:
            return ano, mes
    except ValueError:
        pass
    return hoje.year, hoje.month


def _vizinho(ano: int, mes: int, passo: int) -> str:
    mes += passo
    ano, mes = ano + (mes - 1) // 12, (mes - 1) % 12 + 1
    return f"{ano:04d}-{mes:02d}"


def _render_fila(titulo: str, filtros: Filtros, mostrar_pessoas: bool, descricao: str):
    visao = _visao()
    organizar = _organizar(visao)
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    contexto = dict(
        organizar=organizar,
        opcoes_organizar=ORGANIZAR_QUADRO if visao == VisaoFila.QUADRO else tuple(Organizar),
        ROTULOS_ORGANIZAR=ROTULOS_ORGANIZAR,
        vistos_opcoes=consultas.vistos_na_fila(filtros.visto),
        SEM_VISTO=SEM_VISTO,
        titulo=titulo,
        descricao=descricao,
        filtros=filtros,
        visao=visao,
        contagem=consultas.contar_por_status(filtros),
        trilhas=db.session.execute(db.select(Trilha).order_by(Trilha.ordem)).scalars().all(),
        procedimentos=consultas.procedimentos_na_fila(filtros.etapa),
        usuarios=db.session.execute(db.select(Usuario).filter_by(ativo=True).order_by(Usuario.nome)).scalars().all(),
        mostrar_pessoas=mostrar_pessoas,
        pagina=pagina,
        paginas=1,
        total=0,
        ROTULOS_ATRASO=ROTULOS_ATRASO,
        ROTULOS_PUBLICO=ROTULOS_PUBLICO,
        ROTULOS_VISAO=ROTULOS_VISAO,
        VisaoFila=VisaoFila,
        NINGUEM=NINGUEM,
        STATUS_ABERTOS=[s for s in StatusTarefa if s in STATUS_ABERTOS],
    )
    if visao == VisaoFila.KANBAN:
        contexto["colunas"] = consultas.kanban(filtros, CARTOES_POR_COLUNA)
        contexto["limite_kanban"] = CARTOES_POR_COLUNA
        contexto["total"] = sum(c.total for c in contexto["colunas"])
    elif visao == VisaoFila.QUADRO:
        cartoes, total = consultas.quadro_por_aluno(filtros, pagina, ALUNOS_POR_PAGINA, organizar)
        contexto.update(cartoes=cartoes, total=total, paginas=max((total + ALUNOS_POR_PAGINA - 1) // ALUNOS_POR_PAGINA, 1))
    elif visao == VisaoFila.CALENDARIO:
        ano, mes = _mes_da_url(filtros.hoje)
        mes_calendario = consultas.calendario(filtros, ano, mes)
        contexto.update(
            mes=mes_calendario, ano_mes=(ano, mes), nome_mes=f"{MESES[mes - 1]} de {ano}",
            ate_antes=min(mes_calendario.inicio, filtros.hoje) - timedelta(days=1),
            mes_anterior=_vizinho(ano, mes, -1), mes_seguinte=_vizinho(ano, mes, 1),
        )
    else:
        tarefas, total = consultas.tarefas(filtros, pagina, POR_PAGINA, organizar)
        contexto.update(tarefas=tarefas, grupos=consultas.agrupar(tarefas, organizar), total=total,
                        paginas=max((total + POR_PAGINA - 1) // POR_PAGINA, 1))
    return render_template("fila.html", **contexto)


@bp.route("/")
@login_obrigatorio
def inicio():
    return redirect(url_for("filas.minha_fila"))


@bp.route("/minha-fila")
@login_obrigatorio
def minha_fila():
    filtros = _filtros_da_url()
    if "prazo_de" not in request.args and "prazo_ate" not in request.args:
        filtros.prazo_ate = consultas.proxima_quinta(filtros.hoje)
    filtros.responsavel = g.usuario.id
    filtros.consultor = None
    return _render_fila("Minha fila", filtros, False, "Tarefas em que você é o responsável.")


@bp.route("/fila")
@login_obrigatorio
def fila_equipe():
    return _render_fila("Fila da equipe", _filtros_da_url(), True, "Todas as tarefas abertas de programas ativos.")


@bp.route("/concluidas")
@login_obrigatorio
def concluidas():
    """Tarefas concluídas ou "não se aplica": as daqui e as que saíram do checklist da Egali."""
    filtros = _filtros_da_url()
    status = request.args.get("status")
    filtros.status = StatusTarefa(status) if status in (StatusTarefa.CONCLUIDA.value, StatusTarefa.NAO_SE_APLICA.value) else None
    de, ate = _data_ou_nada(request.args.get("de")), _data_ou_nada(request.args.get("ate"))
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    linhas, total = consultas.concluidas(filtros, de, ate, pagina, POR_PAGINA)
    return render_template(
        "concluidas.html", linhas=linhas, total=total, pagina=pagina, paginas=max((total + POR_PAGINA - 1) // POR_PAGINA, 1),
        filtros=filtros, de=de, ate=ate,
        trilhas=db.session.execute(db.select(Trilha).order_by(Trilha.ordem)).scalars().all(),
        usuarios=db.session.execute(db.select(Usuario).filter_by(ativo=True).order_by(Usuario.nome)).scalars().all(),
        vistos_opcoes=consultas.vistos_na_fila(filtros.visto), SEM_VISTO=SEM_VISTO,
        ROTULOS_PUBLICO=ROTULOS_PUBLICO, NINGUEM=NINGUEM,
    )


@bp.route("/para-lancar")
@login_obrigatorio
def para_lancar():
    """O que foi feito aqui e ainda precisa ser lançado no sistema da Egali."""
    equipe = request.args.get("quem") == "equipe"
    usuario_id = None if equipe else g.usuario.id
    return render_template(
        "para_lancar.html", equipe=equipe,
        tarefas=consultas.tarefas_para_lancar(usuario_id),
        conferir=consultas.lancadas_mas_abertas(usuario_id),
        anotacoes=consultas.anotacoes_para_lancar(usuario_id),
    )


@bp.route("/consultores")
@login_obrigatorio
def por_consultor():
    publico = _publico_da_url()
    return render_template(
        "consultores.html", linhas=consultas.resumo_por_consultor(date.today(), publico), NINGUEM=NINGUEM,
        publico=publico, ROTULOS_PUBLICO=ROTULOS_PUBLICO,
    )


@bp.route("/andamento-vistos")
@login_obrigatorio
def andamento_vistos():
    """Aluno, consultor e % do processo de visto (100% = "Documentação OK" finalizado), com a NEG do procedimento atual."""
    consultor = _id_ou_ninguem(request.args.get("consultor"))
    situacao = request.args.get("situacao", "")
    busca = normalizar_texto(request.args.get("busca", ""))
    # Data de embarque (de / até). O checklist do ano traz também quem já embarcou: na primeira abertura,
    # o "de" vem com a data de hoje. Campo apagado = sem limite.
    hoje = date.today()
    embarque_de = _data_ou_nada(request.args.get("embarque_de")) if "embarque_de" in request.args else hoje
    embarque_ate = _data_ou_nada(request.args.get("embarque_ate"))
    sem_data = request.args.get("sem_data", "1" if "embarque_de" not in request.args else "") == "1"
    etapa = request.args.get("etapa", "")
    etapas_do_processo = andamento.etapas_do_processo_de_visto()

    consulta = (
        db.select(Programa).join(Programa.aluno)
        .where(Programa.situacao == SituacaoPrograma.ATIVO)
        .options(
            joinedload(Programa.aluno), joinedload(Programa.consultor), selectinload(Programa.compras),
            selectinload(Programa.tarefas).joinedload(Tarefa.etapa),
        )
        .order_by(Aluno.nome)
    )
    if consultor == NINGUEM:
        consulta = consulta.where(Programa.consultor_id.is_(None))
    elif consultor:
        consulta = consulta.where(Programa.consultor_id == consultor)
    if embarque_de or embarque_ate:
        no_periodo = db.and_(
            Programa.data_embarque >= embarque_de if embarque_de else db.true(),
            Programa.data_embarque <= embarque_ate if embarque_ate else db.true(),
        )
        consulta = consulta.where(db.or_(no_periodo, Programa.data_embarque.is_(None)) if sem_data else no_periodo)
    elif not sem_data:
        consulta = consulta.where(Programa.data_embarque.is_not(None))
    programas = db.session.execute(consulta).unique().scalars().all()
    if busca:
        programas = [p for p in programas if busca in normalizar_texto(p.aluno.nome)
                     or busca in (p.aluno.aluno_id_egali or "") or busca in (p.programa_id_egali or "")]

    linhas = andamento.andamentos_de_visto(programas)
    if situacao == "concluido":
        linhas = [l for l in linhas if l.concluido]
    elif situacao == "andamento":
        linhas = [l for l in linhas if not l.concluido]
    if etapa == "concluido":
        linhas = [l for l in linhas if l.concluido]
    elif etapa.isdigit():
        linhas = [l for l in linhas if not l.concluido and l.atual and l.atual.etapa.id == int(etapa)]
    linhas.sort(key=lambda l: (l.porcentagem, normalizar_texto(l.programa.aluno.nome)))
    return render_template(
        "andamento_vistos.html", linhas=linhas, consultor=consultor, situacao=situacao,
        embarque_de=embarque_de, embarque_ate=embarque_ate, sem_data=sem_data, etapa=etapa, etapas_do_processo=etapas_do_processo,
        busca=request.args.get("busca", ""), NINGUEM=NINGUEM, Situacao=andamento.Situacao,
        usuarios=db.session.execute(db.select(Usuario).filter_by(ativo=True).order_by(Usuario.nome)).scalars().all(),
    )
