import hashlib
import os
import secrets
import sqlite3

from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.extensions import db, migrate

CHAVE_PADRAO = "dev-troque-em-producao"
PASTA_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Impressões digitais (SHA-256) de chaves e senhas que já foram publicadas no repositório
# (docker-compose.yml e config.py.exemplo antigos) ou que são textos de exemplo. O sistema
# recusa subir com qualquer uma delas. Guardamos só o hash, nunca o valor.
VALORES_PROIBIDOS_SHA256 = {
    "6140333c0b9ad491a959238d61f1c3a79d2f249d3e8d343560edc7848d1ddbfd",  # SECRET_KEY do docker-compose antigo
    "912d37440b807b13b651c0434797e22232dcbbba6af6eecf0be52a12865b8ec7",  # SECRET_KEY do config.py.exemplo antigo
    "be2422066292ab10133a4e8ea0a75a9d400566eced5c489b9570b90635bd2cb4",  # senha da equipe do docker-compose antigo
    hashlib.sha256(b"senha_da_equipe_aqui").hexdigest(),
    hashlib.sha256(CHAVE_PADRAO.encode()).hexdigest(),
}


class ConfiguracaoInsegura(RuntimeError):
    pass


def _proibido(valor: str | None) -> bool:
    return bool(valor) and hashlib.sha256(str(valor).encode()).hexdigest() in VALORES_PROIBIDOS_SHA256


def _chave_da_pasta_de_dados(pasta: str) -> str:
    """Sem SECRET_KEY configurada, usa uma chave gerada na primeira subida e guardada na pasta de
    dados (persistente no volume do Docker). Vale para qualquer forma de subir: gunicorn, waitress, flask."""
    caminho = os.path.join(pasta, "secret_key")
    if not os.path.exists(caminho):
        chave = secrets.token_hex(32)
        with open(os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            f.write(chave)
    with open(caminho) as f:
        return f.read().strip()


def _conferir_seguranca(app: Flask) -> None:
    if app.config.get("TESTING"):
        return
    if not app.config.get("SECRET_KEY") or app.config["SECRET_KEY"] == CHAVE_PADRAO:
        app.config["SECRET_KEY"] = _chave_da_pasta_de_dados(app.instance_path)
    if _proibido(app.config["SECRET_KEY"]):
        raise ConfiguracaoInsegura(
            "A SECRET_KEY configurada é uma das que foram publicadas no repositório. Gere outra "
            "(python -c \"import secrets; print(secrets.token_hex(32))\") ou apague a variável para o sistema gerar uma."
        )
    if app.config.get("LOGIN_PROVISORIO"):
        senha = app.config.get("SENHA_PROVISORIA")
        if not senha:
            raise ConfiguracaoInsegura("LOGIN_PROVISORIO está ligado sem SENHA_PROVISORIA. Defina a senha da equipe ou desligue o login provisório.")
        if _proibido(senha):
            raise ConfiguracaoInsegura("A SENHA_PROVISORIA é a que foi publicada no repositório (ou o texto de exemplo). Troque a senha da equipe.")


@event.listens_for(Engine, "connect")
def _configurar_sqlite(conexao, _registro):
    if isinstance(conexao, sqlite3.Connection):
        cursor = conexao.cursor()
        # O SQLite só respeita chaves estrangeiras com este PRAGMA ligado.
        cursor.execute("PRAGMA foreign_keys=ON")
        # Várias pessoas usando ao mesmo tempo: WAL deixa ler enquanto alguém grava,
        # e o busy_timeout espera em vez de dar erro quando o banco está ocupado.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        # (A coluna usuario.senha_hash agora vem da migração 11a6fad7f26a.)
        cursor.close()


def create_app(config: dict | None = None) -> Flask:
    """Configuração, em ordem (a última vence):
    1. padrões e variáveis de ambiente (DATABASE_URL, SECRET_KEY, LOGIN_PROVISORIO);
    2. o arquivo config.py da pasta de dados (gerado pelo instalador no servidor);
    3. o dicionário `config` (testes).

    A pasta de dados é CHECKLIST_DADOS, se definida; senão, a pasta instance/ do projeto."""
    pasta_dados = os.environ.get("CHECKLIST_DADOS")
    app = Flask(__name__, instance_path=os.path.abspath(pasta_dados) if pasta_dados else None, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    caminho_banco = os.path.join(app.instance_path, "checklist.db")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or CHAVE_PADRAO,
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", f"sqlite:///{caminho_banco}"),
        # Transição: quem ainda não tem senha individual entra uma vez com a senha da equipe e cria a sua.
        # Desligado por padrão; ligue (LOGIN_PROVISORIO=1) só enquanto houver gente sem senha. Nunca vale para admin.
        LOGIN_PROVISORIO=os.environ.get("LOGIN_PROVISORIO", "0") == "1",
        # Senha da equipe para a transição. Obrigatória se LOGIN_PROVISORIO estiver ligado.
        SENHA_PROVISORIA=os.environ.get("SENHA_PROVISORIA") or None,
        # True quando o proxy reverso (Nginx, Caddy, Cloudflare, IIS) fica na frente com HTTPS.
        ATRAS_DE_PROXY=os.environ.get("ATRAS_DE_PROXY", "0") in ("1", "true", "True"),
        SERVIDOR_HOST=os.environ.get("SERVIDOR_HOST", "127.0.0.1"),
        SERVIDOR_PORTA=int(os.environ.get("SERVIDOR_PORTA", "8080")),
        SERVIDOR_THREADS=int(os.environ.get("SERVIDOR_THREADS", "8")),
        BACKUPS_MANTER=30,
        MAX_CONTENT_LENGTH=30 * 1024 * 1024,  # planilha semanal ~1,3 MB; folga para crescer
    )
    app.config.from_pyfile("config.py", silent=True)
    if config:
        app.config.update(config)
    _conferir_seguranca(app)

    if app.config["ATRAS_DE_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix

        # O IIS avisa por cabeçalho que a conexão original era HTTPS e qual o endereço público.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        resposta.headers.setdefault("X-Frame-Options", "DENY")
        resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
        resposta.headers.setdefault("Referrer-Policy", "same-origin")
        if app.config["ATRAS_DE_PROXY"]:  # só atrás do proxy com HTTPS
            resposta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return resposta

    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(PASTA_PROJETO, "migrations"), render_as_batch=True)

    from app import models  # noqa: F401  (registra as tabelas)
    from app.cli import registrar_comandos
    from app.web import registrar_web

    registrar_comandos(app)
    registrar_web(app)
    return app
