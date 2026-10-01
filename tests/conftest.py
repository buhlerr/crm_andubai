import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "teste-chave-secreta-forte-2026",
        "LOGIN_PROVISORIO": True,
        "SENHA_PROVISORIA": "senha-equipe-forte-2026",
    })
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _limpar_tentativas():
    from app.web.auth import _TENTATIVAS_FALHAS
    _TENTATIVAS_FALHAS.clear()
    yield
    _TENTATIVAS_FALHAS.clear()
