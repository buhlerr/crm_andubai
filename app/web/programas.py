from flask import Blueprint, abort, render_template, request

from app import andamento
from app.extensions import db
from app.models import Aluno, EtapaModelo, Programa, Tarefa, Trilha
from app.web.auth import login_obrigatorio

bp = Blueprint("programas", __name__)


@bp.route("/programas/<int:programa_id>")
@login_obrigatorio
def detalhe(programa_id):
    programa = db.session.get(Programa, programa_id) or abort(404, "Programa não encontrado.")
    tarefas = db.session.execute(
        db.select(Tarefa).join(Tarefa.etapa).join(EtapaModelo.trilha)
        .filter(Tarefa.programa_id == programa.id)
        .order_by(Trilha.ordem, EtapaModelo.ordem, Tarefa.prazo_egali)
    ).scalars().all()
    abertas = [t for t in tarefas if t.aberta]
    encerradas = [t for t in tarefas if not t.aberta]
    outros = [p for p in programa.aluno.programas if p.id != programa.id]
    return render_template("programa.html", programa=programa, abertas=abertas, encerradas=encerradas, outros=outros,
                           andamento=andamento.calcular(programa), Situacao=andamento.Situacao,
                           ROTULOS_ANDAMENTO=andamento.ROTULOS)


@bp.route("/busca")
@login_obrigatorio
def busca():
    termo = request.args.get("q", "").strip()
    alunos = []
    if termo:
        alunos = db.session.execute(
            db.select(Aluno).outerjoin(Aluno.programas).where(db.or_(
                Aluno.nome.ilike(f"%{termo}%"),
                Aluno.aluno_id_egali == termo,
                Programa.programa_id_egali == termo,
            )).order_by(Aluno.nome).limit(100)
        ).scalars().unique().all()
    return render_template("busca.html", termo=termo, alunos=alunos)
