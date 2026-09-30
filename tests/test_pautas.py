from datetime import date
import os
import pytest
from app import create_app
from app.extensions import db
from app.importacao.pautas import carregar_pautas, normalizar_nome
from app.models import Papel, Usuario

CAMINHO_MHTML = os.path.join(os.path.dirname(__file__), "..", "pautas_home.mhtml")


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "CSRF_DESLIGADO": True})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_carregar_pautas_mhtml_existente():
    if not os.path.exists(CAMINHO_MHTML):
        return

    data_ref = date(2026, 9, 30)
    pautas = carregar_pautas(CAMINHO_MHTML, data_referencia=data_ref)

    assert len(pautas) == 77

    # Verifica pauta 3102692
    p1 = next((p for p in pautas if p["ID"] == "3102692"), None)
    assert p1 is not None
    assert p1["Atualizada?"] == "FALSE"
    assert p1["Dias"] == "0"
    assert p1["UN Atualizou"] == ""
    assert p1["Responsável"] == "Márcia Bocorny Allgayer"
    assert p1["Criada por"] == "Vitor Bühler Rau"
    assert p1["Atualizado por"] == "Márcia Bocorny Allgayer"
    assert p1["Aluno"] == "Thays Baptista De Souza"
    assert p1["Status"] == "Em aberto"

    # Verifica pauta 3101587 (atualizada pela unidade)
    p2 = next((p for p in pautas if p["ID"] == "3101587"), None)
    assert p2 is not None
    assert p2["Atualizada?"] == "TRUE"
    assert p2["Dias"] == "2"
    assert p2["UN Atualizou"] == "AN e Dubai"
    assert p2["Responsável"] == "Vitor Bühler Rau"
    assert p2["TAG"] == "Atrasada"

    # Verifica pauta 3102536 (com extração inteligente de aluno)
    p3 = next((p for p in pautas if p["ID"] == "3102536"), None)
    assert p3 is not None
    assert p3["Aluno"] == "Letícia Vitória Silva Gomes"
    assert p3["Criada por"] == "Vitor Bühler Rau"


def test_carregar_pautas_csv_existente():
    caminho_csv = os.path.join(os.path.dirname(__file__), "..", "pautaList-30_09_2026.csv")
    if not os.path.exists(caminho_csv):
        return

    data_ref = date(2026, 9, 30)
    pautas = carregar_pautas(caminho_csv, data_referencia=data_ref)

    assert len(pautas) == 77
    p1 = next((p for p in pautas if p["ID"] == "3102692"), None)
    assert p1 is not None
    assert p1["Responsável"] == "Márcia Bocorny Allgayer"
    assert p1["Aluno"] == "Thays Baptista De Souza"
    assert p1["Status"] == "Em aberto"
    assert p1["Atualizada?"] == "FALSE"



def test_rota_web_pautas(app, client):
    u = Usuario(nome="Vitor Bühler Rau", email="vitor@egali.com.br", papel=Papel.ADMIN)
    db.session.add(u)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["usuario_id"] = u.id

    res = client.get("/pautas/")
    assert res.status_code == 200
    assert "Pautas por Consultor" in res.text
    assert "3102692" in res.text

    # Teste de exportação JSON
    res_json = client.get("/pautas/exportar-json?consultor=Vitor Bühler Rau")
    assert res_json.status_code == 200
    assert res_json.content_type.startswith("application/json")
    dados = res_json.json
    assert isinstance(dados, list)
    assert len(dados) > 0
    assert any(p["ID"] == "3102692" for p in dados)


def test_salvar_observacao_ajax_e_upsert(app, client):
    u = Usuario(nome="Consultor Teste", email="consultor@teste.com", papel=Papel.CONSULTOR)
    db.session.add(u)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["usuario_id"] = u.id

    # Garante que pautas foram carregadas no banco
    client.get("/pautas/")

    from app.models.pautas import Pauta, PautaAnotacao
    pauta = Pauta.query.first()
    assert pauta is not None
    pauta_id = pauta.id

    # Salva observação via endpoint AJAX
    res = client.post(
        f"/pautas/{pauta_id}/observacao",
        json={"observacao": "Aguardando confirmação de voo com aluno."},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["sucesso"] is True
    assert data["observacao"] == "Aguardando confirmação de voo com aluno."

    # Verifica persistência no banco
    pauta_atualizada = db.session.get(Pauta, pauta_id)
    assert pauta_atualizada.observacao == "Aguardando confirmação de voo com aluno."
    assert len(pauta_atualizada.anotacoes) == 1
    assert pauta_atualizada.anotacoes[0].texto == "Aguardando confirmação de voo com aluno."
    assert pauta_atualizada.anotacoes[0].autor_id == u.id

    # Testa que nova sincronização do TM preserva a observação interna
    from app.importacao.pautas import carregar_pautas, sincronizar_pautas_no_banco
    linhas = carregar_pautas(CAMINHO_MHTML)
    sincronizar_pautas_no_banco(linhas, arquivo_origem="teste_reimport.mhtml")

    pauta_apos_sync = db.session.get(Pauta, pauta_id)
    assert pauta_apos_sync.observacao == "Aguardando confirmação de voo com aluno."
    assert len(pauta_apos_sync.anotacoes) == 1


def test_cadastros_pautas_setores(app, client):
    admin = Usuario(nome="Admin Master", email="admin@teste.com", papel=Papel.ADMIN)
    db.session.add(admin)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["usuario_id"] = admin.id

    # 1. Acessa a tela de configurações de pautas
    res = client.get("/cadastros/pautas")
    assert res.status_code == 200
    assert "Mapeamento de Setores para Pautas" in res.text

    # 2. Adiciona novo colaborador -> setor
    res_add = client.post(
        "/cadastros/pautas",
        data={
            "acao": "adicionar",
            "nome": "Marcia Bocorny Allgayer",
            "setor": "Acomodação",
        },
        follow_redirects=True,
    )
    assert "cadastrado(a) no setor" in res_add.text
    assert "Marcia Bocorny Allgayer" in res_add.text

    from app.models.pautas import ColaboradorSetor
    colab = ColaboradorSetor.query.filter_by(nome="Marcia Bocorny Allgayer").first()
    assert colab is not None
    assert colab.setor == "Acomodação"

    # 3. Edita o mapeamento atualizando o setor
    res_edit = client.post(
        "/cadastros/pautas",
        data={
            "acao": "adicionar",
            "nome": "Marcia Bocorny Allgayer",
            "setor": "Aéreo / Reembolsos",
        },
        follow_redirects=True,
    )
    assert res_edit.status_code == 200
    db.session.refresh(colab)
    assert colab.setor == "Aéreo / Reembolsos"

    # 4. Remove o mapeamento
    res_del = client.post(
        "/cadastros/pautas",
        data={
            "acao": "remover",
            "id": colab.id,
        },
        follow_redirects=True,
    )
    assert res_del.status_code == 200
    assert db.session.get(ColaboradorSetor, colab.id) is None

