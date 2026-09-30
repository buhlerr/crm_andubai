"""Servidor de produção (Windows), com waitress.

No servidor, uma tarefa agendada do Windows roda este arquivo quando a máquina
liga (veja instalar/LEIAME.md). Se o servidor web cair, ele volta sozinho em
10 segundos. Logs em <dados>/logs/servidor.log.

Pasta de dados: CHECKLIST_DADOS ou, se não definida, a pasta "dados" ao lado
da pasta do código (C:\\ChecklistEgali\\app -> C:\\ChecklistEgali\\dados).
"""

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_de_dados_padrao() -> str | None:
    candidata = os.path.join(os.path.dirname(AQUI), "dados")
    return candidata if os.path.isdir(candidata) else None


def configurar_logs(pasta_dados: str) -> logging.Logger:
    pasta_logs = os.path.join(pasta_dados, "logs")
    os.makedirs(pasta_logs, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    arquivo = RotatingFileHandler(os.path.join(pasta_logs, "servidor.log"), maxBytes=5_000_000, backupCount=10, encoding="utf-8")
    arquivo.setFormatter(formato)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(arquivo)
    if sys.stdout is not None:
        tela = logging.StreamHandler(sys.stdout)
        tela.setFormatter(formato)
        raiz.addHandler(tela)
    return logging.getLogger("checklist")


def main() -> None:
    if not os.environ.get("CHECKLIST_DADOS") and pasta_de_dados_padrao():
        os.environ["CHECKLIST_DADOS"] = pasta_de_dados_padrao()
    sys.path.insert(0, AQUI)

    from waitress import serve

    from app import CHAVE_PADRAO, create_app

    app = create_app()
    log = configurar_logs(app.instance_path)
    if app.config["SECRET_KEY"] == CHAVE_PADRAO:
        log.error("SECRET_KEY está com o valor padrão. Defina no config.py da pasta de dados (o instalador gera um).")
        sys.exit(1)
    if app.config.get("LOGIN_PROVISORIO") and not app.config.get("SENHA_PROVISORIA"):
        log.error("Login provisório sem SENHA_PROVISORIA: qualquer pessoa da rede entraria. Defina no config.py.")
        sys.exit(1)

    host, porta = app.config["SERVIDOR_HOST"], app.config["SERVIDOR_PORTA"]
    while True:
        try:
            log.info("Iniciando em http://%s:%s (dados em %s)", host, porta, app.instance_path)
            serve(app, host=host, port=porta, threads=app.config["SERVIDOR_THREADS"], channel_timeout=300, ident="checklist")
            log.info("Servidor parou.")
            return
        except Exception:
            log.exception("O servidor caiu. Reiniciando em 10 segundos.")
            time.sleep(10)


if __name__ == "__main__":
    main()
