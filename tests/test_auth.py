import pytest
from app import create_app
from app.extensions import db
from app.models import Papel, Usuario


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


def test_usuario_definir_e_verificar_senha(app):
    u = Usuario(nome="Consultor Teste", email="consultor@exemplo.test", papel=Papel.CONSULTOR)
    u.definir_senha("SenhaSegura123")
    db.session.add(u)
    db.session.commit()

    assert u.senha_hash is not None
    assert u.verificar_senha("SenhaSegura123") is True
    assert u.verificar_senha("SenhaErrada") is False
    assert u.verificar_senha("") is False


def test_login_com_email_e_senha(app, client):
    u = Usuario(nome="Admin Teste", email="admin@exemplo.test", papel=Papel.ADMIN)
    u.definir_senha("Admin@12345")
    db.session.add(u)
    db.session.commit()

    # Login com senha errada
    res = client.post("/entrar", data={"email": "admin@exemplo.test", "senha": "errada"})
    assert res.status_code == 200
    assert b"E-mail ou senha incorretos." in res.data

    # Login com senha certa
    res = client.post("/entrar", data={"email": "admin@exemplo.test", "senha": "Admin@12345"})
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/minha-fila")


def test_trocar_senha_usuario(app, client):
    u = Usuario(nome="Usuario Teste", email="user@exemplo.test", papel=Papel.CONSULTOR)
    u.definir_senha("SenhaAntiga1")
    db.session.add(u)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["usuario_id"] = u.id

    # Troca com senha atual errada
    res = client.post("/trocar-senha", data={
        "senha_atual": "errada",
        "nova_senha": "NovaSenhaForte2",
        "confirmacao": "NovaSenhaForte2"
    })
    assert b"A senha atual informada est" in res.data

    # Troca com sucesso
    res = client.post("/trocar-senha", data={
        "senha_atual": "SenhaAntiga1",
        "nova_senha": "NovaSenhaForte2",
        "confirmacao": "NovaSenhaForte2"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Sua senha foi alterada com sucesso." in res.data

    db.session.refresh(u)
    assert u.verificar_senha("NovaSenhaForte2") is True
    assert u.verificar_senha("SenhaAntiga1") is False


def test_admin_cria_e_edita_usuario_com_senha(app, client):
    admin = Usuario(nome="Admin", email="admin@exemplo.test", papel=Papel.ADMIN)
    admin.definir_senha("AdminPass1")
    db.session.add(admin)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["usuario_id"] = admin.id

    # Cria novo usuário com senha
    res = client.post("/cadastros/usuarios", data={
        "nome": "Novo Consultor",
        "email": "novo@exemplo.test",
        "papel": "consultor",
        "senha": "ConsultorPass1"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Novo Consultor cadastrado(a) com sucesso." in res.data

    novo = db.session.execute(db.select(Usuario).filter_by(email="novo@exemplo.test")).scalar_one()
    assert novo.verificar_senha("ConsultorPass1") is True

    # Redefine a senha do consultor
    res = client.post(f"/cadastros/usuarios/{novo.id}", data={
        "nome": "Novo Consultor Alterado",
        "email": "novo@exemplo.test",
        "papel": "consultor",
        "ativo": "1",
        "nova_senha": "ResetPass999"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert "Usuário atualizado com sucesso.".encode("utf-8") in res.data

    db.session.refresh(novo)
    assert novo.verificar_senha("ResetPass999") is True
