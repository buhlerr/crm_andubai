import os
import uuid

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from app.extensions import db
from app.importacao import ErroImportacao, checklist, comum
from app.importacao.rotulos import DETALHES, RESUMO_BASE, RESUMO_CHECKLIST
from app.importacao.valores import para_data
from app.models import Gravidade, Importacao, SituacaoImportacao, TipoImportacao
from app.web.auth import admin_obrigatorio, login_obrigatorio

bp = Blueprint("importacoes", __name__, url_prefix="/importacoes")

TIPOS = {
    TipoImportacao.CHECKLIST: {
        "nome": "Relatório de checklist do TM (CSV)",
        "descricao": "Única importação do sistema: procedimentos finalizados e em aberto. Cria e atualiza alunos, "
                     "programas e tarefas, e atualiza o painel RSA - Checklist do Suporte.",
        "extensoes": (".csv",),
        "modulo": checklist,
        "rotulos": RESUMO_CHECKLIST,
    },
}
# Importações antigas da planilha semanal continuam aparecendo no histórico (só para ver ou descartar).
NOMES_ANTIGOS = {TipoImportacao.BASE_ALUNOS: {"nome": "Base de alunos (planilha semanal, não é mais usada)",
                                              "rotulos": RESUMO_BASE}}


TODOS_OS_TIPOS = {**NOMES_ANTIGOS, **TIPOS}


def _importacao(importacao_id: int) -> Importacao:
    return db.session.get(Importacao, importacao_id) or abort(404, "Importação não encontrada.")


@bp.route("/")
@login_obrigatorio
def lista():
    importacoes = db.session.execute(db.select(Importacao).order_by(Importacao.iniciada_em.desc()).limit(50)).scalars().all()
    return render_template("importacoes/lista.html", importacoes=importacoes, TIPOS=TODOS_OS_TIPOS)


@bp.route("/nova", methods=["GET", "POST"])
@admin_obrigatorio
def nova():
    if request.method == "GET":
        return render_template("importacoes/nova.html", TIPOS=TIPOS, form={})

    form = request.form
    try:
        tipo = TipoImportacao(form.get("tipo") or TipoImportacao.CHECKLIST.value)
        if tipo not in TIPOS:
            raise ValueError
    except ValueError:
        flash("Escolha o tipo de arquivo.", "erro")
        return render_template("importacoes/nova.html", TIPOS=TIPOS, form=form), 400
    arquivo = request.files.get("arquivo")
    nome = os.path.basename(arquivo.filename) if arquivo and arquivo.filename else ""
    extensao = os.path.splitext(nome)[1].lower()
    if not nome:
        flash("Escolha o arquivo.", "erro")
        return render_template("importacoes/nova.html", TIPOS=TIPOS, form=form), 400
    if extensao not in TIPOS[tipo]["extensoes"]:
        flash(f"Para \"{TIPOS[tipo]['nome']}\" o arquivo precisa ser {' ou '.join(TIPOS[tipo]['extensoes'])}.", "erro")
        return render_template("importacoes/nova.html", TIPOS=TIPOS, form=form), 400

    periodo = {}
    if tipo == TipoImportacao.CHECKLIST:
        try:
            periodo = {
                "periodo_inicio": para_data(form.get("periodo_inicio") or None),
                "periodo_fim": para_data(form.get("periodo_fim") or None),
                "periodo_completo": bool(form.get("periodo_completo")),
            }
        except ValueError:
            flash("Data do período inválida. Use dd/mm/aaaa.", "erro")
            return render_template("importacoes/nova.html", TIPOS=TIPOS, form=form), 400

    # O arquivo fica em disco só durante a leitura (o Excel precisa de um caminho).
    pasta = os.path.join(current_app.instance_path, "envios")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, f"{uuid.uuid4().hex}{extensao}")
    arquivo.save(caminho)
    try:
        importacao = TIPOS[tipo]["modulo"].importar_arquivo(caminho, usuario_id=g.usuario.id, **periodo)
    except ErroImportacao as erro:
        flash(str(erro), "erro")
        return render_template("importacoes/nova.html", TIPOS=TIPOS, form=form), 400
    finally:
        os.remove(caminho)
    importacao.arquivo_nome = nome
    db.session.commit()
    return redirect(url_for("importacoes.detalhe", importacao_id=importacao.id))


@bp.route("/<int:importacao_id>")
@login_obrigatorio
def detalhe(importacao_id):
    importacao = _importacao(importacao_id)
    ocorrencias = sorted(importacao.ocorrencias, key=lambda o: (o.gravidade != Gravidade.ERRO, o.linha or 0))
    fora_do_periodo = []
    ultima = checklist.ultima_importacao_confirmada()
    if ultima is not None and ultima.id == importacao.id:
        fora_do_periodo = checklist.tarefas_fora_do_periodo(importacao)
    # Só vem marcado para encerrar o que ficou para trás (prazo antes do período). O que tem prazo depois do
    # fim do período só não veio porque a exportação terminava antes: em geral continua pendente.
    inicio = importacao.periodo_inicio
    marcar = {t.id: bool(t.prazo_egali and inicio and t.prazo_egali < inicio) for t in fora_do_periodo}
    return render_template(
        "importacoes/detalhe.html",
        importacao=importacao,
        tipo=TODOS_OS_TIPOS[importacao.tipo],
        ocorrencias=ocorrencias,
        fora_do_periodo=fora_do_periodo,
        marcar=marcar,
        DETALHES=DETALHES,
        Gravidade=Gravidade,
        SituacaoImportacao=SituacaoImportacao,
    )


@bp.route("/<int:importacao_id>/encerrar-fora-do-periodo", methods=["POST"])
@admin_obrigatorio
def encerrar_fora_do_periodo(importacao_id):
    importacao = _importacao(importacao_id)
    ids = {int(v) for v in request.form.getlist("tarefa") if v.isdigit()}
    if not ids:
        flash("Marque pelo menos uma tarefa.", "erro")
    else:
        try:
            encerradas = checklist.encerrar_a_mao(importacao, ids, g.usuario)
        except ErroImportacao as erro:
            flash(str(erro), "erro")
        else:
            flash(f"{encerradas} tarefa(s) encerrada(s). Se algum item voltar ao checklist da Egali, a tarefa é reaberta.", "ok")
    return redirect(url_for("importacoes.detalhe", importacao_id=importacao_id))


@bp.route("/<int:importacao_id>/confirmar", methods=["POST"])
@admin_obrigatorio
def confirmar(importacao_id):
    importacao = _importacao(importacao_id)
    try:
        if importacao.tipo not in TIPOS:
            raise ErroImportacao("A planilha semanal não é mais importada. Descarte esta prévia e importe o relatório de checklist.")
        TIPOS[importacao.tipo]["modulo"].confirmar(importacao)
    except ErroImportacao as erro:
        flash(str(erro), "erro")
    else:
        flash("Importação gravada.", "ok")
    return redirect(url_for("importacoes.detalhe", importacao_id=importacao_id))


@bp.route("/<int:importacao_id>/descartar", methods=["POST"])
@admin_obrigatorio
def descartar(importacao_id):
    importacao = _importacao(importacao_id)
    try:
        comum.descartar(importacao)
    except ErroImportacao as erro:
        flash(str(erro), "erro")
    else:
        flash("Importação descartada. Nada foi alterado.", "ok")
    return redirect(url_for("importacoes.detalhe", importacao_id=importacao_id))
