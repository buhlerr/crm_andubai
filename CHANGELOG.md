# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [Não lançado]

### Adicionado
- **RSA - Checklist do Suporte:** o app `APP_Checklist_Suporte_ao_Aluno.html` (modelo base VEG) aparece dentro do CRM, em `/rsa/<pagina>`, no toggle "RSA - Checklist do Suporte" (Visão Geral, Procedimentos, Executores e Consultores, Programas e Vistos, Prazos e Atrasos). O grupo Sistema do app (Credenciais, Envio de Arquivos, Manual, Melhorias, Testes) fica no toggle "Sistema do RSA", só para administradores. O administrador envia o HTML pela própria tela; ele fica em `instance/rsa/`, fora do Git, porque traz nomes de colaboradores. O original não é alterado: na hora de mostrar, o CRM pula o login do app, esconde o cabeçalho e o menu dele e abre a página escolhida (`app/rsa.py`).
- **Pautas TM:** filtro "Quebrou na nossa UN" (`pendencia=quebra_un`), com as pautas em que a quebra de 72h é da AN e Dubai.

### Modificado
- **Barra lateral:** pode ser recolhida, deixando só os ícones (a escolha fica no navegador). Recolhida, o grupo abre ao lado do ícone. Ordem: Buscar aluno, Filas de trabalho, Pautas TM (Total de pautas, Ação pendente da UN, Quebrou na nossa UN), RSA - Checklist do Suporte, Sistema do RSA (admin) e Administração (admin; junta os antigos grupos Dados e Administração).
- **Menu do nome:** "Trocar senha", "Para lançar na Egali" (com o contador) e "Quando usar NEG" saíram da lateral e ficam no menu que abre ao clicar no nome.
- **Andamento do aluno:** procedimentos "Ainda não criado pela Egali" continuam visíveis na lista, mas deixaram de entrar no total do percentual e não acionam sozinhos o aviso de estimativa.

### Documentação
- **Regras de Pautas TM:** Esclarecida a configuração atual da unidade AN e Dubai e documentada a identificação do setor que abriu, que é responsável e que realizou a última atualização da pauta.
- **Política de testes:** Substituída a exigência de executar todos os testes em toda alteração por validação proporcional ao risco, mantendo a suíte completa para merge, publicação e mudanças amplas.
- **Cobertura de testes:** A suíte passou a contar com 273 casos após as validações de pautas e da precedência do consultor do checklist.

### Modificado
- **Consultor do checklist:** O consultor informado no relatório de checklist passa a prevalecer sobre a Base semanal e é preservado em importações posteriores da Base. Divergências continuam sendo registradas para conferência.
- **Estrutura web:** Centralizado o carregamento dos blueprints em `app/web/__init__.py`, padronizando a inicialização da aplicação e reduzindo acoplamento na montagem das rotas.
- **Importação de Pautas TM:** Pautas sem vínculo com AN e Dubai em responsável, criador ou última atualização deixam de ser importadas para o painel.

### Corrigido
- **Exportação JSON de Pautas TM:** Corrigido erro `Internal Server Error` (HTTP 500) que ocorria ao tentar exportar o JSON de pautas que possuíam anotações ou observações salvas. O campo `Observacao em` agora é formatado como string (`dd/mm/aaaa HH:MM`) e a serialização conta com `default=str` para prevenir falhas de serialização de objetos datetime.

---

## [2.1.1] - 2026-10-02

### Corrigido
- **Docker Compose:** Ajustado o fallback de `LOGIN_PROVISORIO` de `1` para `0` em `docker-compose.yml`, evitando a exceção `ConfiguracaoInsegura` na inicialização do container quando a variável `SENHA_PROVISORIA` não for informada.

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
- **Documentação de Negócio:** Adicionado `docs/REGRAS_CHECKLIST.md` contendo a especificação detalhada de regras, entidades e prazos.
- **Tabela de SLA de Pautas:** `app/dados/pautas_sla.csv` incorporado para cálculo automático de SLA sem dependência de planilhas externas.
- **Suíte de Testes:** 271 testes automatizados cobrindo autenticação, rate-limiting, migrações, importações, pautas TM e visualizações web.

### Modificado
- **Migrações:** Migração `ec1a54ac4fe8` tornando a criação das tabelas de pautas e campos de senha idempotentes.
- **Dockerfile:** Atualização da rotina de inicialização para falhar imediatamente se a migração do banco falhar.
- **Layout:** Barra de navegação com menus dropdown dinâmicos preservando atalhos de Pautas TM e autoatendimento de senha.

### Segurança e LGPD
- Remoção e bloqueio via `.gitignore` de planilhas e exportações reais de alunos e colaboradores.
- Nomes reais de colaboradores substituídos por configuração dinâmica (`PAUTAS_MEMBROS_UNIDADE`).
- Adição de fixtures higienizadas e fictícias em `tests/amostras/`.
