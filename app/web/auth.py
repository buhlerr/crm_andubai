"""Autenticação e controle de acesso por e-mail e senha.

Permite login individual com e-mail e senha cadastrados no sistema,
além de autoatendimento para troca de senha e transição suave para
contas que ainda não possuem senha definida.
"""

import secrets
import time
from collections import defaultdict
from functools import wraps

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import func

from app.extensions import db
from app.models import Papel, Usuario

bp = Blueprint("auth", __name__)

# Registro em memória de tentativas de login falhas por IP e por e-mail
_TENTATIVAS_FALHAS: dict[str, list[float]] = defaultdict(list)
JANELA_TENTATIVAS_SEGUNDOS = 15 * 60  # 15 minutos
MAX_TENTATIVAS = 10


def _obter_ip_cliente() -> str:
    # Se ATRAS_DE_PROXY=True, request.remote_addr já foi corrigido pelo ProxyFix
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def _limpar_tentativas_expiradas(chave: str, agora_ts: float) -> list[float]:
    limite = agora_ts - JANELA_TENTATIVAS_SEGUNDOS
    _TENTATIVAS_FALHAS[chave] = [ts for ts in _TENTATIVAS_FALHAS[chave] if ts > limite]
    return _TENTATIVAS_FALHAS[chave]


def _esta_bloqueado(ip: str, email: str) -> bool:
    agora_ts = time.time()
    tentativas_ip = _limpar_tentativas_expiradas(f"ip:{ip}", agora_ts)
    tentativas_email = _limpar_tentativas_expiradas(f"email:{email}", agora_ts) if email else []
    return len(tentativas_ip) >= MAX_TENTATIVAS or len(tentativas_email) >= MAX_TENTATIVAS


def _registrar_tentativa_falha(ip: str, email: str) -> None:
    agora_ts = time.time()
    _TENTATIVAS_FALHAS[f"ip:{ip}"].append(agora_ts)
    if email:
        _TENTATIVAS_FALHAS[f"email:{email}"].append(agora_ts)


def _limpar_tentativas(ip: str, email: str) -> None:
    _TENTATIVAS_FALHAS.pop(f"ip:{ip}", None)
    if email:
        _TENTATIVAS_FALHAS.pop(f"email:{email}", None)


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
    ip = _obter_ip_cliente()

    if request.method == "POST":
        email_informado = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if _esta_bloqueado(ip, email_informado):
            erro = "Muitas tentativas. Aguarde alguns minutos."
            return render_template("entrar.html", erro=erro, email=email_informado, total_usuarios=total_usuarios), 429

        usuario = db.session.execute(
            db.select(Usuario).filter(func.lower(Usuario.email) == email_informado, Usuario.ativo.is_(True))
        ).scalar_one_or_none()

        senha_equipe = current_app.config.get("SENHA_PROVISORIA")
        login_provisorio_ativo = current_app.config.get("LOGIN_PROVISORIO", False)

        if not email_informado or not senha:
            erro = "Informe seu e-mail e sua senha."
            _registrar_tentativa_falha(ip, email_informado)
        elif usuario is None:
            erro = "E-mail ou senha incorretos."
            _registrar_tentativa_falha(ip, email_informado)
        elif usuario.senha_hash and usuario.verificar_senha(senha):
            _limpar_tentativas(ip, email_informado)
            session.clear()
            session["usuario_id"] = usuario.id
            return redirect(destino_seguro(request.args.get("proximo"), url_for("filas.minha_fila")))
        elif not usuario.senha_hash and senha_equipe and secrets.compare_digest(senha, senha_equipe):
            if not login_provisorio_ativo:
                erro = "E-mail ou senha incorretos."
                _registrar_tentativa_falha(ip, email_informado)
            elif usuario.papel == Papel.ADMIN:
                current_app.logger.warning(
                    "Tentativa de login de transição rejeitada para administrador %s (%s) a partir do IP %s",
                    usuario.nome,
                    usuario.email,
                    ip,
                )
                erro = "Contas de administrador não podem usar a senha provisória da equipe. Solicite a redefinição de senha."
                _registrar_tentativa_falha(ip, email_informado)
            else:
                current_app.logger.info(
                    "Login de transição realizado para o usuário %s (%s) a partir do IP %s",
                    usuario.nome,
                    usuario.email,
                    ip,
                )
                _limpar_tentativas(ip, email_informado)
                session.clear()
                session["usuario_id"] = usuario.id
                flash("Bem-vindo(a)! Você ainda não cadastrou uma senha individual. Por favor, defina sua senha abaixo.", "alerta")
                return redirect(url_for("auth.trocar_senha"))
        else:
            erro = "E-mail ou senha incorretos."
            _registrar_tentativa_falha(ip, email_informado)

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
        elif len(nova_senha) < 10:
            erro = "A nova senha deve ter pelo menos 10 caracteres."
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
