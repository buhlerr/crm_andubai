import os
import sqlite3

import pytest

from app import CHAVE_PADRAO, create_app
from app.extensions import db
from app.models import Papel, Usuario


@pytest.fixture
def pasta_dados(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKLIST_DADOS", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


def escrever_config(pasta, texto):
    (pasta / "config.py").write_text(texto, encoding="utf-8")


def test_pasta_de_dados_e_config_py(pasta_dados):
    escrever_config(pasta_dados, 'SECRET_KEY = "chave-do-servidor"\nSERVIDOR_PORTA = 9090\nSENHA_PROVISORIA = "abc"\n')
    app = create_app()
    assert app.instance_path == str(pasta_dados)
    assert app.config["SECRET_KEY"] == "chave-do-servidor"
    assert app.config["SERVIDOR_PORTA"] == 9090
    assert app.config["SQLALCHEMY_DATABASE_URI"].endswith("checklist.db")
    assert str(pasta_dados).replace("\\", "/") in app.config["SQLALCHEMY_DATABASE_URI"].replace("\\", "/")


def test_atras_do_iis_usa_https(pasta_dados):
    escrever_config(pasta_dados, "ATRAS_DE_PROXY = True\n")
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    assert app.config["SESSION_COOKIE_SECURE"] is True

    @app.route("/_esquema")
    def esquema():
        from flask import request
        return request.scheme

    resposta = app.test_client().get("/_esquema", headers={"X-Forwarded-Proto": "https"})
    assert resposta.get_data(as_text=True) == "https"


def test_senha_da_equipe_no_login_provisorio(pasta_dados):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "LOGIN_PROVISORIO": True,
        "SENHA_PROVISORIA": "segredo",
        "SECRET_KEY": "chave-forte-teste-2026",
    })
    with app.app_context():
        db.create_all()
        usuario = Usuario(nome="Pessoa Teste", email="p@exemplo.test")
        db.session.add(usuario)
        db.session.commit()
        cliente = app.test_client()
        pagina = cliente.get("/entrar").get_data(as_text=True)
        assert "e-mail" in pagina.lower() and "senha" in pagina.lower()
        with cliente.session_transaction() as sessao:
            token = sessao["csrf"]
        errada = cliente.post("/entrar", data={"email": usuario.email, "senha": "outra", "csrf": token})
        assert errada.status_code == 200 and "incorret" in errada.get_data(as_text=True).lower()
        certa = cliente.post("/entrar", data={"email": usuario.email, "senha": "segredo", "csrf": token})
        assert certa.status_code == 302


def test_backup_e_rodizio(pasta_dados):
    app = create_app()
    with app.app_context():
        db.create_all()
        db.session.add(Usuario(nome="Pessoa Teste", email="p@exemplo.test"))
        db.session.commit()
        from app.manutencao import fazer_backup

        caminhos = [fazer_backup(app, manter=2) for _ in range(5)]
        restantes = sorted(os.listdir(pasta_dados / "backups"))
        assert restantes == sorted(os.path.basename(c) for c in caminhos[-2:])
        with sqlite3.connect(pasta_dados / "backups" / restantes[-1]) as conexao:
            assert conexao.execute("select nome from usuario").fetchone() == ("Pessoa Teste",)
        db.session.remove()
        db.engine.dispose()


def test_backup_recusa_banco_em_memoria(pasta_dados):
    from app.manutencao import ErroManutencao, fazer_backup

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context(), pytest.raises(ErroManutencao):
        fazer_backup(app)


def test_diagnostico(pasta_dados):
    from app.manutencao import diagnosticar

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "LOGIN_PROVISORIO": True, "SECRET_KEY": CHAVE_PADRAO})
    with app.app_context():
        db.create_all()
        resultado = {v.nome: v for v in diagnosticar(app, testar_excel=False)}
        assert resultado["Chave secreta"].ok is False  # valor padrão
        assert resultado["Login"].ok is False  # provisório sem senha
        assert resultado["Pasta de dados"].ok is True
        assert resultado["Administradores"].ok is False
        assert resultado["Banco de dados"].ok is False  # criado sem as migrações

        db.session.add(Usuario(nome="Admin", email="a@exemplo.test", papel=Papel.ADMIN))
        db.session.commit()
        app.config.update(SECRET_KEY="outra", SENHA_PROVISORIA="x")
        resultado = {v.nome: v for v in diagnosticar(app, testar_excel=False)}
        assert resultado["Chave secreta"].ok and resultado["Administradores"].ok
        assert resultado["Login"].ok is None  # aviso: ainda é provisório


def test_comando_usuario_repetido_da_mensagem_curta(pasta_dados):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        executar = app.test_cli_runner()
        assert executar.invoke(args=["usuarios", "adicionar", "Pessoa", "p@exemplo.test"]).exit_code == 0
        resultado = executar.invoke(args=["usuarios", "adicionar", "Pessoa", "P@exemplo.test"])
        assert resultado.exit_code != 0
        assert "Já existe um usuário com o e-mail p@exemplo.test" in resultado.output
        assert "Traceback" not in resultado.output


def test_servidor_recusa_chave_padrao(pasta_dados, monkeypatch):
    import servidor

    escrever_config(pasta_dados, f'SECRET_KEY = "{CHAVE_PADRAO}"\n')
    monkeypatch.setattr("waitress.serve", lambda *a, **k: pytest.fail("não devia iniciar"))
    with pytest.raises((SystemExit, RuntimeError)):
        servidor.main()
    assert create_app().config["SECRET_KEY"] == CHAVE_PADRAO


def test_servidor_recusa_login_provisorio_sem_senha(pasta_dados, monkeypatch):
    import servidor

    escrever_config(pasta_dados, 'SECRET_KEY = "chave"\nLOGIN_PROVISORIO = True\n')
    monkeypatch.setattr("waitress.serve", lambda *a, **k: pytest.fail("não devia iniciar"))
    with pytest.raises(SystemExit):
        servidor.main()


def test_servidor_sobe_com_config_completo(pasta_dados, monkeypatch):
    import servidor

    escrever_config(pasta_dados, 'SECRET_KEY = "chave"\nSENHA_PROVISORIA = "x"\nSERVIDOR_PORTA = 9999\n')
    chamadas = []
    monkeypatch.setattr("waitress.serve", lambda app, **k: chamadas.append(k))
    servidor.main()
    assert chamadas[0]["port"] == 9999 and chamadas[0]["host"] == "127.0.0.1"
    assert (pasta_dados / "logs" / "servidor.log").exists()
