"""Autenticação e controle de acesso por e-mail e senha.

Permite login individual com e-mail e senha cadastrados no sistema,
além de autoatendimento para troca de senha e transição suave para
contas que ainda não possuem senha definida.
"""

import logging
import secrets
import time
from functools import wraps

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import func

from app.extensions import db
from app.models import Papel, Usuario
from app.models.cadastro import SENHA_MINIMA

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


TENTATIVAS_MAXIMAS = 10  # por e-mail e por endereço, em JANELA_TENTATIVAS segundos
JANELA_TENTATIVAS = 15 * 60
_tentativas: dict[str, list[float]] = {}  # em memória, por processo (com gunicorn -w 4, o limite é por processo)
log = logging.getLogger("checklist.auth")


def _bloqueado(*chaves: str) -> bool:
    agora_ = time.monotonic()
    for chave in chaves:
        recentes = [t for t in _tentativas.get(chave, []) if agora_ - t < JANELA_TENTATIVAS]
        _tentativas[chave] = recentes
        if len(recentes) >= TENTATIVAS_MAXIMAS:
            return True
    return False


def _registrar_falha(*chaves: str) -> None:
    for chave in chaves:
        _tentativas.setdefault(chave, []).append(time.monotonic())


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    erro = None
    email_informado = ""
    total_usuarios = db.session.execute(db.select(func.count(Usuario.id))).scalar() or 0

    if request.method == "POST":
        email_informado = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        chaves = (f"email:{email_informado}", f"ip:{request.remote_addr}")
        if _bloqueado(*chaves):
            return render_template("entrar.html", erro="Muitas tentativas. Aguarde alguns minutos e tente de novo.",
                                   email=email_informado, total_usuarios=total_usuarios), 429

        usuario = db.session.execute(
            db.select(Usuario).filter(func.lower(Usuario.email) == email_informado, Usuario.ativo.is_(True))
        ).scalar_one_or_none()

        senha_equipe = current_app.config.get("SENHA_PROVISORIA")
        # Transição só com LOGIN_PROVISORIO ligado, e nunca para administrador (a senha da equipe é
        # conhecida por muita gente: com ela, alguém tomaria a conta de um admin que ainda não criou senha).
        transicao = (current_app.config.get("LOGIN_PROVISORIO") and senha_equipe and usuario is not None
                     and not usuario.senha_hash and usuario.papel != Papel.ADMIN)

        if not email_informado or not senha:
            erro = "Informe seu e-mail e sua senha."
        elif usuario is None:
            erro = "E-mail ou senha incorretos."
        elif usuario.senha_hash and usuario.verificar_senha(senha):
            session.clear()
            session["usuario_id"] = usuario.id
            return redirect(destino_seguro(request.args.get("proximo"), url_for("filas.minha_fila")))
        elif transicao and secrets.compare_digest(senha, senha_equipe):
            log.warning("Entrada pela senha da equipe (transição): usuário %s, endereço %s", usuario.id, request.remote_addr)
            session.clear()
            session["usuario_id"] = usuario.id
            flash("Bem-vindo(a)! Você ainda não cadastrou uma senha individual. Por favor, defina sua senha abaixo.", "alerta")
            return redirect(url_for("auth.trocar_senha"))
        elif usuario is not None and not usuario.senha_hash and usuario.papel == Papel.ADMIN:
            erro = "Administradores precisam de senha individual. Peça a outro administrador para definir uma."
        else:
            erro = "E-mail ou senha incorretos."
        _registrar_falha(*chaves)

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
        elif len(nova_senha) < SENHA_MINIMA:
            erro = f"A nova senha deve ter pelo menos {SENHA_MINIMA} caracteres."
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
