import pytest
from app import create_app
from app.extensions import db
from app.models import Papel, Usuario
from app.web.auth import _TENTATIVAS_FALHAS


@pytest.fixture(autouse=True)
def _desligar_csrf_para_auth(app):
    app.config["CSRF_DESLIGADO"] = True
    yield
    app.config["CSRF_DESLIGADO"] = False




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

    # Troca com senha curta (< 10 caracteres)
    res_curta = client.post("/trocar-senha", data={
        "senha_atual": "SenhaAntiga1",
        "nova_senha": "Curta123",
        "confirmacao": "Curta123"
    })
    assert "A nova senha deve ter pelo menos 10 caracteres.".encode("utf-8") in res_curta.data

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
    admin.definir_senha("AdminPass10")
    db.session.add(admin)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["usuario_id"] = admin.id

    # Tentativa de criar com senha menor que 10 caracteres
    res_invalida = client.post("/cadastros/usuarios", data={
        "nome": "Consultor Invalido",
        "email": "invalido@exemplo.test",
        "papel": "consultor",
        "senha": "12345"
    }, follow_redirects=True)
    assert "A senha deve ter no mínimo 10 caracteres.".encode("utf-8") in res_invalida.data

    # Cria novo usuário com senha válida (>= 10 chars)
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


def test_login_rate_limiting(app, client):
    _TENTATIVAS_FALHAS.clear()
    for i in range(10):
        res = client.post("/entrar", data={"email": "tentativa@exemplo.test", "senha": f"errada{i}"})
        assert res.status_code == 200
        assert b"E-mail ou senha incorretos." in res.data

    # 11ª tentativa deve ser bloqueada com 429
    res_bloqueada = client.post("/entrar", data={"email": "tentativa@exemplo.test", "senha": "outra"})
    assert res_bloqueada.status_code == 429
    assert "Muitas tentativas. Aguarde alguns minutos.".encode("utf-8") in res_bloqueada.data


def test_transicao_senha_equipe(app, client):
    # Consultor sem senha consegue usar senha de equipe para definir senha
    consultor = Usuario(nome="Consultor Transição", email="transicao@exemplo.test", papel=Papel.CONSULTOR)
    # Admin sem senha NÃO pode usar a senha de equipe
    admin = Usuario(nome="Admin Transição", email="admin_transicao@exemplo.test", papel=Papel.ADMIN)
    db.session.add_all([consultor, admin])
    db.session.commit()

    # 1. Admin tenta usar senha de equipe: deve ser rejeitado
    res_admin = client.post("/entrar", data={"email": "admin_transicao@exemplo.test", "senha": "senha-equipe-forte-2026"})
    assert res_admin.status_code == 200
    assert "Contas de administrador não podem usar a senha provisória".encode("utf-8") in res_admin.data

    # 2. Consultor usa senha de equipe: deve ser aceito e redirecionado para trocar-senha
    res_consultor = client.post("/entrar", data={"email": "transicao@exemplo.test", "senha": "senha-equipe-forte-2026"})
    assert res_consultor.status_code == 302
    assert res_consultor.headers["Location"].endswith("/trocar-senha")


def test_cabecalhos_seguranca_http(app, client):
    res = client.get("/entrar")
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
