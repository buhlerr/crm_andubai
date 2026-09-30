# Instruções para Agentes de IA (AGENTS.md)

Este arquivo define os padrões, regras e convenções que qualquer agente autônomo de IA deve seguir ao manter este repositório.

## 🛠️ Stack e Padrões
- **Linguagem:** Python 3.12+
- **Framework Web:** Flask 3.x com Application Factory pattern (`create_app()` em `app/__init__.py`).
- **ORM / Banco:** SQLAlchemy 2.x com `db.session`. O SQLite fica por padrão em `instance/checklist.db` ou `CHECKLIST_DADOS`.
- **Validações e Testes:** Sempre rodar `pytest` após qualquer modificação em modelos, autenticação ou leitores de importação.
- **Frontend:** Jinja2 + CSS puro em `app/static/estilo.css`. Não adicione Tailwind ou Bootstrap sem pedido explícito.

## 🛡️ Segurança e .gitignore
- Nunca commite o banco de dados `checklist.db` nem arquivos de credenciais `.env` ou `config.py`.
- O arquivo `.gitignore` bloqueia qualquer arquivo `.db`, `.sqlite`, `.zip`, `.key`, `.pem` e caches.
- Use `instance/.gitkeep` para manter a estrutura de pastas no repositório.

## 🧪 Como rodar os testes
```bash
pytest
```
Todos os 10 testes em `tests/` devem passar com 100% de sucesso.
