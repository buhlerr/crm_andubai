# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [2.1.0] - 2026-10-01

### Adicionado
- **Filtro de Vistos:** Identificação e selos visuais com cores distintas para vistos consulares (`app/vistos.py`).
- **Organização Flexível de Tarefas:** Dropdowns de navegação para alternar entre visão tabular e kanban por aluno/consultor.
- **Novas Telas de Operação:**
  - `/concluidas`: Visão de histórico de tarefas finalizadas com filtros por período.
  - `/para-lancar`: Fila de tarefas concluídas aguardando lançamento no sistema Egali.
- **Ações Rápidas em Lote:** Recursos para marcar lançamento de tarefas e inserção de anotações em bloco.
- **Segurança Reforçada:**
  - Geração automática e persistência de `SECRET_KEY` criptográfica forte em `instance/secret_key`.
  - Rate limiting no endpoint de login `/entrar` (10 tentativas a cada 15 minutos por IP/usuário).
  - Cabeçalhos de segurança HTTP (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `HSTS`).
  - Bloqueio definitivo do login provisório para contas de Administrador.
- **Suíte de Testes:** 270 testes automatizados cobrindo autenticação, migrações, importações, pautas TM e visualizações web.

### Modificado
- **Migrações:** Migração `ec1a54ac4fe8` tornando a criação das tabelas de pautas e campos de senha idempotentes.
- **Dockerfile:** Atualização da rotina de inicialização para falhar imediatamente se a migração do banco falhar.
- **Layout:** Barra de navegação com menus dropdown dinâmicos preservando atalhos de Pautas TM e autoatendimento de senha.

### Segurança e LGPD
- Remoção e bloqueio via `.gitignore` de planilhas e exportações reais de alunos e colaboradores.
- Adição de fixtures higienizadas e fictícias em `tests/amostras/`.
