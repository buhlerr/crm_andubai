import io
import os
import zipfile
import pytest

from app.importacao import ErroImportacao
from app.importacao.leitor_excel import ler_planilha


def _gerar_planilha_teste(linhas_xml: list[str], nome_aba: str = "Base", linha_inicio: int = 1) -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    wb_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{nome_aba}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""

    wb_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""

    linhas_corpo = "\n".join(linhas_xml)
    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    {linhas_corpo}
  </sheetData>
</worksheet>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", wb_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return buf.getvalue()


def test_ler_planilha_sucesso(tmp_path):
    linhas_xml = [
        """<row r="1">
            <c r="A1" t="inlineStr"><is><t>programa_id</t></is></c>
            <c r="B1" t="inlineStr"><is><t>aluno_id</t></is></c>
            <c r="C1" t="inlineStr"><is><t>aluno_name</t></is></c>
            <c r="D1" t="inlineStr"><is><t>compra_id</t></is></c>
            <c r="E1" t="inlineStr"><is><t>consultor</t></is></c>
        </row>""",
        """<row r="2">
            <c r="A2"><v>1001</v></c>
            <c r="B2"><v>2001</v></c>
            <c r="C2" t="inlineStr"><is><t>João Silva</t></is></c>
            <c r="D2"><v>5703996</v></c>
            <c r="E2" t="inlineStr"><is><t>Ana Paula</t></is></c>
        </row>""",
    ]
    arquivo = tmp_path / "alunos.xlsx"
    arquivo.write_bytes(_gerar_planilha_teste(linhas_xml))

    resultado = ler_planilha(str(arquivo), "Base", colunas_texto=("compra_id",))

    assert len(resultado) == 1
    linha = resultado[0]
    assert linha["linha"] == 2
    assert linha["valores"]["programa_id"] == 1001.0
    assert linha["valores"]["aluno_id"] == 2001.0
    assert linha["valores"]["aluno_name"] == "João Silva"
    assert linha["valores"]["compra_id"] == "5703996"
    assert linha["valores"]["consultor"] == "Ana Paula"


def test_ler_planilha_com_offset_de_linhas(tmp_path):
    linhas_xml = [
        """<row r="3">
            <c r="B3" t="inlineStr"><is><t>programa_id</t></is></c>
            <c r="C3" t="inlineStr"><is><t>aluno_name</t></is></c>
        </row>""",
        """<row r="4">
            <c r="B4"><v>1002</v></c>
            <c r="C4" t="inlineStr"><is><t>Mariana Santos</t></is></c>
        </row>""",
    ]
    arquivo = tmp_path / "offset.xlsx"
    arquivo.write_bytes(_gerar_planilha_teste(linhas_xml))

    resultado = ler_planilha(str(arquivo), "Base")
    assert len(resultado) == 1
    assert resultado[0]["linha"] == 4
    assert resultado[0]["valores"]["programa_id"] == 1002.0
    assert resultado[0]["valores"]["aluno_name"] == "Mariana Santos"


def test_ler_planilha_aba_inexistente(tmp_path):
    arquivo = tmp_path / "sem_aba.xlsx"
    arquivo.write_bytes(_gerar_planilha_teste(["<row r='1'><c r='A1' t='inlineStr'><is><t>col</t></is></c></row>"]))

    with pytest.raises(ErroImportacao) as exc_info:
        ler_planilha(str(arquivo), "AbaNaoExistente")
    assert "A aba 'AbaNaoExistente' não foi encontrada" in str(exc_info.value)


def test_ler_planilha_arquivo_inexistente():
    with pytest.raises(ErroImportacao) as exc_info:
        ler_planilha("caminho/falso/nao_existe.xlsx", "Base")
    assert "Arquivo não encontrado" in str(exc_info.value)


def test_ler_planilha_vazia(tmp_path):
    arquivo = tmp_path / "vazia.xlsx"
    arquivo.write_bytes(_gerar_planilha_teste([]))

    resultado = ler_planilha(str(arquivo), "Base")
    assert resultado == []
