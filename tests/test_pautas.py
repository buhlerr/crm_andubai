"""Pautas TM. Só amostras fictícias (tests/amostras/, geradas por gerar_amostras.py): nunca arquivos reais."""

import io
import os
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.importacao.pautas import carregar_pautas
from app.models import Papel, Usuario

AMOSTRAS = os.path.join(os.path.dirname(__file__), "amostras")
CSV = os.path.join(AMOSTRAS, "pautas_exemplo.csv")
HTML = os.path.join(AMOSTRAS, "pautas_exemplo.html")
TOKEN = "token-de-teste"


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    app.instance_path = str(tmp_path)  # o envio grava o arquivo na pasta de dados: nunca na do projeto
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Usuario(nome="Consultora Ana", email="ana@exemplo.test", papel=Papel.CONSULTOR),
            Usuario(nome="Admin Teste", email="admin@exemplo.test", papel=Papel.ADMIN),
        ])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def entrar(client, email):
    usuario = db.session.execute(db.select(Usuario).filter_by(email=email)).scalar_one()
    with client.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = usuario.id, TOKEN
    return usuario


def enviar(client, caminho):
    with open(caminho, "rb") as f:
        return client.post("/pautas/enviar", data={"csrf": TOKEN, "arquivo": (io.BytesIO(f.read()), os.path.basename(caminho))},
                           content_type="multipart/form-data", follow_redirects=True)


@pytest.mark.parametrize("caminho", [CSV, HTML])
def test_le_csv_e_pagina_salva(app, caminho):
    pautas = {p["ID"]: p for p in carregar_pautas(caminho, data_referencia=date(2026, 10, 1))}
    assert set(pautas) == {"9000001", "9000002", "9000003"}
    p1 = pautas["9000001"]
    assert p1["Aluno"] == "Aluno Ficticio Um"  # tirado do título da pauta
    assert p1["Criada por"] == "Consultora Ana" and p1["Responsável"] == "Pessoa Acomodacao"
    assert p1["SLA"] == 72  # "MKT - Criação de material" na tabela app/dados/pautas_sla.csv
    assert p1["UN Criou"] == "AN e Dubai" and p1["UN Responsável"] == "Outro Setor"
    assert p1["Quebra Outro"] and not p1["Quebra UN"]
    assert pautas["9000002"]["Aluno"] == "Aluna Ficticia Dois"  # formato "... - Nome"
    assert pautas["9000002"]["Atualizada?"] == "TRUE"
    assert pautas["9000003"]["SLA"] is None  # categoria fora da tabela


def test_rotas_de_pautas_exigem_login(client):
    for url in ("/pautas/", "/pautas/exportar-json"):
        resposta = client.get(url)
        assert resposta.status_code == 302 and "/entrar" in resposta.headers["Location"], url
    assert client.post("/pautas/9000001/observacao", json={"observacao": "x"}).status_code in (302, 400)


def test_envio_so_para_admin_e_sincroniza(app, client):
    entrar(client, "ana@exemplo.test")
    assert enviar(client, CSV).status_code == 403
    entrar(client, "admin@exemplo.test")
    resposta = enviar(client, CSV)
    assert "Base de pautas sincronizada" in resposta.get_data(as_text=True)
    assert os.path.exists(os.path.join(app.instance_path, "pautas_recente.csv"))
    pagina = client.get("/pautas/").get_data(as_text=True)
    assert "9000001" in pagina
    dados = client.get("/pautas/exportar-json?consultor=Consultora Ana").get_json()
    assert any(p["ID"] == "9000001" for p in dados)


def test_observacao_por_fetch_com_token_e_reimportacao_preserva(app, client):
    from app.importacao.pautas import sincronizar_pautas_no_banco
    from app.models.pautas import Pauta

    entrar(client, "admin@exemplo.test")
    enviar(client, CSV)
    sem_token = client.post("/pautas/9000001/observacao", json={"observacao": "nota"})
    assert sem_token.status_code == 400  # o CSRF vale também para o fetch
    com_token = client.post("/pautas/9000001/observacao", json={"observacao": "Aguardando retorno do setor."},
                            headers={"X-CSRF-Token": TOKEN})
    assert com_token.status_code == 200 and com_token.get_json()["sucesso"] is True
    assert "X-CSRF-Token" in client.get("/pautas/").get_data(as_text=True)  # a tela manda o token

    sincronizar_pautas_no_banco(carregar_pautas(HTML), arquivo_origem="reimportacao.html")
    pauta = db.session.get(Pauta, 9000001)
    assert pauta.observacao == "Aguardando retorno do setor." and len(pauta.anotacoes) == 1


def test_membros_da_unidade_vem_da_configuracao(app):
    from app.importacao.pautas import membros_padrao

    assert membros_padrao() == []  # nada de nomes no código
    app.config["PAUTAS_MEMBROS_UNIDADE"] = ["Nome Sobrenome"]
    assert membros_padrao() == ["Nome Sobrenome"]


def test_cadastros_pautas_setores(app, client):
    entrar(client, "admin@exemplo.test")
    res = client.get("/cadastros/pautas")
    assert res.status_code == 200 and "Mapeamento de Setores para Pautas" in res.text

    res_add = client.post("/cadastros/pautas", data={"csrf": TOKEN, "acao": "adicionar", "nome": "Pessoa Acomodacao",
                                                     "setor": "Acomodação"}, follow_redirects=True)
    assert "cadastrado(a) no setor" in res_add.text and "Pessoa Acomodacao" in res_add.text

    from app.models.pautas import ColaboradorSetor
    colab = db.session.execute(db.select(ColaboradorSetor).filter_by(nome="Pessoa Acomodacao")).scalar_one()
    assert colab.setor == "Acomodação"

    client.post("/cadastros/pautas", data={"csrf": TOKEN, "acao": "adicionar", "nome": "Pessoa Acomodacao",
                                           "setor": "Aéreo / Reembolsos"}, follow_redirects=True)
    db.session.refresh(colab)
    assert colab.setor == "Aéreo / Reembolsos"

    res_del = client.post("/cadastros/pautas", data={"csrf": TOKEN, "acao": "remover", "id": colab.id}, follow_redirects=True)
    assert res_del.status_code == 200 and db.session.get(ColaboradorSetor, colab.id) is None
