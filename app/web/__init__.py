import secrets
from datetime import date, timedelta

from flask import Flask, abort, render_template, request, session

from app.models import ROTULOS_STATUS, StatusTarefa
from app.models.base import hora_local
from app.texto import separar_neg


def token_csrf() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def registrar_web(app: Flask) -> None:
    from app.web import auth, cadastros, filas, importacoes, painel, pautas, programas, tarefas

    for modulo in (auth, filas, tarefas, programas, importacoes, painel, cadastros, pautas):
        app.register_blueprint(modulo.bp)

    @app.before_request
    def verificar_csrf():
        if request.method == "POST" and not app.config.get("CSRF_DESLIGADO"):
            enviado = request.form.get("csrf", "")
            if not enviado or not secrets.compare_digest(enviado, session.get("csrf", "")):
                abort(400, "O formulário expirou. Volte, recarregue a página e tente de novo.")

    @app.template_filter("data")
    def formatar_data(valor):
        return valor.strftime("%d/%m/%Y") if valor else "—"

    @app.template_filter("data_hora")
    def formatar_data_hora(valor):
        return hora_local(valor).strftime("%d/%m/%Y %H:%M") if valor else "—"

    @app.template_filter("status")
    def rotulo_status(valor):
        return ROTULOS_STATUS.get(StatusTarefa(valor), valor) if valor else "—"

    app.add_template_filter(separar_neg, "separar_neg")

    @app.context_processor
    def dados_do_topo():
        """Topo e barra lateral: últimas importações, tamanho da minha fila, prévias pendentes."""
        from flask import g

        if not getattr(g, "usuario", None):
            return {}
        from app import consultas
        from app.extensions import db
        from app.models import Importacao, SituacaoImportacao, TipoImportacao

        def ultima(tipo):
            return db.session.execute(
                db.select(Importacao.concluida_em)
                .filter_by(tipo=tipo, situacao=SituacaoImportacao.CONFIRMADA)
                .order_by(Importacao.concluida_em.desc())
            ).scalars().first()

        return {
            "topo_planilha": ultima(TipoImportacao.BASE_ALUNOS),
            "topo_checklist": ultima(TipoImportacao.CHECKLIST),
            "topo_minha_fila": consultas.contar(consultas.Filtros(responsavel=g.usuario.id)),
            "topo_previas": db.session.execute(
                db.select(db.func.count()).select_from(Importacao).filter_by(situacao=SituacaoImportacao.PREVIA)
            ).scalar_one(),
        }

    app.jinja_env.globals.update(
        token_csrf=token_csrf,
        ROTULOS_STATUS=ROTULOS_STATUS,
        StatusTarefa=StatusTarefa,
        hoje=date.today,
        timedelta=timedelta,
    )

    def pagina_de_erro(erro, codigo, titulo):
        # Só mostra a descrição quando é nossa (em português), não a padrão do Werkzeug.
        descricao = getattr(erro, "description", "")
        mensagem = descricao if descricao != getattr(type(erro), "description", None) else ""
        return render_template("erro.html", titulo=titulo, mensagem=mensagem), codigo

    for codigo, titulo in ((400, "Pedido inválido"), (403, "Sem permissão"), (404, "Página não encontrada"),
                           (413, "Arquivo grande demais")):
        app.register_error_handler(codigo, lambda erro, codigo=codigo, titulo=titulo: pagina_de_erro(erro, codigo, titulo))
