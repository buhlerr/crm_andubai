# Instruções para agentes de IA (AGENTS.md)

Padrões, regras e convenções para qualquer agente que mantenha este repositório. As regras de negócio
completas do sistema de checklist (de onde este projeto saiu) estão em `docs/REGRAS_CHECKLIST.md`: leia
antes de mexer em importação, filas, tarefas ou andamento. As das pautas estão em `REGRAS_PAUTAS.md`.

## Stack e padrões
- **Linguagem:** Python 3.12+.
- **Web:** Flask 3.x com application factory (`create_app()` em `app/__init__.py`).
- **Banco:** SQLAlchemy 2.x com `db.session`. SQLite em `instance/checklist.db` ou em `CHECKLIST_DADOS`.
- **Migrações:** Alembic (Flask-Migrate) com `render_as_batch`.
  - Toda mudança de modelo ganha migração; nada de `ALTER TABLE` em código.
  - Boolean com `server_default=sa.false()`, nunca `sa.text('0')`.
  - Nomes de constraint com `op.f()`.
  - `flask db heads` tem de mostrar uma cabeça só.
- **Frontend:** Jinja2 e CSS puro em `app/static/estilo.css`, com cores só pelas variáveis do `:root`. Sem Tailwind nem Bootstrap sem pedido explícito.
- **Textos da interface e mensagens de erro:** em português, sem jargão, dizendo o que fazer.

## Segurança e dados (não negociável)
- **Nunca versione dados reais:**
  - planilhas, CSVs ou páginas salvas do TM ou do SharePoint;
  - bancos, `config.py`, `.env`, `secret_key`.
  O `.gitignore` bloqueia esses formatos. Amostras de teste ficam em `tests/amostras/` e são **fictícias**.
- **Nomes de colegas e alunos** não entram no código nem nos testes. Listas de pessoas vêm da configuração (ex.: `PAUTAS_MEMBROS_UNIDADE`) ou do banco.
- **Chave das sessões:** sem `SECRET_KEY`, o sistema gera uma e guarda em `<CHECKLIST_DADOS>/secret_key`. Ele **recusa subir** com chaves ou senhas que já foram publicadas (`VALORES_PROIBIDOS_SHA256`, em `app/__init__.py`). Não ponha valores padrão de segredo em `docker-compose.yml`, `checklist.service` ou nos exemplos.
- **Login:** e-mail e senha individual, com mínimo de 10 caracteres (`SENHA_MINIMA`), e limite de tentativas no `/entrar`.
  - A transição com a senha da equipe só funciona com `LOGIN_PROVISORIO=1`, e **nunca para administradores**.
- **Rotas:** toda rota com dado exige `@login_obrigatorio`; importar arquivos e mexer em cadastros exige `@admin_obrigatorio`.
- **POST e CSRF:** todo POST passa pelo token CSRF, como campo `csrf` nos formulários ou cabeçalho `X-CSRF-Token` em `fetch`.
- **Texto do usuário no JavaScript:** entra com `textContent`, nunca com `innerHTML`.

## Regras de negócio que valem para qualquer mudança
- Correspondência sempre pelos IDs da Egali (`programa_id`, `aluno_id`, `#` do item), nunca pelo nome.
- A importação nunca sobrescreve o trabalho feito no sistema: status, responsável trocado à mão, data planejada e anotações.
- Toda importação tem **prévia** antes de gravar e é idempotente: rodar duas vezes não duplica.
- A NEG vem da Egali e fica separada das observações do sistema. Só a NEG conta como justificativa.
- A data do procedimento (Egali) é fixa e é ela que define o atraso. A data planejada não muda o atraso.
- "Para lançar na Egali": o que foi concluído ou anotado aqui fica na lista até o item sumir do CSV seguinte.

## Diferenças de propósito em relação ao sistema original
Estas diferenças são decisões, e não esquecimentos. Não "corrija de volta":
- Linux/Docker, gunicorn e túnel em vez de IIS e Windows.
- Excel lido com calamine em vez de automação COM do Excel.
- Login por e-mail e senha em vez de Microsoft 365.
- Módulo de Pautas TM, que só existe aqui.

## Testes
```bash
pytest
```
Os 271 testes precisam passar. Use só dados fictícios. Testes que gravam arquivo usam uma pasta
temporária (`tmp_path`), nunca a `instance/` do projeto. `tests/test_migracoes.py` roda todas as
migrações num banco com dados: não apague.
