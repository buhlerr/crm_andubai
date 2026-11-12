import os

from flask import Blueprint, abort, flash, g, make_response, redirect, render_template, request, url_for

from app import rsa
from app.importacao.rsa_checklist import base_guardada
from app.models import Papel
from app.web.auth import admin_obrigatorio, login_obrigatorio

bp = Blueprint("rsa", __name__, url_prefix="/rsa")


@bp.app_context_processor
def paginas_do_menu():
    return {"RSA_PAGINAS_DADOS": rsa.PAGINAS_DADOS, "RSA_PAGINAS_SISTEMA": rsa.PAGINAS_SISTEMA}


def _pagina_permitida(pagina: str) -> str:
    if pagina not in rsa.PAGINAS:
        abort(404)
    if pagina in rsa.PAGINAS_SISTEMA and g.usuario.papel != Papel.ADMIN:
        abort(403, "Esta página é só para administradores.")
    return pagina


@bp.route("/")
@login_obrigatorio
def inicio():
    return redirect(url_for("rsa.pagina", pagina="visao"))


@bp.route("/<pagina>")
@login_obrigatorio
def pagina(pagina):
    _pagina_permitida(pagina)
    base = base_guardada()
    html = rsa.html_guardado() if base else None
    return render_template("rsa/pagina.html", pagina=pagina, rotulo=rsa.PAGINAS[pagina],
                           sistema=pagina in rsa.PAGINAS_SISTEMA, info=rsa.info_guardada(),
                           base=(base or {}).get("meta"),
                           sem_base=rsa.AVISO_SEM_BASE if html is not None and not rsa.aceita_base(html) else None)


@bp.route("/<pagina>/app")
@login_obrigatorio
def app_html(pagina):
    """O HTML do app, aberto na página pedida. Só pode ser mostrado dentro do próprio CRM (iframe)."""
    _pagina_permitida(pagina)
    html = rsa.html_guardado()
    if html is None:
        abort(404, "Ainda não há HTML do RSA guardado.")
    html = rsa.encaixar(html, pagina, g.usuario.nome, g.usuario.papel == Papel.ADMIN, base=base_guardada())
    resposta = make_response(html)
    resposta.headers["Content-Type"] = "text/html; charset=utf-8"
    resposta.headers["X-Frame-Options"] = "SAMEORIGIN"
    resposta.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@bp.route("/enviar", methods=["POST"])
@admin_obrigatorio
def enviar():
    arquivo = request.files.get("arquivo")
    nome = os.path.basename(arquivo.filename) if arquivo and arquivo.filename else ""
    voltar = request.form.get("pagina", "visao")
    if voltar not in rsa.PAGINAS:
        voltar = "visao"
    if not nome:
        flash("Escolha o arquivo HTML do RSA.", "erro")
    elif os.path.splitext(nome)[1].lower() not in (".html", ".htm"):
        flash("O RSA precisa ser o arquivo .html do app (APP_Checklist_Suporte_ao_Aluno.html).", "erro")
    else:
        try:
            rsa.guardar(arquivo.read(), nome, g.usuario.nome)
        except rsa.ErroRSA as erro:
            flash(str(erro), "erro")
        else:
            flash("HTML do RSA guardado. As páginas já mostram a versão nova.", "ok")
            html = rsa.html_guardado()
            if base_guardada() and html is not None and not rsa.aceita_base(html):
                flash(rsa.AVISO_SEM_BASE, "alerta")
    return redirect(url_for("rsa.pagina", pagina=voltar))
