import re
import unicodedata

_TRACOS = str.maketrans({"–": "-", "—": "-", "−": "-", "`": "'", "’": "'", "‘": "'"})


# Cada observação do NEG termina com "(Nome, dd-mm-aaaa, HHhMM)"; a Egali cola todas sem separador.
_ASSINATURA_NEG = re.compile(r"\(([^()]+?),\s*(\d{2}-\d{2}-\d{4}),\s*(\d{1,2}h\d{2})\)")


def separar_neg(texto: str | None) -> list[dict]:
    """'obs A (Fulana, 10-09-2026, 14h23)obs B (Beltrano, 08-09-2026, 17h46)' ->
    [{'texto': 'obs A', 'autor': 'Fulana', 'quando': '10/09/2026 14h23'}, {...}].
    Texto sem assinatura vira uma entrada sem autor. A ordem é a da Egali (mais recente primeiro)."""
    if not texto or not texto.strip():
        return []
    partes, inicio = [], 0
    for m in _ASSINATURA_NEG.finditer(texto):
        trecho = texto[inicio:m.start()].strip()
        if trecho:
            partes.append({"texto": trecho, "autor": m.group(1).strip(), "quando": f"{m.group(2).replace('-', '/')} {m.group(3)}"})
        inicio = m.end()
    resto = texto[inicio:].strip()
    if resto:
        partes.append({"texto": resto, "autor": None, "quando": None})
    return partes


def normalizar_texto(texto: str | None) -> str:
    """Forma usada para comparar textos vindos de fontes diferentes (planilha,
    CSV, PPT): mesmos acentos, traços e aspas unificados, espaços colapsados
    e sem diferença de maiúsculas."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFC", str(texto)).translate(_TRACOS)
    return re.sub(r"\s+", " ", texto).strip().casefold()
