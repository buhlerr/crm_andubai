# Instruções para Agentes de IA (AGENTS.md)

Este arquivo define os padrões, regras, regras de negócio e convenções que qualquer agente autônomo de IA deve seguir rigorosamente ao manter este repositório.

---

## 🛠️ Stack e Padrões de Engenharia
- **Linguagem:** Python 3.12+
- **Framework Web:** Flask 3.x com Application Factory pattern (`create_app()` em [`app/__init__.py`](file:///d:/dev/crm_andubai/app/__init__.py)).
- **ORM / Banco:** SQLAlchemy 2.x com `db.session`. O SQLite fica por padrão em `instance/checklist.db` ou no caminho definido por `CHECKLIST_DADOS`.
- **Migrações:** Flask-Migrate (Alembic) em `migrations/versions/`. Toda migração deve ser batch (`render_as_batch=True`), usar `server_default=sa.false()` para booleanos e ser idempotente.
- **Frontend:** Jinja2 + CSS puro em [`app/static/estilo.css`](file:///d:/dev/crm_andubai/app/static/estilo.css). Não adicione Tailwind ou Bootstrap sem pedido explícito do usuário.
- **Servidores WSGI:** `gunicorn` no ambiente Linux/Docker e `waitress` em instalações Windows (`servidor.py`).
- **Leitura de Planilhas:** `calamine` (`python-calamine`) com fallback `openpyxl`. Nunca dependa de automação COM do Excel do Windows.

---

## 🏛️ Diferenças de Propósito em Relação ao Sistema Original (NÃO REVERTER)
O repositório `crm_andubai` possui decisões arquiteturais deliberadas que diferem do pacote legado da Egali:
1. **Ambiente Multiplataforma (Linux/Docker/Systemd):** Container Docker com Alpine/Debian Slim em vez de dependência estrita de Windows Server e IIS.
2. **Leitor de Excel com Calamine:** Leitura de planilhas em milissegundos via biblioteca Rust (`python-calamine`), sem depender do executável `excel.exe`.
3. **Autenticação Local por E-mail e Senha:** Hash com PBKDF2/Werkzeug, tela de login `/entrar`, autoatendimento em `/trocar-senha`, rate-limiting contra brute force e headers de segurança HTTP (`HSTS`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`). O login provisório de transição (`LOGIN_PROVISORIO=1`) é opcional e bloqueado para administradores.
4. **Módulo de Pautas TM:** Sistema completo de gestão de pautas internas da unidade AN e Dubai ([`app/models/pautas.py`](file:///d:/dev/crm_andubai/app/models/pautas.py), [`app/web/pautas.py`](file:///d:/dev/crm_andubai/app/web/pautas.py), [`app/importacao/pautas.py`](file:///d:/dev/crm_andubai/app/importacao/pautas.py)), mapeamento de setores e histórico preservado entre sincronizações.

---

## 📋 Regras de Negócio Inegociáveis (Baseadas no CLAUDE.md)
1. **Correspondência Sempre por ID:** Alunos, compras, programas e itens de checklist devem ser associados exclusivamente pelos identificadores externos da Egali (`aluno_id_egali`, `compra_id_egali`, `programa_id_egali`, `item_checklist_egali`), **nunca por nome**.
2. **A Importação Nunca Sobrescreve o Trabalho da Equipe:** Campos preenchidos pela equipe no CRM (`status`, `responsavel_manual_id`, `data_planejada`, `anotacoes`) são intocáveis pela importação. A importação só atualiza campos de espelho da Egali (`prazo_egali`, `status_egali`, `obs_egali`, `compras`).
3. **Prévia Obrigatória e Idempotência:** Toda rotina de importação gera uma prévia para conferência humana antes da confirmação e deve poder ser executada múltiplas vezes sem duplicar registros.
4. **NEG Separada de Anotações:** O campo `obs_egali` (NEG da Egali) é estritamente separado das anotações internas da equipe (`Anotacao`). Apenas o NEG é considerado como justificativa formal de atraso corporativo.
5. **Data Fixa vs Data Planejada:** O `prazo_egali` é a data do procedimento oficial e é o único critério que define atraso da tarefa. A `data_planejada` é a estimativa operacional do consultor e não altera o cálculo do atraso.
6. **Interface em Português Claro:** Todo o sistema e suas mensagens de erro e validação devem ser apresentados em português sem jargões técnicos para a equipe de atendimento.

---

## 🛡️ Segurança e LGPD
- **Dados Fictícios em Testes:** É terminantemente proibido versionar planilhas reais, CSVs de exportação ou dados pessoais de colaboradores/alunos. Testes devem utilizar exclusivamente dados fictícios em `tests/amostras/`.
- **Credenciais e Segredos:** Nunca commitar arquivos `.env`, `config.py`, chaves criptográficas (`secret_key`) ou bancos `.db`/`.sqlite`. O `.gitignore` bloqueia todos esses formatos.
- **Gestão de Chave:** Em produção, se `SECRET_KEY` não for informada no ambiente ou no `config.py`, o sistema gera e persiste automaticamente uma chave criptográfica forte em `<CHECKLIST_DADOS>/secret_key`, recusando a chave padrão `dev-troque-em-producao`.

---

## 🧪 Como Rodar os Testes
```bash
pytest
```
Todos os **270 testes automatizados** em `tests/` devem passar com 100% de sucesso a cada modificação no código.
