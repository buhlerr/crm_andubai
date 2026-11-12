"""Leitura do checklist exportado do sistema Egali (checklistServicoNew.csv).

Separador ";". A exportação vem em cp1252 (Windows); se um dia vier em
UTF-8, também funciona. Tudo é lido como texto.

Quando a leitura passar a ser direta da ferramenta da Egali, basta trocar
este módulo por outro que devolva as mesmas linhas.
"""

import csv
import io
import os

from app.importacao import ErroImportacao
from app.texto import normalizar_texto


def decodificar(bruto: bytes) -> str:
    try:
        return bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return bruto.decode("cp1252")
    except UnicodeDecodeError:
        return bruto.decode("latin1")  # nunca falha


def ler_texto_csv(texto: str) -> list[dict]:
    """Devolve [{"linha": n, "valores": {cabeçalho_normalizado: texto}}], sem as linhas vazias."""
    todas = list(csv.reader(io.StringIO(texto, newline=""), delimiter=";"))
    if not todas:
        return []
    # A exportação do TM pode vir com linhas antes do cabeçalho (campos ocultos da tela e
    # "Contagem de linhas: N"). O cabeçalho é a primeira linha com a coluna "#"; sem ela, a primeira.
    inicio = next((i for i, valores in enumerate(todas) if "#" in (normalizar_texto(v) for v in valores)), 0)
    cabecalho = [normalizar_texto(c) for c in todas[inicio]]
    linhas = []
    for numero, valores in enumerate(todas[inicio + 1:], start=inicio + 2):
        if not any(v.strip() for v in valores):
            continue
        linhas.append({"linha": numero, "valores": {c: v for c, v in zip(cabecalho, valores) if c}})
    return linhas


def ler_csv(caminho: str) -> list[dict]:
    if not os.path.exists(caminho):
        raise ErroImportacao(f"Arquivo não encontrado: {caminho}")
    try:
        with open(caminho, "rb") as arquivo:
            bruto = arquivo.read()
    except PermissionError as erro:
        raise ErroImportacao("O arquivo está aberto em outro programa (Excel?). Feche e tente de novo.") from erro
    return ler_texto_csv(decodificar(bruto))
