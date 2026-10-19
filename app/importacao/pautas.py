"""Leitor, parser e sincronizador de Pautas de Comunicação Interna (TM Egali).

Lê arquivos .csv (pautaList-*.csv) ou .mhtml exportados do sistema corporativo,
associa categorias a SLAs (app/dados/pautas_sla.csv), cruza setores via ColaboradorSetor
e usuários da unidade, e executa Upsert declarativo seguro no banco de dados.
"""

import csv
import email
from email import policy
import os
import re
import unicodedata
from datetime import date, datetime, timezone
from io import BytesIO, StringIO

from app.extensions import db
from app.models.base import agora
from app.models.cadastro import Usuario
from app.models.pautas import ColaboradorSetor, Pauta

NOME_UNIDADE_PADRAO = "AN e Dubai"

# Tabela de prazos (SLA) por categoria: só "categoria;horas", tirada da lista de categorias do TM.
# Para atualizar sem mexer no código, ponha um pautas_sla.csv no mesmo formato na pasta de dados.
SLA_PADRAO = os.path.join(os.path.dirname(__file__), "..", "dados", "pautas_sla.csv")

_CACHE_SLA_CATEGORIAS: dict[str, int] | None = None


def membros_padrao() -> list[str]:
    """Nomes da unidade quando ainda não há usuários cadastrados: vêm da configuração
    (PAUTAS_MEMBROS_UNIDADE no config.py), nunca do código, que é versionado."""
    try:
        from flask import current_app

        return list(current_app.config.get("PAUTAS_MEMBROS_UNIDADE") or [])
    except RuntimeError:
        return []


def normalizar_nome(txt: str | None) -> str:
    """Normaliza strings removendo acentos, pontuações e convertendo para minúsculas."""
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")
    return txt.lower().strip()


def limpar_categoria(cat: str | None) -> str:
    """Remove traços e espaços residuais no final do nome da categoria."""
    if not cat:
        return ""
    return re.sub(r"\s*-\s*$", "", cat).strip()


def obter_membros_unidade() -> dict[str, Usuario | None]:
    """Retorna mapa de {nome_normalizado: Usuario} dos consultores ativos da unidade."""
    resultado = {}
    try:
        usuarios = db.session.execute(db.select(Usuario).filter_by(ativo=True)).scalars().all()
        for u in usuarios:
            resultado[normalizar_nome(u.nome)] = u
    except Exception:
        pass

    if not resultado:
        for m in membros_padrao():
            resultado[normalizar_nome(m)] = None

    return resultado


def _caminho_sla() -> str:
    try:
        from flask import current_app

        personalizado = os.path.join(current_app.instance_path, "pautas_sla.csv")
        if os.path.exists(personalizado):
            return personalizado
    except RuntimeError:
        pass
    return SLA_PADRAO


