"""Backup do banco e diagnóstico da instalação (usados pela TI no servidor)."""

import glob
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime

from flask import Flask

from app import CHAVE_PADRAO, PASTA_PROJETO
from app.extensions import db


class ErroManutencao(Exception):
    pass


def _arquivo_sqlite() -> str:
    url = db.engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ErroManutencao("O backup automático é só para o banco SQLite. No Postgres, use o pg_dump.")
    return url.database


def fazer_backup(app: Flask, manter: int | None = None) -> str:
    """Cópia consistente do banco (API de backup do SQLite: funciona com o sistema
    no ar) em <dados>/backups. Mantém só os `manter` mais recentes."""
    manter = manter or app.config["BACKUPS_MANTER"]
    origem = _arquivo_sqlite()
    pasta = os.path.join(app.instance_path, "backups")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, f"checklist-{datetime.now():%Y%m%d-%H%M%S-%f}.db")
    fonte, copia = sqlite3.connect(origem), sqlite3.connect(destino)
    try:
        fonte.backup(copia)
    finally:
        copia.close()
        fonte.close()
    for antigo in sorted(glob.glob(os.path.join(pasta, "checklist-*.db")))[:-manter]:
        os.remove(antigo)
    return destino


@dataclass
class Verificacao:
    ok: bool | None  # None = aviso (funciona, mas precisa de atenção)
    nome: str
    detalhe: str


def diagnosticar(app: Flask, planilha: str | None = None, testar_excel: bool = True) -> list[Verificacao]:
    resultado = []

    # Banco e migrações
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        with db.engine.connect() as conexao:
            atual = MigrationContext.configure(conexao).get_current_revision()
        config = Config()
        config.set_main_option("script_location", os.path.join(PASTA_PROJETO, "migrations"))
        mais_nova = ScriptDirectory.from_config(config).get_current_head()
        url = db.engine.url
        onde = url.database if url.get_backend_name() == "sqlite" else url.render_as_string(hide_password=True)
        if atual == mais_nova:
            resultado.append(Verificacao(True, "Banco de dados", f"{onde} (versão {atual})"))
        else:
            resultado.append(Verificacao(False, "Banco de dados", f"versão {atual}, esperada {mais_nova}. Rode: flask db upgrade"))
    except Exception as erro:
        resultado.append(Verificacao(False, "Banco de dados", f"não abriu: {erro}"))

    # Pasta de dados
    try:
        with tempfile.NamedTemporaryFile(dir=app.instance_path, prefix="teste-", delete=True):
            pass
        resultado.append(Verificacao(True, "Pasta de dados", app.instance_path))
    except OSError as erro:
        resultado.append(Verificacao(False, "Pasta de dados", f"sem permissão de escrita em {app.instance_path}: {erro}"))
    if "onedrive" in app.instance_path.lower():
        resultado.append(Verificacao(None, "Pasta de dados no OneDrive", "a sincronização pode corromper o banco. No servidor, use uma pasta local."))

    # Segurança
    if app.config["SECRET_KEY"] == CHAVE_PADRAO:
        resultado.append(Verificacao(False, "Chave secreta", "está com o valor padrão. Defina SECRET_KEY no config.py."))
    elif os.path.exists(os.path.join(app.instance_path, "secret_key")) and not os.environ.get("SECRET_KEY"):
        resultado.append(Verificacao(True, "Chave secreta", "gerada pelo sistema e guardada na pasta de dados (secret_key)"))
    else:
        resultado.append(Verificacao(True, "Chave secreta", "configurada"))
    if app.config.get("LOGIN_PROVISORIO"):
        if app.config.get("SENHA_PROVISORIA"):
            resultado.append(Verificacao(None, "Login", "transição ligada: quem ainda não tem senha entra com a da equipe "
                                         "(nunca admin). Desligue LOGIN_PROVISORIO quando todos tiverem senha."))
        else:
            resultado.append(Verificacao(False, "Login", "transição ligada SEM senha da equipe. Defina SENHA_PROVISORIA ou desligue LOGIN_PROVISORIO."))
    else:
        resultado.append(Verificacao(True, "Login", "e-mail e senha individual"))
    if not app.config.get("ATRAS_DE_PROXY"):
        resultado.append(Verificacao(None, "HTTPS", "sem proxy (IIS) na frente: as senhas trafegam sem criptografia na rede."))

    # Usuários
    try:
        from app.models import Papel, Usuario

        admins = db.session.execute(db.select(db.func.count()).select_from(Usuario).filter_by(papel=Papel.ADMIN, ativo=True)).scalar_one()
        resultado.append(Verificacao(admins > 0, "Administradores", f"{admins} ativo(s)" if admins else "nenhum: cadastre com flask usuarios adicionar ... --papel admin"))
    except Exception as erro:
        resultado.append(Verificacao(False, "Administradores", f"não deu para conferir: {erro}"))

    # Leitor de Excel (importação da planilha semanal)
    if testar_excel:
        try:
            import python_calamine

            resultado.append(
                Verificacao(
                    True,
                    "Leitor de planilhas",
                    f"python-calamine disponível (multiplataforma Linux/Windows)",
                )
            )
        except Exception as erro:
            com_ok = False
            if sys.platform == "win32":
                try:
                    import pythoncom
                    import win32com.client as win32

                    pythoncom.CoInitialize()
                    try:
                        excel = win32.DispatchEx("Excel.Application")
                        versao = excel.Version
                        excel.Quit()
                        com_ok = True
                    finally:
                        pythoncom.CoUninitialize()
                    resultado.append(Verificacao(True, "Excel (COM)", f"abre pela automação (versão {versao})"))
                except Exception:
                    pass
            if not com_ok:
                resultado.append(
                    Verificacao(
                        False,
                        "Leitor de planilhas",
                        f"python-calamine não disponível: {erro}. Instale com 'pip install python-calamine'.",
                    )
                )

    if planilha:
        try:
            from app.importacao.base_alunos import COL_COMPRAS, NOME_ABA
            from app.importacao.leitor_excel import ler_planilha

            linhas = ler_planilha(planilha, NOME_ABA, colunas_texto=(COL_COMPRAS,))
            com_programa = sum(1 for l in linhas if l["valores"].get("programa_id") is not None)
            resultado.append(Verificacao(True, "Leitura da planilha", f"{com_programa} linha(s) com programa_id em {os.path.basename(planilha)}"))
        except Exception as erro:
            resultado.append(Verificacao(False, "Leitura da planilha", str(erro)))

    return resultado
