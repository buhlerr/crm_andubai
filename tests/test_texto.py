from app.texto import separar_neg


def test_neg_com_varias_observacoes_coladas():
    texto = ("15/09 - cobrei envio dos docs (Fulana de Tal, 08-09-2026, 14h10)recobrei cognito "
             "(Beltrana Souza, 04-09-2026, 14h16)Cobrei cognito (Beltrana Souza, 28-08-2026, 10h33)")
    assert separar_neg(texto) == [
        {"texto": "15/09 - cobrei envio dos docs", "autor": "Fulana de Tal", "quando": "08/09/2026 14h10"},
        {"texto": "recobrei cognito", "autor": "Beltrana Souza", "quando": "04/09/2026 14h16"},
        {"texto": "Cobrei cognito", "autor": "Beltrana Souza", "quando": "28/08/2026 10h33"},
    ]


def test_neg_com_texto_depois_da_ultima_assinatura():
    partes = separar_neg("vai alterar (Fulana, 08-09-2026, 17h41)Mais de um ano que cobramos os envios")
    assert partes[-1] == {"texto": "Mais de um ano que cobramos os envios", "autor": None, "quando": None}


def test_neg_sem_assinatura_e_parenteses_comuns():
    assert separar_neg("sem cognito") == [{"texto": "sem cognito", "autor": None, "quando": None}]
    assert separar_neg("entrevista (consulado de SP) em 09/11") == [
        {"texto": "entrevista (consulado de SP) em 09/11", "autor": None, "quando": None}
    ]
    assert separar_neg("") == [] and separar_neg(None) == []
