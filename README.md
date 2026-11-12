# CRM Checklist Pós-Venda (Andubai)

Sistema de gestão e acompanhamento de tarefas pós-venda para consultores e equipe de atendimento, alimentado por uma única importação: o relatório de checklist do TM (procedimentos finalizados e em aberto).

---

## 🚀 Principais Funcionalidades

- **Autenticação Individual e Gestão de Acessos:**
  - Login individual por e-mail e senha com hash seguro (`PBKDF2-SHA256`).
  - Primeiro acesso facilitado com fluxo de definição de senha para consultores.
  - Rate-limiting integrado contra ataques de força bruta no login.
  - Painel de administração para controle de usuários e papéis (`admin`, `consultor`, `estagiário`).
- **Filas de Atendimento e Organização Avançada:**
  - Minha Fila, Fila da Equipe e Visão por Consultor.
  - Visualizações em **Lista**, **Kanban**, **Quadro por Aluno (com expansão em dropdown)** e **Calendário**.
  - **Organizar por:** Agrupamento e ordenação flexível por data prevista, procedimento, visto, embarque, responsável ou status, com persistência da preferência por usuário.
  - **Tipos de Visto Normalizados:** Conversão de múltiplos vistos ("Turista - EUA,eTA - Canadá") em selos padronizados com suporte a filtros e busca.
  - **Concluídas (`/concluidas`):** Auditoria de itens concluídos no sistema ou baixados no checklist original.
  - **Para Lançar na Egali (`/para-lancar`):** Fila de pendências concluídas localmente que precisam de baixa no sistema da Egali com botão "Lancei na Egali" e contador no menu lateral.
- **Módulo de Pautas TM:**
  - Importação de pautas de comunicação interna (CSV/MHTML do TM) com preservação perpétua de observações e histórico da unidade AN e Dubai.
- **Acompanhamento do Aluno:**
  - Cálculo de "Andamento até o embarque" em percentual estimado.
  - Registro de observações internas de NEG e histórico de alterações com autoria.
- **Mecanismo de Importação Inteligente:**
  - Importação única do relatório de checklist do TM (CSV): cria alunos, programas e tarefas e atualiza o painel RSA. O leitor de Excel via Calamine (`python-calamine`) continua no projeto, mas a planilha semanal não é mais importada.
  - Importação de relatórios CSV de checklist exportados da Egali com prévia antes da confirmação.
  - Identificação de tarefas fora do período de corte da exportação.

---

## 🛠️ Stack Tecnológica

- **Backend:** Python 3.12+ / Flask 3.x com SQLAlchemy 2.x
- **Banco de Dados:** SQLite 3 com WAL habilitado e migrações versionadas via Flask-Migrate (Alembic)
- **Servidores WSGI:** `gunicorn` (produção Linux/Docker) e `waitress` (Windows)
- **Leitura de Planilhas:** `calamine` (`python-calamine`) com fallback `openpyxl`
- **Frontend:** Jinja2 templates, CSS puro moderno e responsivo sem frameworks pesados
- **Deploy & Infraestrutura:** Docker / Docker Compose / LXC Proxmox VE / Túnel Pangolin ZTNA

---

## 📦 Como Rodar o Projeto

### Opção 1: Via Docker Compose (Produção / Servidores)

1. Clone o repositório:
   ```bash
   git clone https://github.com/buhlerr/crm_andubai.git
   cd crm_andubai
   ```

2. Suba o container com a imagem publicada no registro do GitHub (`ghcr.io/buhlerr/crm_andubai`, gerada a cada merge na `master`). O pacote é privado: entre uma vez com um token que tenha a permissão `read:packages`:
   ```bash
   docker login ghcr.io -u <usuário do GitHub>
   docker compose pull
   docker compose up -d
   ```
   Para atualizar depois de um merge, repita `docker compose pull` e `docker compose up -d`. A migração do banco roda sozinha ao subir. Para fixar uma versão, use `CRM_IMAGEM=ghcr.io/buhlerr/crm_andubai:sha-<commit>`.
   Sem acesso ao registro, dá para gerar a imagem na própria máquina com `docker compose up -d --build`.

