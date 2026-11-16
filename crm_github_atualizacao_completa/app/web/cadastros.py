from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.catalogo_inicial import ORIENTACOES_NEG
from app.extensions import db
from app.importacao.consultores import TEXTOS_SEM_CONSULTOR
from app.importacao.pautas import normalizar_nome
from app.models import (
    Aluno,
    ApelidoConsultor,
    CategoriaServico,
    ColaboradorSetor,
    ConsultorTeen,
    EtapaModelo,
    Papel,
    Pauta,
    Programa,
    ServicoEgali,
    SituacaoPrograma,
    Trilha,
    Usuario,
)
from app.texto import normalizar_texto
from app.web.auth import admin_obrigatorio, login_obrigatorio

bp = Blueprint("cadastros", __name__, url_prefix="/cadastros")

ROTULOS_PAPEL = {Papel.CONSULTOR: "Consultor(a)", Papel.ESTAGIARIO: "Estagiário(a)", Papel.ADMIN: "Administrador(a)"}
ROTULOS_CATEGORIA = {
    CategoriaServico.CURSO: "Curso",
    CategoriaServico.VISTO: "Visto (pode vir sozinho)",
    CategoriaServico.AVULSO: "Avulso (vai junto de um programa)",
    CategoriaServico.IGNORADO: "Ignorado (a importação pula)",
    CategoriaServico.NAO_CLASSIFICADO: "Não classificado",
}


@bp.app_context_processor
def rotulos():
    return {"ROTULOS_PAPEL": ROTULOS_PAPEL, "ROTULOS_CATEGORIA": ROTULOS_CATEGORIA, "Papel": Papel}


def _usuarios_ativos():
    return db.session.execute(db.select(Usuario).filter_by(ativo=True).order_by(Usuario.nome)).scalars().all()


# ---------------------------------------------------------------- usuários


@bp.route("/usuarios", methods=["GET", "POST"])
@admin_obrigatorio
def usuarios():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        papel = request.form.get("papel", Papel.CONSULTOR.value)
        senha = request.form.get("senha", "").strip()
        if not nome or "@" not in email or papel not in {p.value for p in Papel}:
            flash("Preencha nome, e-mail e papel.", "erro")
        elif senha and len(senha) < 10:
            flash("A senha deve ter no mínimo 10 caracteres.", "erro")
        else:
            novo_usuario = Usuario(nome=nome, email=email, papel=Papel(papel))
            if senha:
                novo_usuario.definir_senha(senha)
            db.session.add(novo_usuario)
            try:
                db.session.commit()
                flash(f"{nome} cadastrado(a) com sucesso.", "ok")
                return redirect(url_for("cadastros.usuarios"))
            except IntegrityError:
                db.session.rollback()
                flash("Já existe um usuário com esse e-mail.", "erro")
    lista = db.session.execute(db.select(Usuario).order_by(Usuario.ativo.desc(), Usuario.nome)).scalars().all()
    return render_template("cadastros/usuarios.html", usuarios=lista)


@bp.route("/usuarios/<int:usuario_id>", methods=["GET", "POST"])
@admin_obrigatorio
def editar_usuario(usuario_id):
    usuario = db.session.get(Usuario, usuario_id) or abort(404)
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        papel = request.form.get("papel", "")
        ativo = bool(request.form.get("ativo"))
        nova_senha = request.form.get("nova_senha", "").strip()
        if not nome or "@" not in email or papel not in {p.value for p in Papel}:
            flash("Preencha nome, e-mail e papel.", "erro")
        elif usuario.id == g.usuario.id and (not ativo or papel != Papel.ADMIN.value):
            flash("Você não pode tirar o seu próprio acesso de administrador.", "erro")
        elif nova_senha and len(nova_senha) < 10:
            flash("A nova senha deve ter no mínimo 10 caracteres.", "erro")
        else:
            usuario.nome, usuario.email, usuario.papel, usuario.ativo = nome, email, Papel(papel), ativo
            if nova_senha:
                usuario.definir_senha(nova_senha)
            try:
                db.session.commit()
                flash("Usuário atualizado com sucesso.", "ok")
                return redirect(url_for("cadastros.usuarios"))
            except IntegrityError:
                db.session.rollback()
                flash("Já existe um usuário com esse e-mail.", "erro")
    return render_template("cadastros/usuario.html", usuario=usuario)


# ---------------------------------------------------------------- exceções de nome do consultor


