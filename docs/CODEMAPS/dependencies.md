<!-- Generated: 2026-11-12 | Files scanned: 179 | Token estimate: ~400 -->
# Dependencies

## Python (requirements.txt, Python 3.12+)
Flask>=3.1               web framework, app factory
Flask-SQLAlchemy>=3.1    ORM (SQLAlchemy 2.x)
Flask-Migrate>=4.0       Alembic migrations (render_as_batch=True)
waitress>=3.0            WSGI server on Windows (servidor.py)
gunicorn>=23.0           WSGI server on Linux/Docker (non-win32)
python-calamine>=0.8.0   fast xlsx reader (Rust); openpyxl used as fallback if present
pywin32>=306             win32 only
pytest>=8                test suite (tests/, 304 cases as of 2026-11-12, pytest.ini)

## External systems
Egali (corporate system) — no API; data arrives as file exports:
  - TM checklist report (CSV, finalizados + em aberto) — the only student/task import
  - weekly student spreadsheet (xlsx) — no longer imported (reader kept)
  - Pautas TM export (CSV / HTML / MHTML)
  Team marks "lançada na Egali" manually after re-entering work there.
Uploaded HTML dashboards: Painel VEG, RSA pages (stored in data dir, data injected server-side).
Reverse proxy (optional): Nginx/Caddy/Cloudflare/IIS → ATRAS_DE_PROXY=1 enables ProxyFix + HSTS.

## Infra
Docker (python:3.12-slim), docker-compose volume crm_dados:/dados
systemd unit: checklist.service
SQLite only (DATABASE_URL may override)

## Env vars
CHECKLIST_DADOS, DATABASE_URL, SECRET_KEY, LOGIN_PROVISORIO, SENHA_PROVISORIA,
ATRAS_DE_PROXY, SERVIDOR_HOST, SERVIDOR_PORTA, SERVIDOR_THREADS, PAUTAS_MEMBROS_UNIDADE