3. Acesse em `http://localhost:8080`.

Para criar o primeiro administrador via CLI no Docker:
```bash
docker exec -it crm_andubai flask criar-admin
```

---

### Opção 2: Execução Local (Windows)

1. Certifique-se de ter o **Python 3.12+** instalado.
2. Dê dois cliques no arquivo `iniciar.cmd` (ou execute `scripts/iniciar_local.ps1`).
3. O script criará o ambiente virtual `.venv` se necessário, atualizará o banco via migrações e iniciará a aplicação na porta **5000** (`http://127.0.0.1:5000`).

---

### Opção 3: Execução Local / Servidor (Linux)

1. Dê permissão de execução ao script:
   ```bash
   chmod +x iniciar_linux.sh
   ./iniciar_linux.sh
   ```

---

## ⚙️ Variáveis de Ambiente e Configurações

Copie o arquivo `config.py.exemplo` para `instance/config.py` ou declare as variáveis no ambiente:

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `SECRET_KEY` | *(persistida em secret_key)* | Chave de assinatura criptográfica das sessões. Se omitida, gerada automaticamente em `<CHECKLIST_DADOS>/secret_key`. A aplicação recusa valores padrão inseguros. |
| `CHECKLIST_DADOS` | `instance` | Diretório onde o banco `checklist.db`, chave e backups são mantidos |
| `SERVIDOR_HOST` | `0.0.0.0` | IP de escuta do servidor WSGI |
| `SERVIDOR_PORTA` | `8080` (Docker) / `5000` (Local) | Porta HTTP do servidor |
| `SERVIDOR_THREADS` | `8` | Quantidade de threads de atendimento simultâneas |
| `ATRAS_DE_PROXY` | `0` | Se ativo (`1`), injeta headers de segurança `Strict-Transport-Security` (HSTS) e habilita `ProxyFix` |
| `LOGIN_PROVISORIO` | `0` | Se ativo (`1`), permite que usuários sem senha usem a `SENHA_PROVISORIA` da equipe para transição e cadastro de senha individual (bloqueado para admin). |
| `SENHA_PROVISORIA` | `None` | Senha da equipe obrigatória quando `LOGIN_PROVISORIO=1`. Não possui valor padrão no código. |

---

## 🛡️ Segurança, Conformidade e LGPD

- **Publicação Externa & ZTNA:** O acesso externo através de `https://crm.vbr.dpdns.org` é intermediado por infraestrutura de Zero Trust Network Access (ZTNA via Pangolin/Traefik com isolamento de rede), com aprovação formal da administração da unidade para fins operacionais da equipe.
- **Cabeçalhos de Segurança HTTP:** Todas as respostas injetam `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` e `Strict-Transport-Security` quando `ATRAS_DE_PROXY=1`.
- **Proteção de Dados Pessoais:** O repositório segue a regra estrita de não versionar arquivos com dados reais de alunos e colaboradores. Testes automatizados utilizam exclusivamente dados fictícios.

---

## 🧰 Comandos de Manutenção (Flask CLI)

O sistema possui uma interface de linha de comando integrada para diagnósticos e tarefas administrativas:

```bash
# Diagnóstico completo do banco, permissões e leitor de planilhas
flask diagnostico

# Gerar backup imediato do banco SQLite para a pasta backups
flask backup --manter 30

# Criar ou promover um usuário a Administrador
flask criar-admin

# Redefinir senha de um usuário
flask redefinir-senha usuario@egali.com.br

# Listar todos os usuários cadastrados e status
flask usuarios listar

# Executar migrações pendentes do banco
flask db upgrade

# Rodar a suíte completa de testes (270 testes)
pytest
```
