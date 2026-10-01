"""As migrações precisam funcionar num banco com dados: é o que acontece no
servidor a cada atualização (instalar/atualizar.ps1 roda flask db upgrade)."""

import sqlite3

from flask_migrate import downgrade, upgrade

from app import create_app
from app.extensions import db


def test_migracoes_sobem_e_descem_com_dados(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKLIST_DADOS", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()
    arquivo = tmp_path / "checklist.db"
    with app.app_context():
        upgrade()
        # Usuário referenciado por outras tabelas: é isso que faz o SQLite recusar recriar a tabela.
        with db.engine.begin() as conexao:
            conexao.exec_driver_sql(
                "INSERT INTO usuario (nome, email, papel, ativo, criado_em, atualizado_em) "
                "VALUES ('Pessoa', 'p@exemplo.test', 'admin', 1, '2026-09-29', '2026-09-29')"
            )
            conexao.exec_driver_sql(
                "INSERT INTO importacao (tipo, situacao, iniciada_por_id, iniciada_em) VALUES ('base_alunos', 'confirmada', 1, '2026-09-29')"
            )
        downgrade(revision="base")  # desce tudo...
        upgrade()  # ...e sobe de novo
        upgrade()  # rodar de novo não faz nada
        db.engine.dispose()

    with sqlite3.connect(arquivo) as conexao:
        assert conexao.execute("PRAGMA foreign_key_check").fetchall() == []
        assert not conexao.execute("SELECT name FROM sqlite_master WHERE name LIKE '_alembic_tmp%'").fetchall()


def test_migracao_nova_preserva_os_dados(tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKLIST_DADOS", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()
    with app.app_context():
        upgrade(revision="c182388d0923")
        with db.engine.begin() as conexao:
            conexao.exec_driver_sql(
                "INSERT INTO usuario (nome, email, papel, ativo, criado_em, atualizado_em) "
                "VALUES ('Pessoa', 'p@exemplo.test', 'consultor', 1, '2026-09-29', '2026-09-29')"
            )
            conexao.exec_driver_sql(
                "INSERT INTO importacao (tipo, situacao, iniciada_por_id, iniciada_em) VALUES ('checklist', 'previa', 1, '2026-09-29')"
            )
        upgrade()
        with db.engine.connect() as conexao:
            assert conexao.exec_driver_sql("SELECT nome, visao_fila FROM usuario").fetchall() == [("Pessoa", "lista")]
            assert conexao.exec_driver_sql("SELECT iniciada_por_id FROM importacao").scalar() == 1
        db.engine.dispose()
