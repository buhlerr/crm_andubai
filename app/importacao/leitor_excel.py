"""Leitura da planilha de alunos via python-calamine (multiplataforma).

Compatível com Linux (Proxmox LXC/Docker) e Windows. Ignora proteções
de bloqueio de células e lê com alta performance sem depender do Excel instalado.
No Windows, mantém fallback opcional para automação COM caso calamine não esteja disponível.

O resultado são linhas com valores simples (texto, número, data em ISO),
prontos para guardar em JSON na prévia da importação.
"""

import os
import sys
import time
from datetime import date, datetime, time as dtime

from app.importacao import ErroImportacao
from app.texto import normalizar_texto


def _simples(valor):
    if valor is None:
        return None
    if isinstance(valor, (datetime, date)) or hasattr(valor, "year"):
        return date(valor.year, valor.month, valor.day).isoformat()
    if isinstance(valor, dtime):
        return valor.isoformat()
    if isinstance(valor, (int, float, str)):
        return valor
    return str(valor)


def ler_planilha(caminho: str, nome_aba: str, colunas_texto: tuple[str, ...] = (), tentativas: int = 3) -> list[dict]:
    """Devolve [{"linha": n, "valores": {cabeçalho_normalizado: valor}}], sem as linhas vazias.

    Colunas em colunas_texto são lidas como texto: se o Excel tiver
    convertido a célula em número, converte preservando representação textual."""
    caminho = os.path.abspath(caminho)
    if not os.path.exists(caminho):
        raise ErroImportacao(f"Arquivo não encontrado: {caminho}")

    try:
        return _ler_calamine(caminho, nome_aba, colunas_texto)
    except ErroImportacao:
        raise
    except Exception as erro:
        # Se estiver no Windows e calamine falhou com erro inesperado, tenta COM como fallback
        if sys.platform == "win32":
            try:
                return _ler_com_windows(caminho, nome_aba, colunas_texto, tentativas)
            except Exception:
                pass
        raise ErroImportacao(f"Não foi possível abrir a planilha: {erro}") from erro


def _ler_calamine(caminho: str, nome_aba: str, colunas_texto: tuple[str, ...]) -> list[dict]:
    try:
        from python_calamine import CalamineWorkbook, PasswordError
    except ImportError as erro:
        raise RuntimeError("python-calamine não está instalado.") from erro

    try:
        wb = CalamineWorkbook.from_path(caminho)
    except PasswordError as erro:
        raise ErroImportacao("A planilha está protegida por senha de abertura. Remova a senha antes de importar.") from erro
    except Exception as erro:
        raise ErroImportacao(f"Não foi possível abrir o arquivo de planilha: {erro}") from erro

    if nome_aba not in wb.sheet_names:
        raise ErroImportacao(
            f"A aba '{nome_aba}' não foi encontrada na planilha. Abas encontradas: {', '.join(wb.sheet_names)}."
        )

    sheet = wb.get_sheet_by_name(nome_aba)
    linhas_grade = sheet.to_python()
    if not linhas_grade or len(linhas_grade) < 2:
        return []

    # Localiza o cabeçalho na primeira linha não vazia
    indice_cabecalho = None
    for idx, r in enumerate(linhas_grade):
        if any(c is not None and str(c).strip() for c in r):
            indice_cabecalho = idx
            break

    if indice_cabecalho is None or len(linhas_grade) <= indice_cabecalho + 1:
        return []

    primeira_linha = ((sheet.start[0] + 1) if getattr(sheet, "start", None) else 1) + indice_cabecalho
    cabecalho_bruto = linhas_grade[indice_cabecalho]
    cabecalho = [normalizar_texto(c) if c is not None else "" for c in cabecalho_bruto]
    indices_texto = {i for i, c in enumerate(cabecalho) if c in {normalizar_texto(t) for t in colunas_texto}}

    linhas = []
    for deslocamento, linha in enumerate(linhas_grade[indice_cabecalho + 1:], start=1):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in linha):
            continue
        dados = {}
        for i, (coluna, valor) in enumerate(zip(cabecalho, linha)):
            if not coluna:
                continue
            if i in indices_texto and valor is not None:
                if isinstance(valor, float) and valor.is_integer():
                    valor = str(int(valor))
                else:
                    valor = str(valor).strip()
            dados[coluna] = _simples(valor)
        linhas.append({"linha": primeira_linha + deslocamento, "valores": dados})
    return linhas


def _ler_com_windows(caminho: str, nome_aba: str, colunas_texto: tuple[str, ...], tentativas: int = 3) -> list[dict]:
    """Fallback legado no Windows usando automação COM do Excel."""
    import pythoncom
    import win32com.client as win32

    pythoncom.CoInitialize()
    try:
        for tentativa in range(1, tentativas + 1):
            excel = None
            try:
                excel = win32.DispatchEx("Excel.Application")
                excel.Visible = False
                excel.DisplayAlerts = False
                excel.Interactive = False
                pasta = excel.Workbooks.Open(caminho, ReadOnly=True, UpdateLinks=False)
                try:
                    nomes = [pasta.Sheets(i).Name for i in range(1, pasta.Sheets.Count + 1)]
                    if nome_aba not in nomes:
                        raise ErroImportacao(
                            f"A aba '{nome_aba}' não foi encontrada na planilha. Abas encontradas: {', '.join(nomes)}."
                        )
                    aba = pasta.Sheets(nome_aba)
                    usado = aba.UsedRange
                    valores = usado.Value
                    if not valores or len(valores) < 2:
                        return []
                    primeira_linha = usado.Row
                    cabecalho = [normalizar_texto(c) if c is not None else "" for c in valores[0]]
                    indices_texto = {i for i, c in enumerate(cabecalho) if c in {normalizar_texto(t) for t in colunas_texto}}

                    linhas = []
                    for deslocamento, linha in enumerate(valores[1:], start=1):
                        if all(v is None or (isinstance(v, str) and not v.strip()) for v in linha):
                            continue
                        dados = {}
                        for i, (coluna, valor) in enumerate(zip(cabecalho, linha)):
                            if not coluna:
                                continue
                            if i in indices_texto and valor is not None and not isinstance(valor, str):
                                valor = usado.Cells(deslocamento + 1, i + 1).Text
                            dados[coluna] = _simples(valor)
                        linhas.append({"linha": primeira_linha + deslocamento, "valores": dados})
                    return linhas
                finally:
                    pasta.Close(SaveChanges=False)
            except ErroImportacao:
                raise
            except Exception as erro:
                if tentativa == tentativas:
                    raise ErroImportacao(f"Não foi possível abrir a planilha no Excel: {erro}") from erro
                time.sleep(5)
            finally:
                if excel is not None:
                    try:
                        excel.Quit()
                    except Exception:
                        pass
    finally:
        pythoncom.CoUninitialize()

