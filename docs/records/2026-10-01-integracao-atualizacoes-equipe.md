# Registro de Intervenção: Integração das Atualizações da Equipe e Governança

- **Data / Hora:** 2026-10-01 16:30
- **Executor:** Antigravity AI Agent (Pair Programming com Vitor)
- **Ambiente:** IDE / Local / Docker Linux
- **Status:** Concluído com Sucesso (100% dos 271 testes passando)

---

## 1. Contexto & Motivação Técnica
Foram recebidas atualizações de código desenvolvidas colaborativamente pela colega Duda (em `atualizacoes_duda/atualizacao_crm_andubai` e na branch `atualizacao-01-10` / PR #3). O objetivo foi incorporar melhorias operacionais (filtros por vistos, organização de tarefas em dropdown, telas de tarefas concluídas e para lançar, tabela de SLA de pautas, validação de regras de negócio em `docs/REGRAS_CHECKLIST.md` e suíte de testes unitários) garantindo a preservação absoluta de decisões arquiteturais deliberadas do `crm_andubai`:
1. Módulo exclusivo de Pautas TM da unidade AN/Dubai.
2. Autenticação local robusta (PBKDF2/Werkzeug) com proteção contra força bruta e headers de segurança HTTP.
3. Leitor de planilhas de alta performance em Rust (`python-calamine`) sem dependência de automação COM do Excel.
4. Suporte nativo a containers Docker Linux e SQLite em modo WAL.

---

## 2. Roteiro Executado em 6 Etapas

### Etapa 1: Dados Reais e LGPD (`be2a882`)
- **Ação:** Identificação e desindexação do Git de arquivos sensíveis contendo dados reais de alunos e colaboradores (`*.csv`, `*.mhtml`, `*.txt`).
- **Segurança:** Atualização do `.gitignore` para bloquear extensões de planilhas e exportações.
- **Amostras:** Criação de fixtures fictícias e higienizadas em `tests/amostras/` para garantir repetibilidade dos testes sem violar a LGPD.

### Etapa 2: Segurança, Login e Sessões (`5785633`)
- **SECRET_KEY:** Implementação de geração automática e persistência criptográfica em `<CHECKLIST_DADOS>/secret_key` quando não informada no ambiente, recusando explicitamente a chave default insegura e checando hashes de segredos proibidos (`VALORES_PROIBIDOS_SHA256`).
- **Transição de Login:** Senhas provisórias padrão removidas dos manifestos; bloqueio estrito de login provisório para perfis administradores; rate limiting no endpoint `/entrar` (10 tentativas por IP/login a cada 15 min); imposição de senha mínima de 10 dígitos.
- **Headers HTTP:** Injeção global de `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` e `Strict-Transport-Security` (quando atrás de proxy reverso).

### Etapa 3: Banco de Dados e Migrações (`70e94e7`)
- **Migrações:** Incorporação da migração `a750f5567f2c` e criação da migração idempotente `ec1a54ac4fe8` adicionando `senha_hash` e as tabelas de Pautas TM via `sa.inspect(op.get_bind())`.
- **Limpeza:** Remoção de `ALTER TABLE` manual na inicialização do SQLite em `app/__init__.py`.
- **Docker:** Atualização do `Dockerfile` para falhar o boot caso o `flask db upgrade` não conclua com êxito.

### Etapa 4: Funcionalidades de Negócio (`e0faf41`)
- **Vistos:** Criação de `app/vistos.py` com normalização de vistos em selos coloridos.
- **Ações em Lote:** Inclusão de `marcar_lancada` e `marcar_anotacao` em `app/acoes_tarefa.py`.
- **Consultas & Filtros:** Adição de enums de ordenação/agrupamento e telas dedicadas `/concluidas` e `/para-lancar`.
- **UI:** Menu em dropdown na barra de navegação preservando o acesso ao módulo de Pautas TM e autoatendimento de troca de senha.

### Etapa 5: Suíte Completa de Testes (`4208310`) e Unificação (`atualizacao-01-10`)
- **Integração:** Importação e centralização da suíte em `tests/` e incorporação de `app/dados/pautas_sla.csv` para cálculo de prazos nominais de pautas.
- **Ajustes:** Validação de CSRF para requisições de API JSON/fetch (`X-CSRF-Token`), parametrização de colaboradores da unidade via `PAUTAS_MEMBROS_UNIDADE` (zero nomes hardcoded no código).
- **Resultado:** **271 testes aprovados com 100% de sucesso** em 40.49s.

### Etapa 6: Documentação e Governança (`0dc513b` e subsequente)
- **AGENTS.md:** Atualização com as regras de negócio inegociáveis do `CLAUDE.md`, restrições negativas, ponte para `docs/REGRAS_CHECKLIST.md` e metas de qualidade.
- **README.md & ESTRUTURA.md:** Alinhamento de portas (5000 dev / 8080 prod), variáveis de ambiente e topologia de arquivos.
- **Interoperabilidade:** Criação de `.cursorrules` e `CLAUDE.md` padronizados para desenvolvimento colaborativo multi-IDE.

---

## 3. Critérios de Validação e Aceite
- [x] Repositório 100% limpo sem dados reais rastreados pelo Git.
- [x] Testes passando sem falhas: `pytest` -> `271 passed`.
- [x] Módulo de Pautas TM operacional com catálogo `pautas_sla.csv`.
- [x] Autenticação local por hash PBKDF2 com rate-limiting e bloqueio de segredos públicos preservada.
- [x] Migrações do banco de dados idempotentes e executáveis em SQLite/Docker.
- [x] Commits semânticos atômicos enviados com sucesso para a branch `master` no GitHub.
