from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from app import acoes_tarefa
from app.extensions import db
from app.importacao.valores import para_data
from app.models import ROTULOS_STATUS, HistoricoTarefa, StatusTarefa, Tarefa, Usuario
from app.web.auth import destino_seguro, login_obrigatorio

bp = Blueprint("tarefas", __name__, url_prefix="/tarefas")


def _tarefa(tarefa_id: int) -> Tarefa:
    return db.session.get(Tarefa, tarefa_id) or abort(404, "Tarefa não encontrada.")


def _voltar(tarefa: Tarefa):
    return redirect(destino_seguro(request.form.get("voltar"), url_for("tarefas.detalhe", tarefa_id=tarefa.id)))


@bp.route("/<int:tarefa_id>")
@login_obrigatorio
def detalhe(tarefa_id):
    tarefa = _tarefa(tarefa_id)
    historico = db.session.execute(
        db.select(HistoricoTarefa, Usuario)
        .outerjoin(Usuario, Usuario.id == HistoricoTarefa.usuario_id)
        .filter(HistoricoTarefa.tarefa_id == tarefa.id)
        .order_by(HistoricoTarefa.quando.desc())
    ).all()
    return render_template(
        "tarefa.html",
        tarefa=tarefa,
        historico=historico,
        usuarios=db.session.execute(db.select(Usuario).filter_by(ativo=True).order_by(Usuario.nome)).scalars().all(),
        rotulo_campo=acoes_tarefa.ROTULOS_CAMPOS_HISTORICO,
        descrever=acoes_tarefa.descrever_valor,
    )


@bp.route("/<int:tarefa_id>/status", methods=["POST"])
@login_obrigatorio
def mudar_status(tarefa_id):
    tarefa = _tarefa(tarefa_id)
    try:
        status = StatusTarefa(request.form.get("status", ""))
    except ValueError:
        abort(400, "Status inválido.")
    if request.headers.get("X-Requested-With") == "fetch":
        # Arrastar e soltar no Kanban: responde sem recarregar a página.
        mudou = acoes_tarefa.mudar_status(tarefa, status, g.usuario)
        return jsonify(ok=True, mudou=mudou, status=status.value, rotulo=ROTULOS_STATUS[status])
    if acoes_tarefa.mudar_status(tarefa, status, g.usuario):
        flash(f"{tarefa.programa.aluno.nome} · {tarefa.etapa.nome}: agora está \"{ROTULOS_STATUS[status]}\".", "ok")
    return _voltar(tarefa)


@bp.route("/<int:tarefa_id>/responsavel", methods=["POST"])
@login_obrigatorio
def mudar_responsavel(tarefa_id):
    tarefa = _tarefa(tarefa_id)
    valor = request.form.get("responsavel", "")
    novo = None
    if valor:
        novo = db.session.get(Usuario, int(valor)) if valor.isdigit() else None
        if novo is None or not novo.ativo:
            abort(400, "Responsável inválido.")
    if acoes_tarefa.mudar_responsavel(tarefa, novo, g.usuario):
        flash("Responsável atualizado.", "ok")
    return _voltar(tarefa)


@bp.route("/<int:tarefa_id>/data-planejada", methods=["POST"])
@login_obrigatorio
def mudar_data_planejada(tarefa_id):
    tarefa = _tarefa(tarefa_id)
    via_calendario = request.headers.get("X-Requested-With") == "fetch"
    texto = "" if request.form.get("usar_egali") else request.form.get("data", "").strip()
    try:
        data = para_data(texto) if texto else None
    except ValueError:
        if via_calendario:
            return jsonify(ok=False, erro="Data inválida."), 400
        flash("Data inválida. Use o formato dd/mm/aaaa.", "erro")
        return _voltar(tarefa)
    mudou = acoes_tarefa.mudar_data_planejada(tarefa, data, g.usuario)
    if via_calendario:
        # Arrastar no calendário: responde sem recarregar a página.
        return jsonify(
            ok=True, mudou=mudou,
            data_prevista=tarefa.data_prevista.isoformat() if tarefa.data_prevista else None,
            planejada=tarefa.data_planejada is not None,
            apos_prazo=tarefa.planejada_apos_prazo,
        )
    if mudou:
        if tarefa.data_planejada is None:
            flash("A data planejada voltou a ser a data do procedimento.", "ok")
        elif tarefa.planejada_apos_prazo:
            flash("Data planejada salva. Atenção: ela é depois da data do procedimento na Egali.", "alerta")
        else:
            flash("Data planejada salva.", "ok")
    return _voltar(tarefa)


@bp.route("/<int:tarefa_id>/anotacoes", methods=["POST"])
@login_obrigatorio
def anotar(tarefa_id):
    tarefa = _tarefa(tarefa_id)
    if acoes_tarefa.anotar(tarefa, request.form.get("texto", ""), g.usuario):
        flash("Anotação salva.", "ok")
    else:
        flash("Escreva a anotação antes de salvar.", "erro")
    return _voltar(tarefa)