@bp.route("/apelidos", methods=["GET", "POST"])
@admin_obrigatorio
def apelidos():
    if request.method == "POST":
        texto = request.form.get("texto", "").strip()
        valor = request.form.get("usuario_id", "")
        usuario = db.session.get(Usuario, int(valor)) if valor.isdigit() else None
        if not texto:
            flash("Escreva o nome como aparece na planilha.", "erro")
        elif valor and usuario is None:
            flash("Usuário inválido.", "erro")
        else:
            db.session.add(ApelidoConsultor(
                texto_planilha=texto, texto_normalizado=normalizar_texto(texto), usuario=usuario, criado_por_id=g.usuario.id
            ))
            try:
                db.session.commit()
                flash(f"\"{texto}\" agora aponta para {usuario.nome if usuario else 'ninguém (sem consultor)'}. "
                      "Vale a partir da próxima importação do checklist.", "ok")
                return redirect(url_for("cadastros.apelidos"))
            except IntegrityError:
                db.session.rollback()
                flash("Esse nome já tem uma exceção cadastrada. Remova a antiga antes.", "erro")

    lista = db.session.execute(db.select(ApelidoConsultor).order_by(ApelidoConsultor.texto_planilha)).scalars().all()
    # Nomes da planilha que não bateram com ninguém: sugestões para cadastrar.
    ja_tem = {a.texto_normalizado for a in lista}
    sem_usuario = db.session.execute(
        db.select(Programa.consultor_texto, db.func.count())
        .where(Programa.consultor_id.is_(None), Programa.consultor_texto.is_not(None), Programa.situacao == SituacaoPrograma.ATIVO)
        .group_by(Programa.consultor_texto).order_by(db.func.count().desc())
    ).all()
    pendentes = [
        (texto, n) for texto, n in sem_usuario
        if normalizar_texto(texto) not in TEXTOS_SEM_CONSULTOR and normalizar_texto(texto) not in ja_tem
    ]
    return render_template("cadastros/apelidos.html", apelidos=lista, pendentes=pendentes, usuarios=_usuarios_ativos())


@bp.route("/apelidos/<int:apelido_id>/remover", methods=["POST"])
@admin_obrigatorio
def remover_apelido(apelido_id):
    apelido = db.session.get(ApelidoConsultor, apelido_id) or abort(404)
    db.session.delete(apelido)
    db.session.commit()
    flash(f"Exceção \"{apelido.texto_planilha}\" removida.", "ok")
    return redirect(url_for("cadastros.apelidos"))


# ---------------------------------------------------------------- serviços


@bp.route("/servicos", methods=["GET", "POST"])
@admin_obrigatorio
def servicos():
    lista = db.session.execute(db.select(ServicoEgali).order_by(ServicoEgali.nome)).scalars().all()
    if request.method == "POST":
        mudou = 0
        for servico in lista:
            valor = request.form.get(f"categoria_{servico.id}")
            if valor in {c.value for c in CategoriaServico} and servico.categoria != valor:
                servico.categoria = CategoriaServico(valor)
                mudou += 1
        db.session.commit()
        flash(f"{mudou} serviço(s) atualizado(s). Vale a partir da próxima importação do checklist.", "ok")
        return redirect(url_for("cadastros.servicos"))
    return render_template("cadastros/servicos.html", servicos=lista, CategoriaServico=CategoriaServico)


# ---------------------------------------------------------------- público teen


@bp.route("/publico-teen", methods=["GET", "POST"])
@admin_obrigatorio
def publico_teen():
    from app import publico_teen as regra

    servicos = db.session.execute(db.select(ServicoEgali).order_by(ServicoEgali.nome)).scalars().all()
    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "servicos":
            marcados = {int(v) for v in request.form.getlist("servico") if v.isdigit()}
            for s in servicos:
                s.teen = s.id in marcados
            flash("Serviços do público teen salvos.", "ok")
        elif acao == "adicionar_consultor":
            nome = request.form.get("nome", "").strip()
            if nome and not db.session.execute(
                db.select(ConsultorTeen).filter_by(nome_normalizado=normalizar_texto(nome))
            ).scalar_one_or_none():
                db.session.add(ConsultorTeen(nome=nome, nome_normalizado=normalizar_texto(nome)))
                flash(f"{nome} incluído(a) como consultor(a) da equipe teen.", "ok")
            elif nome:
                flash("Esse nome já está na lista.", "erro")
        elif acao == "remover_consultor":
            consultor = db.session.get(ConsultorTeen, request.form.get("id", type=int) or 0)
            if consultor:
                db.session.delete(consultor)
                flash(f"{consultor.nome} removido(a) da lista.", "ok")
        db.session.flush()
        total = regra.recalcular()
        db.session.commit()
        flash(f"Marcação refeita: {total} aluno(s) do público teen.", "ok")
        return redirect(url_for("cadastros.publico_teen"))

    consultores = db.session.execute(db.select(ConsultorTeen).order_by(ConsultorTeen.nome)).scalars().all()
    total = db.session.execute(db.select(db.func.count()).select_from(Aluno).filter_by(teen=True)).scalar_one()
    motivos = db.session.execute(
        db.select(Aluno.teen_motivo, db.func.count()).filter_by(teen=True).group_by(Aluno.teen_motivo).order_by(db.func.count().desc()).limit(15)
    ).all()
    # Nomes de consultor que aparecem nos programas: facilitam escolher quem é da equipe teen.
    nomes_programas = db.session.execute(
        db.select(Programa.consultor_texto).where(Programa.consultor_texto.is_not(None)).distinct().order_by(Programa.consultor_texto)
    ).scalars().all()
    return render_template(
        "cadastros/publico_teen.html", servicos=servicos, consultores=consultores, total=total, motivos=motivos,
        nomes_programas=nomes_programas, tag=regra.TAG_TEEN,
    )


