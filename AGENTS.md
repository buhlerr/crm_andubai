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

Para o detalhamento exaustivo de cada entidade, importações e regras de negócio do Checklist, consulte [`docs/REGRAS_CHECKLIST.md`](file:///d:/dev/crm_andubai/docs/REGRAS_CHECKLIST.md) e [`REGRAS_PAUTAS.md`](file:///d:/dev/crm_andubai/REGRAS_PAUTAS.md).

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
Todos os **271 testes automatizados** em `tests/` devem passar com 100% de sucesso a cada modificação no código.

---

## 🤝 Protocolo de Colaboração Multi-Agente e Concorrência

Para garantir que múltiplos desenvolvedores e agentes autônomos de IA (Antigravity, Cursor, Claude Code, Copilot) colaborem sem retrabalho, divergência no Git ou quebra de subsistemas:

1. **Sincronização Prévia Obrigatória:** Antes de iniciar qualquer tarefa ou criar uma branch de feature, execute sempre `git pull origin master` e baseie seu trabalho no commit mais recente da `master`.
2. **Linearidade e Idempotência de Migrações:**
   - Antes de criar nova migração, verifique `flask db heads`.
   - Nunca crie migrações concorrentes com o mesmo `down_revision`.
   - Toda migração deve ser batch (`render_as_batch=True`), usar `server_default=sa.false()` para booleanos e inspecionar tabelas/colunas existentes com `inspect(op.get_bind())` para garantir idempotência sem falhar em bancos já atualizados.
3. **Módulo de Pautas TM é Intocável:** O módulo de Pautas TM (`app/models/pautas.py`, `app/web/pautas.py`, `app/dados/pautas_sla.csv`) e seus links na barra de navegação são exclusivos da unidade AN e Dubai. Nenhum agente tem permissão para remover, desativar ou ocultar rotas de pautas.
4. **Zero Nomes Hardcoded no Código (LGPD):** Nunca insira nomes reais de colaboradores ou alunos em arquivos de código, scripts ou commits. Use a variável de ambiente `PAUTAS_MEMBROS_UNIDADE` ou cadastros no banco. Em testes, use exclusivamente nomes fictícios em `tests/amostras/`.
5. **Portão de Testes Não Negociável:** A contagem de testes só pode aumentar ou permanecer estável (mínimo de **271 testes**). É proibido deletar ou desativar testes para mascarar falhas.
6. **Registro no CHANGELOG.md:** Qualquer alteração funcional, de tela, banco ou segurança deve ser documentada no [`CHANGELOG.md`](file:///d:/dev/crm_andubai/CHANGELOG.md).