def carregar_sla_categorias() -> dict[str, int]:
    """Tempo de resposta em horas de cada categoria (arquivo "categoria;horas")."""
    global _CACHE_SLA_CATEGORIAS
    if _CACHE_SLA_CATEGORIAS is not None:
        return _CACHE_SLA_CATEGORIAS

    mapa: dict[str, int] = {}
    caminho_csv = _caminho_sla()
    if os.path.exists(caminho_csv):
        with open(caminho_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                nome = (row.get("categoria") or "").strip()
                horas = (row.get("horas") or "").strip()
                if nome and horas.isdigit():
                    mapa[normalizar_nome(nome)] = int(horas)
                    mapa[normalizar_nome(limpar_categoria(nome))] = int(horas)

    _CACHE_SLA_CATEGORIAS = mapa
    return mapa


def obter_mapa_colaborador_setor() -> dict[str, str]:
    """Retorna mapa de {nome_normalizado: setor} para colaboradores externos cadastrados."""
    mapa: dict[str, str] = {}
    try:
        linhas = db.session.execute(db.select(ColaboradorSetor)).scalars().all()
        for c in linhas:
            mapa[c.nome_normalizado] = c.setor
    except Exception:
        pass
    return mapa


def extrair_nome_aluno(pauta_str: str, aluno_col: str, pid: str) -> str:
    """Extrai o nome do aluno da coluna ou da string da pauta."""
    if aluno_col and aluno_col != "+ alunos" and aluno_col.strip():
        return aluno_col.strip()

    # Formato comum: "3104087 - AC-SA-AND - Nome do Aluno - Escola (Cidade) - 26/09/2026"
    partes = [p.strip() for p in pauta_str.split(" - ")]
    if len(partes) >= 3:
        cand = partes[2]
        if cand and not cand.isdigit() and len(cand) > 3:
            return cand

    # Formato com hífen: "Visto CAD negado - Rebeca Dias de Lima"
    m_traco = re.search(r"-\s*([A-ZÀ-Úa-zà-ú\s]{4,40})$", pauta_str)
    if m_traco:
        return m_traco.group(1).strip()

    return aluno_col if aluno_col and aluno_col != "+ alunos" else ""


def extrair_horas_inativas(tempo_str: str | None) -> int:
    """Converte string de tempo inativo (ex: '145:33:42' ou '05:18:35') para inteiro de horas."""
    if not tempo_str:
        return 0
    m = re.match(r"^(\d+):", tempo_str.strip())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return 0
    return 0


def converter_data_tm(data_str: str | None) -> datetime | None:
    """Converte data do formato DD/MM/AAAA para datetime UTC."""
    if not data_str:
        return None
    data_limpa = data_str.strip()[:10]
    try:
        dt = datetime.strptime(data_limpa, "%d/%m/%Y")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def extrair_linhas_csv(conteudo_bytes: bytes) -> list[dict]:
    """Lê bytes de um arquivo CSV de pautas (latin1, delimiter ';') e retorna lista de dicionários."""
    for enc in ["latin1", "cp1252", "iso-8859-1", "utf-8-sig", "utf-8"]:
        try:
            texto = conteudo_bytes.decode(enc)
            break
        except Exception:
            continue
    else:
        texto = conteudo_bytes.decode("latin1", errors="ignore")

    lines = texto.splitlines()
    header_idx = -1
    for idx, line in enumerate(lines[:15]):
        if line.startswith('"#"') or line.startswith('#;') or '";"Categoria";' in line:
            header_idx = idx
            break

    if header_idx == -1:
        return []

    stream = StringIO("\n".join(lines[header_idx:]))
    reader = csv.DictReader(stream, delimiter=";")
    return [row for row in reader if row.get("#") and row.get("#").strip().isdigit()]


def extrair_linhas_mhtml(conteudo_bytes: bytes) -> list[dict]:
    """Fallback para arquivos MHTML/HTML caso o usuário suba arquivo salvo do navegador."""
    html = ""
    if b"MIME-Version:" in conteudo_bytes[:2000] or b"multipart/related" in conteudo_bytes[:2000]:
        msg = email.message_from_bytes(conteudo_bytes, policy=policy.default)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                try:
                    html = payload.decode(charset)
                except Exception:
                    html = payload.decode("latin1", errors="replace")
                break
    if not html:
        try:
            html = conteudo_bytes.decode("utf-8")
        except Exception:
            html = conteudo_bytes.decode("latin1", errors="replace")

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    itens = []
    for r in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.DOTALL | re.IGNORECASE)
        clean = [re.sub(r"<[^>]+>", "", t).strip() for t in tds]
        if not clean or not clean[0].isdigit():
            continue
        pid = clean[0]
        cat = clean[1] if len(clean) > 1 else ""
        pauta = clean[2] if len(clean) > 2 else ""
        status = clean[3] if len(clean) > 3 else ""
        resp = clean[4] if len(clean) > 4 else ""
        cria_raw = clean[5] if len(clean) > 5 else ""
        atual_raw = clean[6] if len(clean) > 6 else ""
        aluno_raw = clean[7] if len(clean) > 7 else ""
        tempo_str = clean[8] if len(clean) > 8 else ""
        tag = clean[9] if len(clean) > 9 else ""

        cria_m = re.match(r"(\d{2}/\d{2}/\d{4})\s*(?:\d{2}:\d{2}:\d{2})?\s*(?:por\s*(.*))?", cria_raw)
        cria_em = cria_m.group(1) if cria_m else ""
        cria_por = cria_m.group(2).strip() if (cria_m and cria_m.group(2)) else ""

        atual_m = re.match(r"(\d{2}/\d{2}/\d{4})\s*(?:\d{2}:\d{2}:\d{2})?\s*(?:por\s*(.*))?", atual_raw)
        atual_em = atual_m.group(1) if atual_m else ""
        atual_por = atual_m.group(2).strip() if (atual_m and atual_m.group(2)) else ""

        itens.append({
            "#": pid,
            "Categoria": cat,
            "Pauta": pauta,
            "Status": status,
            "Consultor": resp,
            "Criado em": cria_em,
            "Criado por": cria_por,
            "Atualizado em": atual_em,
            "Atualizado por": atual_por,
            "Aluno": aluno_raw,
            "Atualizado": tempo_str,
            "TAG": tag,
        })
    return itens


def processar_linhas_para_pautas(linhas_brutas: list[dict], data_referencia: date | None = None) -> list[dict]:
    """Aplica toda a lógica de negócio, categorização de SLA e setores da unidade sobre as linhas lidas."""
    if data_referencia is None:
        data_referencia = date.today()

    membros_map = obter_membros_unidade()
    colaborador_setor_map = obter_mapa_colaborador_setor()
    slas_categorias = carregar_sla_categorias()

    def _determinar_setor(nome_pessoa: str | None) -> str:
        if not nome_pessoa:
            return ""
        norm = normalizar_nome(nome_pessoa)
        if norm in membros_map:
            return NOME_UNIDADE_PADRAO
        if norm in colaborador_setor_map:
            return colaborador_setor_map[norm]
        return "Outro Setor"

    pautas_processadas = []

    for row in linhas_brutas:
        pid_str = row.get("#", "").strip()
        if not pid_str.isdigit():
            continue
        pid = int(pid_str)

        cat_original = row.get("Categoria", "").strip()
        cat_limpa = re.sub(r"\s*-\s*$", "", cat_original).strip()

        pauta_str = row.get("Pauta", "").strip()
        status = row.get("Status", "").strip()
        responsavel = row.get("Consultor", "").strip()
        if responsavel in ["Sem respons&aacute;vel", "Sem responsável"]:
            responsavel = "Sem responsável"

        cria_em_str = row.get("Criado em", "").strip()
        cria_por = row.get("Criado por", "").strip()
        atual_em_str = row.get("Atualizado em", "").strip()
        atual_por = row.get("Atualizado por", "").strip()

        aluno_raw = row.get("Aluno", "").strip()
        aluno = extrair_nome_aluno(pauta_str, aluno_raw, str(pid))

        tag = row.get("TAG", "").strip()
        tempo_str = row.get("Atualizado", "").strip()
        horas_inativas = extrair_horas_inativas(tempo_str)

        # Determina SLA da categoria
        sla_horas = slas_categorias.get(normalizar_nome(cat_limpa))
        if sla_horas is None:
            sla_horas = slas_categorias.get(normalizar_nome(cat_original))

        # Determina Setores conforme planilha paralela
        un_responsavel = _determinar_setor(responsavel) if responsavel != "Sem responsável" else ""
        un_criou = _determinar_setor(cria_por)
        un_atualizou = _determinar_setor(atual_por)

        tem_relacao_unidade = (
            un_responsavel == NOME_UNIDADE_PADRAO
            or un_criou == NOME_UNIDADE_PADRAO
            or un_atualizou == NOME_UNIDADE_PADRAO
        )
        if not tem_relacao_unidade:
            continue

        # UN Final: =IF(UN_Resp<>UN_Criou, UN_Resp & " - " & UN_Criou, UN_Resp)
        if un_responsavel and un_criou and un_responsavel != un_criou:
            un_final = f"{un_responsavel} - {un_criou}"
        else:
            un_final = un_responsavel or un_criou

        atualizada_un = (un_atualizou == NOME_UNIDADE_PADRAO)

        # Quebra 72h
        quebra_un = (tag == "Atrasada 72h +" and un_responsavel == NOME_UNIDADE_PADRAO)
        quebra_outro = (tag == "Atrasada 72h +" and un_responsavel != NOME_UNIDADE_PADRAO)

        # Dias sem atualização (para ordenação)
        dias = 0
        data_base_str = atual_em_str or cria_em_str
        if data_base_str:
            try:
                dt_base = datetime.strptime(data_base_str[:10], "%d/%m/%Y").date()
                dias = max(0, (data_referencia - dt_base).days)
            except Exception:
                dias = 0

        # Encontra consultor atribuído da nossa unidade
        consultor_usuario = None
        if normalizar_nome(responsavel) in membros_map:
            consultor_usuario = membros_map[normalizar_nome(responsavel)]
        elif normalizar_nome(cria_por) in membros_map:
            consultor_usuario = membros_map[normalizar_nome(cria_por)]
        else:
            for m_norm, u_obj in membros_map.items():
                if m_norm in normalizar_nome(pauta_str):
                    consultor_usuario = u_obj
                    break

        item = {
            "id": pid,
            "categoria": cat_original,
            "categoria_limpa": cat_limpa,
            "pauta_titulo": pauta_str,
            "aluno": aluno,
            "status_tm": status,
            "responsavel_tm": responsavel,
            "criado_em_tm": converter_data_tm(cria_em_str),
            "criado_por_tm": cria_por,
            "atualizado_em_tm": converter_data_tm(atual_em_str),
            "atualizado_por_tm": atual_por,
            "tag": tag,
            "tempo_inativo_texto": tempo_str,
            "tempo_inativo_horas": horas_inativas,
            "prazo_sla_horas": sla_horas,
            "un_atualizou": un_atualizou,
            "un_responsavel": un_responsavel,
            "un_criou": un_criou,
            "un_final": un_final,
            "atualizada_un": atualizada_un,
            "quebra_72h_unidade": quebra_un,
            "quebra_72h_outro": quebra_outro,
            "dias_inativo": dias,
            "consultor_usuario_id": consultor_usuario.id if consultor_usuario else None,
            "consultor_nome": consultor_usuario.nome if consultor_usuario else "Outros",
        }
        pautas_processadas.append(item)

    return pautas_processadas


def sincronizar_pautas_no_banco(linhas_processadas: list[dict], arquivo_origem: str | None = None) -> dict:
    """Executa o Upsert das pautas no banco de dados SQLite.

    - Pautas existentes: atualiza dados externos e indicadores, preserva dados internos.
    - Pautas novas: insere no banco.
    - Pautas ativas no banco que não vieram no arquivo: marca como encerrada_em = agora(), ativa = False.
    """
    if not linhas_processadas:
        return {"novas": 0, "atualizadas": 0, "encerradas": 0, "quebras_unidade": 0}

    agora_momento = agora()

    # Normaliza dicionários de entrada para aceitar tanto processar_linhas_para_pautas quanto carregar_pautas
    itens_normalizados = []
    for p in linhas_processadas:
        pid = int(p.get("id") or p.get("ID"))
        criado_tm = p.get("criado_em_tm")
        if criado_tm is None and p.get("Criada em"):
            criado_tm = converter_data_tm(p.get("Criada em"))

        atualizado_tm = p.get("atualizado_em_tm")
        if atualizado_tm is None and p.get("Atualizado em"):
            atualizado_tm = converter_data_tm(p.get("Atualizado em"))

        cat_orig = p.get("categoria") or p.get("Categoria") or ""
        cat_limpa = p.get("categoria_limpa") or limpar_categoria(cat_orig)

        atualizada_un_val = p.get("atualizada_un")
        if atualizada_un_val is None:
            atualizada_un_val = (p.get("Atualizada?") == "TRUE")

        horas_inativo = p.get("tempo_inativo_horas") or p.get("Horas Inativo")
        if horas_inativo is None:
            try:
                horas_inativo = int(p.get("Dias", 0)) * 24
            except (ValueError, TypeError):
                horas_inativo = 0

        item = {
            "id": pid,
            "categoria": cat_orig,
            "categoria_limpa": cat_limpa,
            "pauta_titulo": p.get("pauta_titulo") or p.get("Pauta") or "",
            "aluno": p.get("aluno") or p.get("Aluno"),
            "status_tm": p.get("status_tm") or p.get("Status") or "Em aberto",
            "responsavel_tm": p.get("responsavel_tm") or p.get("Responsável"),
            "criado_em_tm": criado_tm,
            "criado_por_tm": p.get("criado_por_tm") or p.get("Criada por"),
            "atualizado_em_tm": atualizado_tm,
            "atualizado_por_tm": p.get("atualizado_por_tm") or p.get("Atualizado por"),
            "tag": p.get("tag") or p.get("TAG"),
            "tempo_inativo_texto": p.get("tempo_inativo_texto") or p.get("Tempo Inativo"),
            "tempo_inativo_horas": horas_inativo,
            "prazo_sla_horas": p.get("prazo_sla_horas") or p.get("SLA"),
            "un_atualizou": p.get("un_atualizou") or p.get("UN Atualizou"),
            "un_responsavel": p.get("un_responsavel") or p.get("UN Responsável"),
            "un_criou": p.get("un_criou") or p.get("UN Criou"),
            "un_final": p.get("un_final") or p.get("UN Final"),
            "atualizada_un": bool(atualizada_un_val),
            "quebra_72h_unidade": bool(p.get("quebra_72h_unidade") or p.get("Quebra UN")),
            "quebra_72h_outro": bool(p.get("quebra_72h_outro") or p.get("Quebra Outro")),
            "consultor_usuario_id": p.get("consultor_usuario_id") or p.get("_consultor_id"),
        }
        itens_normalizados.append(item)

    ids_no_arquivo = {p["id"] for p in itens_normalizados}

    novas = 0
    atualizadas = 0
    quebras_unidade = 0

    pautas_existentes = db.session.execute(
        db.select(Pauta).where(Pauta.id.in_(ids_no_arquivo))
    ).scalars().all()
    mapa_existentes = {p.id: p for p in pautas_existentes}

    for dados in itens_normalizados:
        pid = dados["id"]
        pauta = mapa_existentes.get(pid)

        if dados["quebra_72h_unidade"]:
            quebras_unidade += 1

        if pauta:
            # Atualiza campos externos do TM
            pauta.categoria = dados["categoria"]
            pauta.categoria_limpa = dados["categoria_limpa"]
            pauta.pauta_titulo = dados["pauta_titulo"]
            pauta.aluno = dados["aluno"] or pauta.aluno
            pauta.status_tm = dados["status_tm"]
            pauta.responsavel_tm = dados["responsavel_tm"]
            pauta.criado_em_tm = dados["criado_em_tm"]
            pauta.criado_por_tm = dados["criado_por_tm"]
            pauta.atualizado_em_tm = dados["atualizado_em_tm"]
            pauta.atualizado_por_tm = dados["atualizado_por_tm"]
            pauta.tag = dados["tag"]
            pauta.tempo_inativo_texto = dados["tempo_inativo_texto"]
            pauta.tempo_inativo_horas = dados["tempo_inativo_horas"]
            pauta.prazo_sla_horas = dados["prazo_sla_horas"]
            pauta.un_atualizou = dados["un_atualizou"]
            pauta.un_responsavel = dados["un_responsavel"]
            pauta.un_criou = dados["un_criou"]
            pauta.un_final = dados["un_final"]
            pauta.atualizada_un = dados["atualizada_un"]
            pauta.quebra_72h_unidade = dados["quebra_72h_unidade"]
            pauta.quebra_72h_outro = dados["quebra_72h_outro"]
            pauta.ativa = True
            pauta.encerrada_em = None
            pauta.importacao_em = agora_momento
            if not pauta.consultor_id and dados["consultor_usuario_id"]:
                pauta.consultor_id = dados["consultor_usuario_id"]
            atualizadas += 1
        else:
            # Cria nova pauta
            nova_pauta = Pauta(
                id=pid,
                categoria=dados["categoria"],
                categoria_limpa=dados["categoria_limpa"],
                pauta_titulo=dados["pauta_titulo"],
                aluno=dados["aluno"],
                status_tm=dados["status_tm"],
                responsavel_tm=dados["responsavel_tm"],
                criado_em_tm=dados["criado_em_tm"],
                criado_por_tm=dados["criado_por_tm"],
                atualizado_em_tm=dados["atualizado_em_tm"],
                atualizado_por_tm=dados["atualizado_por_tm"],
                tag=dados["tag"],
                tempo_inativo_texto=dados["tempo_inativo_texto"],
                tempo_inativo_horas=dados["tempo_inativo_horas"],
                prazo_sla_horas=dados["prazo_sla_horas"],
                un_atualizou=dados["un_atualizou"],
                un_responsavel=dados["un_responsavel"],
                un_criou=dados["un_criou"],
                un_final=dados["un_final"],
                atualizada_un=dados["atualizada_un"],
                quebra_72h_unidade=dados["quebra_72h_unidade"],
                quebra_72h_outro=dados["quebra_72h_outro"],
                ativa=True,
                importacao_em=agora_momento,
                consultor_id=dados["consultor_usuario_id"],
            )
            db.session.add(nova_pauta)
            novas += 1

    # Pautas que estavam ativas no banco mas sumiram do arquivo (concluídas/canceladas no TM)
    pautas_encerradas = db.session.execute(
        db.select(Pauta).where(Pauta.ativa.is_(True), Pauta.id.not_in(ids_no_arquivo))
    ).scalars().all()

    for p in pautas_encerradas:
        p.ativa = False
        p.encerrada_em = agora_momento
        if "finaliz" not in p.status_tm.lower() and "cancel" not in p.status_tm.lower():
            p.status_tm = "Finalizado"

    db.session.commit()

    return {
        "novas": novas,
        "atualizadas": atualizadas,
        "encerradas": len(pautas_encerradas),
        "total_ativas": len(linhas_processadas),
        "quebras_unidade": quebras_unidade,
    }


def carregar_pautas(caminho_ou_bytes: str | bytes, data_referencia: date | None = None) -> list[dict]:
    """Carrega e retorna as pautas no formato legado/dicionário para compatibilidade com templates."""
    if isinstance(caminho_ou_bytes, str):
        if not os.path.exists(caminho_ou_bytes):
            return []
        with open(caminho_ou_bytes, "rb") as f:
            conteudo = f.read()
    else:
        conteudo = caminho_ou_bytes

    if b'"#";"Categoria"' in conteudo[:3000] or b'#;Categoria' in conteudo[:3000]:
        linhas = extrair_linhas_csv(conteudo)
    else:
        linhas = extrair_linhas_mhtml(conteudo)

    processadas = processar_linhas_para_pautas(linhas, data_referencia=data_referencia)

    # Converte para as chaves compatíveis com o template
    resultado = []
    for p in processadas:
        item = {
            "ID": str(p["id"]),
            "Categoria": p["categoria"],
            "Pauta": p["pauta_titulo"],
            "Aluno": p["aluno"],
            "Status": p["status_tm"],
            "Responsável": p["responsavel_tm"],
            "Criada por": p["criado_por_tm"],
            "Criada em": p["criado_em_tm"].strftime("%d/%m/%Y") if p["criado_em_tm"] else "",
            "Atualizado por": p["atualizado_por_tm"],
            "Atualizado em": p["atualizado_em_tm"].strftime("%d/%m/%Y") if p["atualizado_em_tm"] else "",
            "TAG": p["tag"],
            "Dias": str(p["dias_inativo"]),
            "Atualizada?": "TRUE" if p["atualizada_un"] else "FALSE",
            "UN Atualizou": p["un_atualizou"] if p["atualizada_un"] else "",
            "UN Responsável": p["un_responsavel"],
            "UN Criou": p["un_criou"],
            "UN Final": p["un_final"],
            "Tempo Inativo": p["tempo_inativo_texto"],
            "Horas Inativo": p["tempo_inativo_horas"],
            "SLA": p["prazo_sla_horas"],
            "Quebra UN": p["quebra_72h_unidade"],
            "Quebra Outro": p["quebra_72h_outro"],
            "_consultor": p["consultor_nome"],
            "_consultor_id": p["consultor_usuario_id"],
        }
        resultado.append(item)

    return resultado
