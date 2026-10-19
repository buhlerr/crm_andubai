import json
import os
from datetime import date
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from app.extensions import db
from app.importacao.pautas import (
    carregar_pautas,
    extrair_linhas_csv,
    extrair_linhas_mhtml,
    membros_padrao,
    normalizar_nome,
    obter_membros_unidade,
    processar_linhas_para_pautas,
    sincronizar_pautas_no_banco,
)
from app.models.base import agora
from app.models.cadastro import Usuario
from app.models.pautas import Pauta, PautaAnotacao
from app.web.auth import admin_obrigatorio, login_obrigatorio

bp = Blueprint("pautas", __name__, url_prefix="/pautas")


def _caminho_arquivo_pautas() -> str:
    """Último arquivo de pautas enviado pela tela (fica só na pasta de dados, nunca no código)."""
    for nome in ("pautas_recente.csv", "pautas_recente.mhtml", "pautas_recente.html", "pautas_recente.htm"):
        caminho = os.path.join(current_app.instance_path, nome)
        if os.path.exists(caminho):
            return os.path.abspath(caminho)
    return ""


def _obter_pautas_gerais(data_ref: date | None = None) -> list[dict]:
    """Obtém as pautas do banco de dados (se houver) ou carrega do arquivo mais recente."""
    if data_ref is None:
        data_ref = date.today()

    # 1. Verifica se já existem pautas gravadas no banco
    pautas_db = db.session.execute(
        db.select(Pauta).order_by(
            Pauta.ativa.desc(),
            Pauta.quebra_72h_unidade.desc(),
            Pauta.atualizada_un.asc(),
            Pauta.tempo_inativo_horas.desc(),
        )
    ).scalars().all()

    if pautas_db:
        resultado = []
        for p in pautas_db:
            dias_num = (p.tempo_inativo_horas // 24) if p.tempo_inativo_horas else 0
            item = {
                "ID": str(p.id),
                "Categoria": p.categoria,
                "Categoria Limpa": p.categoria_limpa,
                "Pauta": p.pauta_titulo,
                "Aluno": p.aluno,
                "Status": p.status_tm,
                "Responsável": p.responsavel_tm,
                "Criada por": p.criado_por_tm,
                "Criada em": p.criado_em_tm.strftime("%d/%m/%Y") if p.criado_em_tm else "",
                "Atualizado por": p.atualizado_por_tm,
                "Atualizado em": p.atualizado_em_tm.strftime("%d/%m/%Y") if p.atualizado_em_tm else "",
                "TAG": p.tag or "",
                "Tempo Inativo": p.tempo_inativo_texto or "",
                "Horas Inativo": p.tempo_inativo_horas or 0,
                "SLA": p.prazo_sla_horas,
                "Dias": str(dias_num),
                "Atualizada?": "TRUE" if p.atualizada_un else "FALSE",
                "UN Atualizou": p.un_atualizou if p.atualizada_un else "",
                "UN Responsável": p.un_responsavel or "",
                "UN Criou": p.un_criou or "",
                "UN Final": p.un_final or "",
                "Quebra UN": p.quebra_72h_unidade,
                "Quebra Outro": p.quebra_72h_outro,
                "Observacao": p.observacao or "",
                "Observacao em": p.observacao_atualizada_em.strftime("%d/%m/%Y %H:%M") if p.observacao_atualizada_em else "",
                "Subestado": p.subestado_aguardando,
                "Ativa": p.ativa,
                "_consultor": p.consultor.nome if p.consultor else "Outros",
                "_consultor_id": p.consultor_id,
                "_objeto": p,
            }
            resultado.append(item)
        return resultado

    # 2. Se o banco estiver vazio, carrega do arquivo existente e popula o banco
    caminho = _caminho_arquivo_pautas()
    if caminho and os.path.exists(caminho):
        linhas = carregar_pautas(caminho, data_referencia=data_ref)
        if linhas:
            try:
                sincronizar_pautas_no_banco(linhas, arquivo_origem=os.path.basename(caminho))
                # Recarrega a partir do banco para obter os IDs e instâncias persistidas
                return _obter_pautas_gerais(data_ref)
            except Exception:
                db.session.rollback()
        return linhas

    return []


@bp.route("/")
@login_obrigatorio
def lista():
    membros_map = obter_membros_unidade()
    membros = [u.nome for u in membros_map.values() if u] or membros_padrao()

    todas_pautas = _obter_pautas_gerais()

    # Filtros da URL
    visao = request.args.get("visao", "etapas")  # etapas | tabela
    consultor_selecionado = request.args.get("consultor", "")
    pendencia = request.args.get("pendencia", "todas")  # todas | aguardando_un | respondidas_un
    status_filtro = request.args.get("status", "")
    busca = request.args.get("busca", "").strip().lower()

    statuses_disponiveis = sorted({p["Status"] for p in todas_pautas if p.get("Status")})

    # Filtro base por consultor
    pautas_base_consultor = todas_pautas
    if consultor_selecionado and consultor_selecionado != "todos":
        c_norm = normalizar_nome(consultor_selecionado)
        pautas_base_consultor = [
            p for p in todas_pautas
            if c_norm == normalizar_nome(p.get("Responsável"))
            or c_norm == normalizar_nome(p.get("Criada por"))
            or c_norm in normalizar_nome(p.get("Pauta"))
            or p.get("_consultor") == consultor_selecionado
        ]

    # Contadores gerais
    total_pautas = len(pautas_base_consultor)
    total_aguardando_un = sum(1 for p in pautas_base_consultor if p.get("Atualizada?") == "FALSE")
    total_respondidas_un = sum(1 for p in pautas_base_consultor if p.get("Atualizada?") == "TRUE")
    total_atrasadas = sum(1 for p in pautas_base_consultor if p.get("TAG"))
    quebras_unidade = sum(1 for p in pautas_base_consultor if p.get("Quebra UN"))
    quebras_outro = sum(1 for p in pautas_base_consultor if p.get("Quebra Outro"))

    # Aplica os filtros
    pautas_filtradas = []
    for p in pautas_base_consultor:
        if pendencia == "aguardando_un" and p.get("Atualizada?") != "FALSE":
            continue
        if pendencia == "respondidas_un" and p.get("Atualizada?") != "TRUE":
            continue
        if status_filtro and p.get("Status") != status_filtro:
            continue
        if busca:
            texto_busca = f"{p.get('ID')} {p.get('Aluno')} {p.get('Pauta')} {p.get('Categoria')} {p.get('Responsável')} {p.get('Observacao')}".lower()
            if busca not in texto_busca:
                continue
        pautas_filtradas.append(p)

    # Ordenação por prioridade: Quebra UN > Não Respondida > Mais horas inativo
    def criterio_ordem(p):
        quebra = 0 if p.get("Quebra UN") else 1
        nao_atualizada = 0 if p.get("Atualizada?") == "FALSE" else 1
        horas = p.get("Horas Inativo") or 0
        return (quebra, nao_atualizada, -horas)

    pautas_filtradas.sort(key=criterio_ordem)

    # Agrupamento para a visualização em Pipeline / Etapas
    etapas = {
        "nossa_acao": [],               # 🚨 Prioridade: UN Resp == AN e Dubai e Atualizada? == FALSE
        "nosso_aluno": [],              # ⏳ UN Resp == AN e Dubai e Atualizada? == TRUE (Aguardando Aluno)
        "outro_setor": [],              # 🏢 Acompanhando Matriz/Outro Setor
        "aguardando_finalizacao": [],   # 🏁 Solucionado pelo setor, pendente de conferência
        "finalizadas": [],              # ✅ Concluídas / Histórico
    }

    for p in pautas_filtradas:
        status_l = (p.get("Status") or "").lower()
        ativa = p.get("Ativa", True)

        if not ativa or "finalizad" in status_l or "cancelad" in status_l:
            etapas["finalizadas"].append(p)
        elif "finaliza" in status_l:
            etapas["aguardando_finalizacao"].append(p)
        elif p.get("UN Responsável") == "AN e Dubai":
            if p.get("Atualizada?") == "FALSE":
                etapas["nossa_acao"].append(p)
            else:
                etapas["nosso_aluno"].append(p)
        else:
            etapas["outro_setor"].append(p)

    # Contagem de pautas por membro para badges nas abas
    contagem_membros = {}
    for m in membros:
        m_n = normalizar_nome(m)
        contagem_membros[m] = sum(
            1 for p in todas_pautas
            if m_n == normalizar_nome(p.get("Responsável"))
            or m_n == normalizar_nome(p.get("Criada por"))
            or m_n in normalizar_nome(p.get("Pauta"))
            or p.get("_consultor") == m
        )

    arquivo_atual = _caminho_arquivo_pautas()
    data_arquivo = None
    if arquivo_atual and os.path.exists(arquivo_atual):
        data_arquivo = date.fromtimestamp(os.path.getmtime(arquivo_atual))

    return render_template(
        "pautas.html",
        pautas=pautas_filtradas,
        etapas=etapas,
        visao=visao,
        membros=membros,
        contagem_membros=contagem_membros,
        consultor_selecionado=consultor_selecionado,
        pendencia=pendencia,
        status_filtro=status_filtro,
        statuses_disponiveis=statuses_disponiveis,
        busca=busca,
        total_pautas=total_pautas,
        total_aguardando_un=total_aguardando_un,
        total_respondidas_un=total_respondidas_un,
        total_atrasadas=total_atrasadas,
        quebras_unidade=quebras_unidade,
        quebras_outro=quebras_outro,
        data_arquivo=data_arquivo,
        tem_arquivo=bool(arquivo_atual) or (len(todas_pautas) > 0),
    )


@bp.route("/<int:pauta_id>/observacao", methods=["POST"])
@login_obrigatorio
def salvar_observacao(pauta_id):
    """Salva anotação ou observação interna da pauta sem afetar dados do TM."""
    pauta = db.session.get(Pauta, pauta_id)
    if not pauta:
        if request.is_json:
            return {"sucesso": False, "erro": "Pauta não encontrada"}, 404
        flash("Pauta não encontrada no banco de dados.", "erro")
        return redirect(url_for("pautas.lista"))

    if request.is_json:
        dados = request.get_json() or {}
        texto = dados.get("observacao", "").strip()
    else:
        texto = request.form.get("observacao", "").strip()

    pauta.observacao = texto or None
    pauta.observacao_atualizada_em = agora()

    # Adiciona ao histórico de anotações
    autor_id = getattr(g, "usuario", None).id if getattr(g, "usuario", None) else None
    if texto:
        anotacao = PautaAnotacao(pauta_id=pauta.id, autor_id=autor_id, texto=texto)
        db.session.add(anotacao)

    db.session.commit()

    if request.is_json:
        return {"sucesso": True, "pauta_id": pauta.id, "observacao": pauta.observacao or ""}

    flash(f"Observação da pauta #{pauta.id} atualizada com sucesso.", "ok")
    return redirect(request.referrer or url_for("pautas.lista"))


@bp.route("/enviar", methods=["POST"])
@admin_obrigatorio
def enviar_arquivo():
    """Recebe upload do arquivo CSV ou MHTML e executa a sincronização segura."""
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        flash("Nenhum arquivo foi selecionado.", "erro")
        return redirect(url_for("pautas.lista"))

    ext = os.path.splitext(arquivo.filename)[1].lower()
    if ext not in [".csv", ".mhtml", ".html", ".htm"]:
        flash("Envie um arquivo CSV (.csv) ou página salva (.mhtml/.html) do TM.", "erro")
        return redirect(url_for("pautas.lista"))

    conteudo_bytes = arquivo.read()
    if not conteudo_bytes:
        flash("O arquivo enviado está vazio.", "erro")
        return redirect(url_for("pautas.lista"))

    # Salva arquivo recente na pasta instance
    nome_salvar = "pautas_recente" + ext
    destino = os.path.join(current_app.instance_path, nome_salvar)
    os.makedirs(current_app.instance_path, exist_ok=True)
    with open(destino, "wb") as f:
        f.write(conteudo_bytes)

    try:
        if ext == ".csv" or b'"#";"Categoria"' in conteudo_bytes[:3000] or b'#;Categoria' in conteudo_bytes[:3000]:
            linhas = extrair_linhas_csv(conteudo_bytes)
        else:
            linhas = extrair_linhas_mhtml(conteudo_bytes)

        if not linhas:
            flash("Nenhuma pauta válida encontrada no arquivo enviado.", "erro")
            return redirect(url_for("pautas.lista"))

        processadas = processar_linhas_para_pautas(linhas)
        resumo = sincronizar_pautas_no_banco(processadas)

        flash(
            f"Base de pautas sincronizada com sucesso! {resumo['total_ativas']} ativas "
            f"({resumo['novas']} novas, {resumo['atualizadas']} atualizadas, {resumo['encerradas']} encerradas). "
            f"🚨 Quebras 72h na nossa UN: {resumo['quebras_unidade']}.",
            "ok",
        )
    except Exception as e:
        flash(f"Erro ao processar o arquivo: {e}", "erro")

    return redirect(url_for("pautas.lista"))


@bp.route("/exportar-json")
@login_obrigatorio
def exportar_json():
    consultor = request.args.get("consultor", "")
    pautas = _obter_pautas_gerais()

    if consultor and consultor != "todos":
        c_norm = normalizar_nome(consultor)
        pautas = [
            p for p in pautas
            if c_norm == normalizar_nome(p.get("Responsável"))
            or c_norm == normalizar_nome(p.get("Criada por"))
            or c_norm in normalizar_nome(p.get("Pauta"))
            or p.get("_consultor") == consultor
        ]

    # Remove chaves internas que começam com '_'
    pautas_limpas = []
    for p in pautas:
        limpo = {k: v for k, v in p.items() if not k.startswith("_")}
        pautas_limpas.append(limpo)

    json_str = json.dumps(pautas_limpas, indent=2, ensure_ascii=False, default=str)
    nome_arquivo = f"pautas_{normalizar_nome(consultor) if consultor else 'todas'}.json"

    return Response(
        json_str,
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )
