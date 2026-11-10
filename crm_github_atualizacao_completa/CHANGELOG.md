# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.
O formato é baseado no [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [Não lançado]

### Adicionado
- **Checklist como única importação:** o relatório de checklist do TM (procedimentos finalizados e em aberto) passa a ser o único arquivo importado. A planilha semanal sai de Importações e do comando `flask importar`. O checklist cria o aluno e **um programa por aluno** com todas as compras dele (programas antigos continuam e recebem as compras novas) e preenche o cadastro: consultor, embarque, tipo de visto, país, cidade, escola, grupo, serviços e tags. VIP passa a ser procedimento "SA - VIP" ou tag VIP (`programa.vip_egali`, migração `e3b9c1d7a520`). Finalizados viram tarefas concluídas na Egali (em Concluídas, fora das filas); cancelados encerram a tarefa como cancelada. Serviço não classificado entra com aviso. Saem o erro "programa faltando na planilha", os avisos de consultor divergente e de VIP abaixo de 85 e a recusa do checklist sem planilha. Limite de envio sobe para 100 MB.
- **RSA - Checklist do Suporte pelo checklist:** a mesma importação monta a base do painel RSA com as regras do app (público teen fora, cancelados fora, tipo de visto, tipo de programa pelos serviços do aluno, procedimento de visto pelo código da trilha, atraso por dia; nos em aberto, atraso até a data da importação). A base fica em `<dados>/rsa/base.json`, fora do Git, e substitui na hora de mostrar a base embutida no HTML, que passa a servir só de layout. No painel, "Período do relatório" vira "Situação (finalizado ou em aberto)" e "Quem mais finaliza" não conta os em aberto. Arquivo sem Data da Finalização atualiza as tarefas e deixa o RSA como estava (`app/importacao/rsa_checklist.py`).
- **Andamento dos vistos:** filtro de embarque, que abre em "de hoje em diante", porque o checklist do ano traz também quem já embarcou.
- **Andamento dos vistos:** nova tela em `/andamento-vistos`, no toggle "Filas de trabalho", com aluno, consultor, data de embarque (ou mês, quando a data não foi informada), % do processo de visto pelos procedimentos finalizados, procedimento atual e, na última coluna, a NEG desse procedimento. O processo vai até o "Documentação OK" (envio para a embaixada/consulado), que leva a 100%; sem ele finalizado, o máximo é 99%. Usa a trilha Vistos / Canadá; vistos dos EUA e o eTA do Canadá ficam fora; filtros por consultor, situação e aluno (`app/andamento.py`, `calcular_visto`).
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
- **Leitura do checklist do TM:** a exportação passou a vir com duas linhas antes do cabeçalho (campos ocultos da tela e "Contagem de linhas"). O leitor agora acha o cabeçalho pela coluna "#", o que vale também para a importação de checklist de sempre.
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
## Próxima versão

- Painel de pautas: estados internos independentes do TM, histórico de movimentações, detalhe da pauta e movimentação dos cards por arrastar e soltar.
