# CRM Checklist Pós-Venda (Andubai)

Sistema de gestão e acompanhamento de tarefas pós-venda para consultores e equipe de atendimento, integrado a fluxos de importação de planilhas semanais e exportações da Egali.

---

## 🚀 Principais Funcionalidades

- **Autenticação Individual e Gestão de Acessos:**
  - Login individual por e-mail e senha com hash seguro (`PBKDF2-SHA256`).
  - Primeiro acesso facilitado com fluxo de definição de senha para consultores.
  - Painel de administração para controle de usuários e papéis (`admin`, `consultor`, `estagiário`).
- **Filas de Atendimento e Visualizações:**
  - Minha Fila, Fila da Equipe e Visão por Consultor.
  - Visualizações em **Lista**, **Kanban**, **Quadro por Aluno** e **Calendário**.
  - Filtros avançados por trilha, procedimento, atraso, público teen e datas.
- **Acompanhamento do Aluno:**
  - Cálculo de "Andamento até o embarque" em percentual estimado.
  - Registro de observações internas de NEG e histórico de alterações.
- **Mecanismo de Importação Inteligente:**
  - Importação de planilhas Excel (`.xlsx`, `.xlsb`, `.xls`) da Base de Alunos (utilizando leitor de alta performance com Calamine/Python-calamine).
  - Importação de relatórios CSV de checklist exportados da Egali.
  - Mapeamento automático de apelidos de consultores e resolução de nomes.

---

## 🛠️ Stack Tecnológica

- **Backend:** Python 3.12+ / Flask 3.x
- **Banco de Dados & ORM:** SQLite 3 (local) / SQLAlchemy 2.x com migrações via Flask-Migrate (Alembic)
- **Servidor WSGI / Produção:** Waitress (multithreaded de alta performance)
- **Leitura de Planilhas:** `calamine` (Rust engine via `python-calamine` / fallback `openpyxl`)
- **Frontend:** Jinja2 templates, CSS puro responsivo com suporte a modo escuro/claro, sem frameworks externos pesados
- **Deploy & Infraestrutura:** Docker / Docker Compose / LXC Proxmox VE / Túnel Pangolin ZTNA

---

## 📦 Como Rodar o Projeto

### Opção 1: Via Docker Compose (Recomendado para Produção/Servidores)

1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/crm_andubai.git
   cd crm_andubai
   ```

2. Suba o container com Docker Compose:
   ```bash
   docker compose up -d --build
   ```

3. Acesse em `http://localhost:8080`.

Para criar ou promover o primeiro administrador via CLI no Docker:
```bash
docker exec -it crm_andubai flask criar-admin
```

---

### Opção 2: Execução Local (Windows)

1. Certifique-se de ter o **Python 3.12+** instalado.
2. Dê dois cliques no arquivo `iniciar.cmd` (ou execute via terminal).
3. Na primeira execução, ele criará o ambiente virtual `.venv`, instalará as dependências e abrirá o navegador em `http://127.0.0.1:8080`.

---

### Opção 3: Execução Local / Servidor (Linux)

1. Dê permissão de execução ao script:
   ```bash
   chmod +x iniciar_linux.sh
   ./iniciar_linux.sh
   ```

---

## ⚙️ Variáveis de Ambiente e Configurações

Copie o arquivo `config.py.exemplo` para `instance/config.py` ou configure as variáveis de ambiente:

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `SECRET_KEY` | *(gerada aleatória)* | Chave de assinatura criptográfica das sessões Flask |
| `CHECKLIST_DADOS` | `instance` | Diretório onde o banco `checklist.db` e backups são salvos |
| `SERVIDOR_HOST` | `0.0.0.0` | IP de escuta do servidor Waitress |
| `SERVIDOR_PORTA` | `8080` | Porta HTTP do servidor |
| `SERVIDOR_THREADS` | `8` | Quantidade de threads de atendimento simultâneas |
| `ATRAS_DE_PROXY` | `1` | Ativa suporte a cabeçalhos `X-Forwarded-For` / `X-Forwarded-Proto` |
| `LOGIN_PROVISORIO` | `0` | Se ativo (`1`), permite login simplificado por seleção de nome |

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

# Importar planilha da Base de Alunos
flask importar base /caminho/para/planilha.xlsx

# Importar CSV do Checklist Egali
flask importar checklist /caminho/para/checklist.csv
```

---

## 🧪 Testes Automatizados

Para rodar a suíte de testes unitários e de integração:

```bash
pytest
```

---

## 📄 Licença e Uso

Projeto interno desenvolvido para a equipe Egali / Andubai.
Proibida a distribuição pública de dados de clientes e alunos.
