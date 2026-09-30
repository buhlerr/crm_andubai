import io
import os

from flask import Blueprint, flash, g, redirect, render_template, request, send_file, url_for

from app import painel_veg
from app.web.auth import admin_obrigatorio, login_obrigatorio

bp = Blueprint("painel", __name__, url_prefix="/painel-veg")


@bp.route("/")
@login_obrigatorio
def inicio():
    guardado = painel_veg.base_guardada()
    return render_template("painel/inicio.html", info=guardado[1] if guardado else None,
                           TITULO_GRUPO=painel_veg.TITULO_GRUPO)


@bp.route("/enviar", methods=["POST"])
@admin_obrigatorio
def enviar():
    arquivo = request.files.get("arquivo")
    nome = os.path.basename(arquivo.filename) if arquivo and arquivo.filename else ""
    if not nome:
        flash("Escolha o arquivo HTML do painel.", "erro")
    elif os.path.splitext(nome)[1].lower() not in (".html", ".htm"):
        flash("O painel precisa ser o arquivo .html baixado dele mesmo (botão \"Baixar HTML\").", "erro")
    else:
        try:
            painel_veg.guardar_base(arquivo.read(), nome, g.usuario.nome)
        except painel_veg.ErroPainel as erro:
            flash(str(erro), "erro")
        else:
            flash("Painel guardado. A partir de agora o download já sai com o grupo do backlog.", "ok")
    return redirect(url_for("painel.inicio"))


@bp.route("/baixar")
@login_obrigatorio
def baixar():
    guardado = painel_veg.base_guardada()
    if guardado is None:
        flash("Ainda não há painel guardado. Peça para um administrador enviar o HTML do painel.", "erro")
        return redirect(url_for("painel.inicio"))
    base, _ = guardado
    try:
        html = painel_veg.encaixar_grupo(base, painel_veg.dados_backlog())
    except painel_veg.ErroPainel as erro:
        flash(str(erro), "erro")
        return redirect(url_for("painel.inicio"))
    # Sempre como anexo: o painel é aberto no computador de quem baixou, nunca dentro deste sistema.
    resposta = send_file(io.BytesIO(html.encode("utf-8")), mimetype="text/html", as_attachment=True,
                         download_name=painel_veg.nome_do_arquivo(base))
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta
