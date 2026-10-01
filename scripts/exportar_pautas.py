"""Script de exportação e processamento de pautas do sistema TM (Egali).

Extrai a tabela de pautas a partir de arquivo .mhtml ou .html salvo da página
de pautas (https://tm.egali.com.br/TM/index.php).

Gera a lista de pautas estruturada no formato JSON solicitado, com cálculo
de dias, identificação de atualização pela unidade ("AN e Dubai") e extração
do nome do aluno.
"""

import argparse
import email
from email import policy
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime

# Consultores da unidade AN e Dubai: vêm da variável de ambiente PAUTAS_MEMBROS_UNIDADE (nomes separados
# por ponto e vírgula) ou do parâmetro --membros. Nomes de pessoas não ficam no código, que é versionado.
MEMBROS_PADRAO_UNIDADE = {m.strip() for m in os.environ.get("PAUTAS_MEMBROS_UNIDADE", "").split(";") if m.strip()}


def normalizar_texto(txt: str | None) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt).encode("ASCII", "ignore").decode("ASCII")
    return txt.lower().strip()


def extrair_html_de_mhtml_ou_arquivo(caminho_ou_bytes: str | bytes) -> str:
    """Extrai o texto HTML principal a partir de um arquivo .mhtml, .html ou bytes."""
    if isinstance(caminho_ou_bytes, str):
        if not os.path.exists(caminho_ou_bytes):
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho_ou_bytes}")
        with open(caminho_ou_bytes, "rb") as f:
            conteudo = f.read()
    else:
        conteudo = caminho_ou_bytes

    # Verifica se é formato MHTML (MIME multipart)
    if b"MIME-Version:" in conteudo[:2000] or b"multipart/related" in conteudo[:2000]:
        msg = email.message_from_bytes(conteudo, policy=policy.default)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload and len(payload) > 500:
                    for enc in ["utf-8", "cp1252", "iso-8859-1"]:
                        try:
                            return payload.decode(enc)
                        except Exception:
                            continue
        raise ValueError("Nenhuma parte text/html encontrada no arquivo MHTML.")
    else:
        # Arquivo HTML comum
        for enc in ["utf-8", "cp1252", "iso-8859-1"]:
            try:
                return conteudo.decode(enc)
            except Exception:
                continue
        return conteudo.decode("latin1", errors="replace")


def extrair_nome_aluno(pauta_texto: str, aluno_coluna: str, pauta_id: str) -> str:
    """Extrai o nome do aluno da coluna ou a partir da string da pauta."""
    aluno_limpo = aluno_coluna.strip()
    if aluno_limpo and aluno_limpo != "+ alunos" and aluno_limpo != "#NAME?":
        return aluno_limpo

    # Padrão típico do TM: ID - CODIGO_SETOR - NOME ALUNO - ESCOLA (CIDADE) - DATA
    # Exemplo: "9000001 - AC-SA-AND - Nome do Aluno - Escola Exemplo - (Toronto) - 15/05/2026"
    partes = [p.strip() for p in pauta_texto.split(" - ")]
    if len(partes) >= 3:
        # Se a primeira parte for o ID ou dígitos, a 3ª parte costuma ser o aluno
        if partes[0] == pauta_id or partes[0].isdigit():
            return partes[2]
        # Caso formato seja "NOME - Alteração nos dados...":
        return partes[0]

    return aluno_limpo if aluno_limpo != "+ alunos" else ""


def extrair_pautas(
    caminho_ou_bytes: str | bytes,
    data_referencia: date | None = None,
    membros_unidade: set[str] | None = None,
    nome_unidade: str = "AN e Dubai",
) -> list[dict]:
    """Processa o HTML e devolve a lista de pautas estruturada."""
    if data_referencia is None:
        data_referencia = date.today()

    if membros_unidade is None:
        membros_norm = {normalizar_texto(m) for m in MEMBROS_PADRAO_UNIDADE}
    else:
        membros_norm = {normalizar_texto(m) for m in membros_unidade}

    html = extrair_html_de_mhtml_ou_arquivo(caminho_ou_bytes)

    # Localiza a tabela principal de pautas
    marcador = "Contagem de pautas:"
    pos = html.find(marcador)
    if pos == -1:
        # Fallback: procura pela tabela com classes trList
        pautas_html = html
    else:
        end_table = html.find("</table>", pos)
        pautas_html = html[pos:end_table] if end_table != -1 else html[pos:]

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", pautas_html, re.DOTALL | re.IGNORECASE)
    pautas = []

    for r in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.DOTALL | re.IGNORECASE)
        clean_tds = [re.sub(r"<[^>]+>", "", t).strip() for t in tds]
        if not clean_tds or not clean_tds[0].isdigit():
            continue

        pid = clean_tds[0]
        cat = clean_tds[1]
        pauta_str = clean_tds[2]
        status = clean_tds[3]
        responsavel = clean_tds[4]

        # Criação: "17/09/2026 18:14:42 por Nome Sobrenome"
        cria_raw = clean_tds[5] if len(clean_tds) > 5 else ""
        cria_m = re.match(r"(\d{2}/\d{2}/\d{4})\s*(?:\d{2}:\d{2}:\d{2})?\s*(?:por\s*(.*))?", cria_raw)
        cria_em = cria_m.group(1) if cria_m else ""
        cria_por = cria_m.group(2).strip() if (cria_m and cria_m.group(2)) else ""

        # Atualizado: "30/09/2026 08:55:51 por Outro Nome"
        atual_raw = clean_tds[6] if len(clean_tds) > 6 else ""
        atual_m = re.match(r"(\d{2}/\d{2}/\d{4})\s*(?:\d{2}:\d{2}:\d{2})?\s*(?:por\s*(.*))?", atual_raw)
        atual_em = atual_m.group(1) if atual_m else ""
        atual_por = atual_m.group(2).strip() if (atual_m and atual_m.group(2)) else ""

        # Aluno
        aluno_raw = clean_tds[7] if len(clean_tds) > 7 else ""
        aluno = extrair_nome_aluno(pauta_str, aluno_raw, pid)

        # Tag
        tag_raw = clean_tds[9] if len(clean_tds) > 9 else ""

        # Dias sem atualização
        dias = "0"
        data_base_str = atual_em or cria_em
        if data_base_str:
            try:
                dt_base = datetime.strptime(data_base_str, "%d/%m/%Y").date()
                diff = (data_referencia - dt_base).days
                dias = str(max(0, diff))
            except Exception:
                dias = "0"

        # UN Atualizou e Atualizada?
        un_atualizou = ""
        if normalizar_texto(atual_por) in membros_norm:
            un_atualizou = nome_unidade

        atualizada = "TRUE" if un_atualizou == nome_unidade else "FALSE"

        item = {
            "Atualizada?": atualizada,
            "Dias": dias,
            "ID": pid,
            "Atualizado em": atual_em,
            "UN Atualizou": un_atualizou,
            "Responsável": responsavel,
            "TAG": tag_raw,
            "Status": status,
            "Categoria": cat,
            "Pauta": pauta_str,
            "Criada por": cria_por,
            "Atualizado por": atual_por,
            "Aluno": aluno,
            "Criada em": cria_em,
        }
        pautas.append(item)

    return pautas


def filtrar_por_consultor(pautas: list[dict], consultor: str) -> list[dict]:
    """Filtra pautas onde o consultor é Responsável, Criador ou citado na pauta."""
    c_norm = normalizar_texto(consultor)
    resultado = []
    for p in pautas:
        resp_norm = normalizar_texto(p.get("Responsável"))
        cria_norm = normalizar_texto(p.get("Criada por"))
        pauta_norm = normalizar_texto(p.get("Pauta"))
        if c_norm == resp_norm or c_norm == cria_norm or c_norm in pauta_norm:
            resultado.append(p)
    return resultado


def main():
    parser = argparse.ArgumentParser(description="Exporta pautas do TM para JSON estruturado.")
    parser.add_argument("arquivo", help="Caminho do arquivo .mhtml ou .html")
    parser.add_argument("--consultor", help="Filtrar por nome do consultor (ex: 'Nome Sobrenome')")
    parser.add_argument("--membros", help="Nomes da unidade separados por ponto e vírgula (senão, PAUTAS_MEMBROS_UNIDADE)")
    parser.add_argument("--saida", help="Arquivo de saída JSON (padrão: stdout)")
    parser.add_argument("--data-ref", help="Data de referência para cálculo de dias (DD/MM/AAAA)")
    args = parser.parse_args()

    data_ref = None
    if args.data_ref:
        data_ref = datetime.strptime(args.data_ref, "%d/%m/%Y").date()

    membros = {m.strip() for m in args.membros.split(";") if m.strip()} if args.membros else None
    pautas = extrair_pautas(args.arquivo, data_referencia=data_ref, membros_unidade=membros)

    if args.consultor:
        pautas = filtrar_por_consultor(pautas, args.consultor)

    json_str = json.dumps(pautas, indent=2, ensure_ascii=False)

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"Salvas {len(pautas)} pautas em {args.saida}")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
