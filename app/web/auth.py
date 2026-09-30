"""Autenticação e controle de acesso por e-mail e senha.

Permite login individual com e-mail e senha cadastrados no sistema,
além de autoatendimento para troca de senha e transição suave para
contas que ainda não possuem senha definida.
"""

import secrets
from functools import wraps

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import func

from app.extensions import db
from app.models import Papel, Usuario

bp = Blueprint("auth", __name__)


@bp.before_app_request
def carregar_usuario():
    usuario_id = session.get("usuario_id")
    g.usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
    if g.usuario is not None and not g.usuario.ativo:
        session.pop("usuario_id", None)
        g.usuario = None


def login_obrigatorio(view):
    @wraps(view)
    def envolvida(*args, **kwargs):
        if g.usuario is None:
            return redirect(url_for("auth.entrar", proximo=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return envolvida


def admin_obrigatorio(view):
    @wraps(view)
    @login_obrigatorio
    def envolvida(*args, **kwargs):
        if g.usuario.papel != Papel.ADMIN:
            abort(403, "Esta página é só para administradores.")
        return view(*args, **kwargs)

    return envolvida


def destino_seguro(proximo: str | None, padrao: str) -> str:
    """Só aceita caminhos deste site (evita redirecionar para outro endereço)."""
    if proximo and proximo.startswith("/") and not proximo.startswith("//") and "\\" not in proximo:
        return proximo
    return padrao


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    erro = None
    email_informado = ""
    total_usuarios = db.session.execute(db.select(func.count(Usuario.id))).scalar() or 0

    if request.method == "POST":
        email_informado = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        usuario = db.session.execute(
            db.select(Usuario).filter(func.lower(Usuario.email) == email_informado, Usuario.ativo.is_(True))
        ).scalar_one_or_none()

        senha_equipe = current_app.config.get("SENHA_PROVISORIA")

        if not email_informado or not senha:
            erro = "Informe seu e-mail e sua senha."
        elif usuario is None:
            erro = "E-mail ou senha incorretos."
        elif usuario.senha_hash and usuario.verificar_senha(senha):
            session.clear()
            session["usuario_id"] = usuario.id
            return redirect(destino_seguro(request.args.get("proximo"), url_for("filas.minha_fila")))
        elif not usuario.senha_hash and senha_equipe and secrets.compare_digest(senha, senha_equipe):
            # Transição: usuário antigo sem senha individual acessando com a senha de equipe
            session.clear()
            session["usuario_id"] = usuario.id
            flash("Bem-vindo(a)! Você ainda não cadastrou uma senha individual. Por favor, defina sua senha abaixo.", "alerta")
            return redirect(url_for("auth.trocar_senha"))
        else:
            erro = "E-mail ou senha incorretos."

    return render_template("entrar.html", erro=erro, email=email_informado, total_usuarios=total_usuarios)


@bp.route("/trocar-senha", methods=["GET", "POST"])
@login_obrigatorio
def trocar_senha():
    erro = None
    usuario = g.usuario
    tem_senha_atual = bool(usuario.senha_hash)

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmacao = request.form.get("confirmacao", "")

        if tem_senha_atual and not usuario.verificar_senha(senha_atual):
            erro = "A senha atual informada está incorreta."
        elif len(nova_senha) < 6:
            erro = "A nova senha deve ter pelo menos 6 caracteres."
        elif nova_senha != confirmacao:
            erro = "A confirmação não coincide com a nova senha."
        else:
            usuario.definir_senha(nova_senha)
            db.session.commit()
            flash("Sua senha foi alterada com sucesso.", "ok")
            return redirect(url_for("filas.minha_fila"))

    return render_template("trocar_senha.html", erro=erro, tem_senha_atual=tem_senha_atual)


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("auth.entrar"))
