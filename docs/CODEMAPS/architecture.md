<!-- Generated: 2026-11-12 | Files scanned: 179 | Token estimate: ~750 -->
# Architecture

Single Flask app (server-rendered monolith), SQLite, PT-BR UI. CRM/checklist for AN + Dubai unit:
mirrors Egali exports (TM checklist report = sole student/task import; Pautas TM) into tasks the team works on.
Rules of record: `AGENTS.md`, `docs/REGRAS_CHECKLIST.md`, `REGRAS_PAUTAS.md`. Human overview: `ESTRUTURA.md`.
Sibling codemaps: backend.md · frontend.md · data.md · dependencies.md

## Entry points
wsgi.py            → create_app()  (gunicorn, Docker/Linux)
servidor.py        → waitress serve() (Windows; logs in data dir)
app/__init__.py    → create_app(config) : config → security check → db/migrate → cli → web
app/cli.py         → `flask catalogo|backup|diagnostico|criar-admin|redefinir-senha|usuarios|importar checklist`
iniciar.cmd / iniciar_linux.sh / scripts/iniciar_local.ps1 / checklist.service (systemd)

## Layers
```
Browser (Jinja2 + estilo.css + lateral.js)
   │  POST needs CSRF (form "csrf" / header X-CSRF-Token)
app/web/*  blueprints ── login_obrigatorio / admin_obrigatorio (app/web/auth.py)
   │
   ├─ app/consultas.py      read side: filters, queues, kanban, counts
   ├─ app/acoes_tarefa.py   write side: status/owner/planned date/notes + HistoricoTarefa
   ├─ app/andamento.py      program & visa progress calc
   ├─ app/importacao/*      preview → confirm pipelines (base, checklist, pautas)
   ├─ app/painel_veg.py / app/rsa.py  uploaded HTML dashboards, data injected
   └─ app/manutencao.py     backup + diagnostics
   │
app/models/*  SQLAlchemy 2.x  ──►  <CHECKLIST_DADOS>/checklist.db (WAL, FK on)
```

## Import data flow
```
TM checklist CSV ─ leitor_csv (header found by "#" col) ─► checklist.interpretar() → criar_previa()
  (finalizados + em aberto, ≤100 MB)                         Importacao(PREVIA)+Ocorrencias
                                                           human review /importacoes/<id>
                                                         └─► confirmar() → upsert by *_id_egali
                                                              Aluno, 1 Programa/aluno, Compra, Tarefa
                                                         └─► rsa_checklist.montar_base() → <data>/rsa/base.json
Pautas TM CSV/HTML ─ importacao/pautas.py ─► Pauta (+ SLA from app/dados/pautas_sla.csv)
```
Weekly xlsx (base_alunos.py + leitor_excel/calamine) is kept in code and tests but no longer imported.
Import only writes Egali-mirror fields (prazo_egali, status_egali, obs_egali, compras);
team fields (status, responsavel_manual_id, data_planejada, anotacoes) are never overwritten.

## Config precedence (last wins)
env (DATABASE_URL, SECRET_KEY, LOGIN_PROVISORIO, ATRAS_DE_PROXY, SERVIDOR_*) → <data>/config.py → dict (tests)
No SECRET_KEY → generated into <data>/secret_key. Known-leaked keys refused (SHA-256 denylist).

## Deploy
Dockerfile: python:3.12-slim → `flask db upgrade` → `flask catalogo carregar` → gunicorn -w 4 :8080
docker-compose: volume crm_dados:/dados (= CHECKLIST_DADOS)

## Do-not-remove (AGENTS.md)
Pautas TM module · PBKDF2 local auth · calamine reader
