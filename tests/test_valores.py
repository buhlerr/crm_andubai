from datetime import date, datetime
from decimal import Decimal

import pytest

from app.importacao.valores import IdInvalido, normalizar_id_egali, para_data, para_decimal, para_texto, separar_compras


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(402668.0, "402668"), ("402668.0", "402668"), (" 402668 ", "402668"), (402668, "402668"),
     ("00123", "123"), (None, None), ("", None), ("  ", None), ("nan", None)],
)
def test_normalizar_id(valor, esperado):
    assert normalizar_id_egali(valor) == esperado


@pytest.mark.parametrize("valor", ["abc", "12.5", 12.5, -1.0, "1e5", True])
def test_id_invalido(valor):
    with pytest.raises(IdInvalido):
        normalizar_id_egali(valor)


def test_separar_compras():
    assert separar_compras("5703996, 5703997,5703998 , ") == (["5703996", "5703997", "5703998"], [])
    assert separar_compras("1, 1, 2") == (["1", "2"], [])
    assert separar_compras("1, x2, 3") == (["1", "3"], ["x2"])
    assert separar_compras(5703996.0) == (["5703996"], [])
    assert separar_compras(None) == ([], [])


def test_lista_longa_de_compras_nao_e_cortada():
    ids = [str(6000000 + i) for i in range(40)]
    assert separar_compras(", ".join(ids))[0] == ids


def test_para_data():
    assert para_data("2027-07-01 00:00:00+00:00") == date(2027, 7, 1)
    assert para_data("2027-07-01") == date(2027, 7, 1)
    assert para_data("08/01/2027") == date(2027, 1, 8)
    assert para_data(datetime(2027, 1, 8, 15)) == date(2027, 1, 8)
    assert para_data(None) is None
    with pytest.raises(ValueError):
        para_data("janeiro")


def test_para_decimal_e_texto():
    assert para_decimal(243.01) == Decimal("243.01")
    assert para_decimal("85") == Decimal("85.00")
    assert para_decimal(None) is None
    assert para_texto("  PVH - SMART   GROUP  ") == "PVH - SMART GROUP"
    assert para_texto("   ") is None
