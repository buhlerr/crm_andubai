import os
import sqlite3

from flask import Flask
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.extensions import db, migrate

CHAVE_PADRAO = "dev-troque-em-producao"
PASTA_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
        SECRET_KEY=os.environ.get("SECRET_KEY") or None,
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", f"sqlite:///{caminho_banco}"),
        # Login de transição com senha única da equipe. Desligado por padrão (0). Ativar com LOGIN_PROVISORIO=1.
        LOGIN_PROVISORIO=os.environ.get("LOGIN_PROVISORIO", "0") in ("1", "true", "True"),
        # Senha única da equipe para o login provisório. Obrigatória se LOGIN_PROVISORIO=1.
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

    if app.config["ATRAS_DE_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix

        # O IIS/proxy avisa por cabeçalho que a conexão original era HTTPS e qual o endereço público.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    em_teste = app.config.get("TESTING") or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if em_teste:
        if not app.config.get("SECRET_KEY"):
            app.config["SECRET_KEY"] = "teste-chave-secreta-ambiente-de-testes"
    else:
        chave_atual = app.config.get("SECRET_KEY")
        if chave_atual == CHAVE_PADRAO:
            raise RuntimeError(
                "A SECRET_KEY não pode ser a chave de desenvolvimento padrão ('dev-troque-em-producao'). "
                "Defina uma chave aleatória e segura."
            )

        if not chave_atual:
            arquivo_chave = os.path.join(app.instance_path, "secret_key")
            if os.path.exists(arquivo_chave):
                try:
                    with open(arquivo_chave, "r", encoding="utf-8") as f:
                        chave = f.read().strip()
                    if chave:
                        app.config["SECRET_KEY"] = chave
                except Exception:
                    pass
            if not app.config.get("SECRET_KEY"):
                import secrets
                chave = secrets.token_hex(32)
                try:
                    with open(arquivo_chave, "w", encoding="utf-8") as f:
                        f.write(chave)
                    try:
                        os.chmod(arquivo_chave, 0o600)
                    except Exception:
                        pass
                    app.config["SECRET_KEY"] = chave
                except Exception:
                    pass

        if not app.config.get("SECRET_KEY") or app.config.get("SECRET_KEY") == CHAVE_PADRAO:
            raise RuntimeError(
                "SECRET_KEY inválida ou não configurada. Defina a variável SECRET_KEY ou configure em config.py."
            )

        if app.config.get("LOGIN_PROVISORIO") and not app.config.get("SENHA_PROVISORIA"):
            raise RuntimeError(
                "LOGIN_PROVISORIO está ativo mas SENHA_PROVISORIA não foi definida no ambiente nem no config.py."
            )

    @app.after_request
    def _adicionar_cabecalhos_seguranca(resposta):
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        if app.config.get("ATRAS_DE_PROXY"):
            resposta.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resposta

    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(PASTA_PROJETO, "migrations"), render_as_batch=True)

    from app import models  # noqa: F401  (registra as tabelas)
    from app.cli import registrar_comandos
    from app.web import registrar_web

    registrar_comandos(app)
    registrar_web(app)
    return app
