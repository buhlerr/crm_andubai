"""Conversão dos valores lidos das planilhas para os tipos do banco."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_ID = re.compile(r"^\d+$")
_ID_DECIMAL = re.compile(r"^(\d+)\.0+$")  # o Excel entrega 402668 como 402668.0


class IdInvalido(ValueError):
    pass


def normalizar_id_egali(valor) -> str | None:
    """402668.0, "402668.0", " 402668 " -> "402668". Vazio -> None.
    Qualquer outra coisa (letras, decimais de verdade) -> IdInvalido."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise IdInvalido(valor)
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if valor.is_integer() and valor >= 0:
            return str(int(valor))
        raise IdInvalido(valor)
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return None
    if _ID.match(texto):
        return texto.lstrip("0") or "0"
    if m := _ID_DECIMAL.match(texto):
        return m.group(1).lstrip("0") or "0"
    raise IdInvalido(valor)


def separar_compras(celula) -> tuple[list[str], list[str]]:
    """'5703996, 5703997,5703998' -> (['5703996', '5703997', '5703998'], []).
    Devolve também os pedaços que não são IDs válidos. Sem repetidos, na ordem."""
    if celula is None:
        return [], []
    if isinstance(celula, (int, float)):
        pedacos = [celula]
    else:
        pedacos = str(celula).split(",")
    validos, invalidos = [], []
    for pedaco in pedacos:
        try:
            compra = normalizar_id_egali(pedaco)
        except IdInvalido:
            invalidos.append(str(pedaco).strip())
            continue
        if compra and compra not in validos:
            validos.append(compra)
    return validos, invalidos


def para_texto(valor) -> str | None:
    if valor is None:
        return None
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    return texto or None


def para_data(valor) -> date | None:
    """Aceita date/datetime, ISO ('2026-09-01', '2026-09-01 00:00:00+00:00') e dd/mm/aaaa."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if m := re.match(r"^(\d{4})-(\d{2})-(\d{2})", texto):
        return date(int(m[1]), int(m[2]), int(m[3]))
    if m := re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", texto):
        return date(int(m[3]), int(m[2]), int(m[1]))
    raise ValueError(f"data inválida: {valor!r}")


def para_decimal(valor) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor).replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation as erro:
        raise ValueError(f"número inválido: {valor!r}") from erro