# ---------------------------------------------------------------- catálogo


@bp.route("/catalogo", methods=["GET", "POST"])
@admin_obrigatorio
def catalogo():
    trilhas = db.session.execute(db.select(Trilha).order_by(Trilha.ordem)).scalars().all()
    if request.method == "POST":
        for trilha in trilhas:
            nome = request.form.get(f"nome_{trilha.id}", "").strip()
            if nome:
                trilha.nome = nome
        db.session.commit()
        flash("Nomes das trilhas salvos.", "ok")
        return redirect(url_for("cadastros.catalogo"))
    return render_template("cadastros/catalogo.html", trilhas=trilhas)


CAMPOS_ETAPA = ("regra_prazo", "o_que_e", "importancia", "quando_cabe_neg", "link_gravacao")


@bp.route("/etapas/<int:etapa_id>", methods=["GET", "POST"])
@admin_obrigatorio
def editar_etapa(etapa_id):
    etapa = db.session.get(EtapaModelo, etapa_id) or abort(404)
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("O nome não pode ficar vazio.", "erro")
        else:
            etapa.nome = nome
            etapa.ordem = request.form.get("ordem", etapa.ordem, type=int)
            etapa.ativa = bool(request.form.get("ativa"))
            for campo in CAMPOS_ETAPA:
                setattr(etapa, campo, request.form.get(campo, "").strip() or None)
            etapa.criada_automaticamente = False  # alguém revisou
            try:
                db.session.commit()
                flash("Etapa salva.", "ok")
                return redirect(url_for("cadastros.catalogo"))
            except IntegrityError:
                db.session.rollback()
                flash("Já existe outra etapa com esse nome nesta trilha.", "erro")
    return render_template("cadastros/etapa.html", etapa=etapa)


# ---------------------------------------------------------------- pautas e setores


@bp.route("/pautas", methods=["GET", "POST"])
@admin_obrigatorio
def pautas():
    if request.method == "POST":
        acao = request.form.get("acao", "adicionar")
        if acao == "adicionar":
            nome = request.form.get("nome", "").strip()
            setor = request.form.get("setor", "").strip()
            if not nome or not setor:
                flash("Preencha o nome do colaborador e o setor.", "erro")
            else:
                norm = normalizar_nome(nome)
                existente = db.session.execute(
                    db.select(ColaboradorSetor).filter_by(nome_normalizado=norm)
                ).scalar_one_or_none()
                if existente:
                    existente.setor = setor
                    existente.nome = nome
                    flash(f"Setor de {nome} atualizado para '{setor}'.", "ok")
                else:
                    db.session.add(ColaboradorSetor(nome=nome, nome_normalizado=norm, setor=setor))
                    flash(f"{nome} cadastrado(a) no setor '{setor}'.", "ok")
                db.session.commit()
                return redirect(url_for("cadastros.pautas"))

        elif acao == "remover":
            cid = request.form.get("id", type=int)
            colab = db.session.get(ColaboradorSetor, cid) if cid else None
            if colab:
                db.session.delete(colab)
                db.session.commit()
                flash(f"Mapeamento de {colab.nome} removido.", "ok")
                return redirect(url_for("cadastros.pautas"))

    mapeados = db.session.execute(
        db.select(ColaboradorSetor).order_by(ColaboradorSetor.setor, ColaboradorSetor.nome)
    ).scalars().all()

    nomes_mapeados = {c.nome_normalizado for c in mapeados}
    usuarios_un = {normalizar_nome(u.nome) for u in _usuarios_ativos()}

    contagem_nomes = {}
    try:
        pautas_db = db.session.execute(
            db.select(Pauta.responsavel_tm, Pauta.criado_por_tm, Pauta.atualizado_por_tm)
        ).all()
        for r, c, a in pautas_db:
            for n in [r, c, a]:
                if n and n != "Sem responsável" and normalizar_nome(n) not in usuarios_un and normalizar_nome(n) not in nomes_mapeados:
                    contagem_nomes[n] = contagem_nomes.get(n, 0) + 1
    except Exception:
        pass

    sugestoes = sorted(contagem_nomes.items(), key=lambda x: -x[1])
    setores_padrao = [
        "Financeiro",
        "Vistos",
        "Matrículas",
        "Suporte ao Aluno",
        "Comercial",
        "Diretoria",
        "Acomodação",
        "Passagens",
    ]

    return render_template(
        "cadastros/pautas.html",
        mapeados=mapeados,
        sugestoes=sugestoes,
        setores_padrao=setores_padrao,
    )


# ---------------------------------------------------------------- ajuda


@bp.route("/ajuda-neg")
@login_obrigatorio
def ajuda_neg():
    return render_template("ajuda_neg.html", orientacoes=ORIENTACOES_NEG)
