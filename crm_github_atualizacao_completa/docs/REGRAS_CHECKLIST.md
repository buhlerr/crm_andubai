<!-- Cópia das regras do sistema original (Checklist Pós-Venda, versão Windows) em 01/10/2026.
     As regras de negócio valem aqui. As partes de Windows, IIS, Excel por COM, modo equipe e login provisório
     por escolha de nome NÃO se aplicam a este repositório: veja AGENTS.md (Diferenças de propósito). -->

# Sistema de Checklist Pós-Venda — Egali

## Objetivo

Sistema interno para acompanhar o checklist pós-venda de cada aluno de intercâmbio da Egali. Substitui a estrutura montada no ClickUp (lista "Checklist Alunos" e lista "base de alunos por consultor").

A equipe inclui pessoas não técnicas. A interface precisa ser simples, em português, sem jargão. Nenhuma operação do dia a dia pode exigir terminal.

## Stack

- Python + Flask (padrão das outras ferramentas internas da Egali)
- SQLite com SQLAlchemy no início, com o modelo pronto para migrar para Postgres depois
- Roda em Windows
- A leitura do Excel usa win32com/pywin32 (automação COM), não openpyxl, porque a planilha tem proteções que o openpyxl não abre. Veja `referencia/atualizar_consultor_alunos_clickup.py`

## Entidades

**Aluno**: `aluno_id` (vem do sistema da Egali), nome. Representa a pessoa.

**Programa**: `programa_id` (vem do sistema da Egali), `aluno_id`, consultor, mês de embarque, visto normalizado, país, cidade, escola, acomodação, grupo, situação (ativo/cancelado). Representa cada programa comprado. Um mesmo aluno pode ter mais de um programa, e o checklist é feito por programa, não por pessoa.

**Compra**: `compra_id` (vem do sistema da Egali), `programa_id`. Cada programa é formado por várias compras. É por elas que o checklist se liga ao programa.

**Trilha**: GERAL, VISTOS ("Vistos / Canadá"), EUA, EAU (Dubai), VIP (programa com `pt_prog` >= 85), ON ("Primeiro contato"; parecido com o onboarding). O serviço contratado gera os procedimentos, mas isso é feito pelo sistema da Egali.

A trilha de uma tarefa é a da etapa no catálogo, não o código no texto da Egali. Reorganização decidida pela equipe em 29/09/2026 (`app/catalogo_inicial.py`: `TRILHAS_MESCLADAS`, `MUDANCAS_DE_TRILHA`, `ORDEM_REORGANIZADA`):
- A trilha CAN da Egali foi mesclada em VISTOS ("Vistos / Canadá"). Procedimento novo "SA - CAN - ..." entra em VISTOS.
- "Realização de Onboarding com novos alunos (CT e Longa)" (GERAL) e "Agendar consultoria com a Base - Canadá Leap" (CAN) estão na trilha VIP: quem tem esses procedimentos é VIP, então com menos de 85 pontos a importação avisa para corrigir.
- "Realização de Onboarding com novos alunos (pacotes)" (GERAL) está em Primeiro contato.
- "Organizar documentos para orçamento de tradução" (GERAL) está em Vistos / Canadá, logo depois da "Entrega da 1a documentação".
- Um banco antigo é reorganizado sozinho pelo `flask catalogo carregar` (roda ao iniciar e no `atualizar.ps1`), uma vez só. Etapa que alguém moveu pela tela, ou trilha renomeada, fica como está.

**Etapa (catálogo)**: lista ordenada de procedimentos de cada trilha, com as orientações do PPT "Checklist S.A. - AN e Dubai" (prazo de referência, o que é, importância, quando cabe NEG, link da gravação). A carga inicial está em `app/catalogo_inicial.py` (`flask catalogo carregar`). O catálogo NÃO gera tarefas. Cada etapa tem apelidos (textos antigos ou do PPT que apontam para ela). Procedimento novo que aparecer no CSV entra sozinho no catálogo, marcado para revisão.

**Tarefa**: é um item do checklist da Egali (uma linha do CSV, chave `#`). Pertence a um programa e a uma compra. Quem cria as tarefas é o CSV, não o catálogo.

Duas datas:
- **Data do procedimento** (`prazo_egali`): fixa, vem do CSV. É por ela que se conta o atraso e que o NEG vira justificativa.
- **Data planejada** (`data_planejada`): quando o consultor vai fazer. Vazia = igual à do procedimento (escolher a própria data do procedimento também esvazia). Ordena as filas, é a usada no filtro "Data de/até" e posiciona a tarefa no calendário, onde dá para arrastar para outro dia. Nunca muda o atraso. Planejada depois da data do procedimento gera aviso ("provavelmente vai precisar de NEG"). `Tarefa.data_prevista` = planejada ou procedimento.

O responsável é da tarefa, não do aluno. Por padrão ele segue o consultor do programa (que acompanha a planilha); se alguém trocar à mão (`responsavel_manual`), a troca fica. Por exemplo, a estagiária executa tarefas de alunos de vários consultores.

Status: A fazer, Em andamento, Aguardando aluno, Concluída, Não se aplica.

**Serviço**: classificação editável dos serviços da Egali. Curso (Curso Premium, Budget, Smart, Summer Schools, Vancouver Experience, grupos, Curso + Trabalho, Curso + Trabalho Canadá, Canada Leap) é um programa e precisa estar na planilha. Visto (inclui "Additional documents - Canadá") pode vir sozinho. Avulso (transfer aeroporto-acomodação, seguro) vai junto de um programa. Ignorado (C. Curso, Valores Extras, Reserva técnica): a importação pula, sem gerar aviso.

## Fontes de dados (importação periódica)

> **Desde 10/11/2026 o checklist é a única importação.** A planilha semanal deixou de ser importada
> (as seções sobre ela abaixo ficam como histórico). O relatório de checklist do TM, com os procedimentos
> finalizados e em aberto, alimenta as filas, as tarefas e o painel RSA ao mesmo tempo.
>
> - **Aluno e programa:** o aluno vem do ID Aluno; o programa é **um por aluno**, com todas as compras dele.
>   Programas que já existiam (da planilha) continuam e recebem as compras novas do aluno (o normal mais
>   recente, quando há mais de um). Só compras de visto: "só de visto"; chegou compra de curso, vira normal.
>   Programa criado pelo checklist não tem `programa_id` (o checklist não traz esse número).
> - **Cadastro do programa:** vem do checklist a cada importação, com o valor que mais aparece nas linhas do
>   aluno: consultor, embarque (data e mês), tipo de visto (`EUA (Turista)` vira `Turista - EUA`), país,
>   cidade, escola, grupo. Serviços se acumulam (não some serviço antigo). Campo vazio não apaga o gravado.
> - **VIP:** procedimento `SA - VIP - ...` ou tag `VIP` (`programa.vip_egali`). A pontuação da planilha
>   continua valendo para os programas antigos.
> - **Status:** "Finalizado" ou Data da Finalização preenchida = tarefa concluída na Egali (se não existia,
>   entra já concluída, fora das filas; a data de conclusão é a da finalização). Status com "cancel" = a tarefa
>   é encerrada como cancelada (não vira tarefa nova). O resto está em aberto. Item ausente do arquivo
>   continua sendo encerrado pela regra do período.
> - **Serviço não classificado:** entra no programa do aluno com aviso (antes não era importado).
> - **Painel RSA:** a mesma importação monta a base do RSA (`app/importacao/rsa_checklist.py`). Arquivo sem
>   Data da Finalização (exportação só dos em aberto) atualiza as tarefas e deixa o RSA como estava.
> - Deixaram de existir: o erro "programa faltando na planilha", o aviso de consultor divergente, o aviso de
>   VIP abaixo de 85 pontos e a recusa do checklist sem planilha.

### 1. Base de alunos (Excel, semanal)

A planilha é ajustada toda semana:
- alunos novos, comprados no sistema da Egali, são adicionados;
- alunos cancelados no sistema são apagados da planilha.

A planilha tem as colunas `programa_id` e `aluno_id`. A correspondência é SEMPRE feita por esses IDs, nunca por nome. `programa_id` é a chave de cada linha.

Regras da sincronização:
- `aluno_id` novo: cria o aluno.
- `programa_id` novo: cria o programa e gera suas tarefas.
- `programa_id` que existe nos dois lados: atualiza os campos de cadastro (consultor, embarque, escola etc.). Se o nome do aluno mudou, atualiza o nome, sem criar outro aluno.
- `programa_id` que existe no banco mas sumiu da planilha NÃO é apagado. O programa é marcado como cancelado, com a data, e suas tarefas abertas saem das filas de trabalho. O histórico fica preservado. Os outros programas do mesmo aluno não são afetados.
- Se um programa cancelado reaparecer na planilha, ele é reativado.
- A coluna `compra_id` traz VÁRIOS IDs numa mesma célula, separados por vírgula e espaço (ex.: `5703996, 5703997, 5703998`). A lista pode ser longa. Separar pela vírgula, tirar espaços e guardar cada ID como uma Compra ligada ao programa. Ler a célula como texto, para o Excel não converter nem cortar os números.
- A cada importação, a lista de compras do programa é sincronizada: compras novas entram, e as que saíram da célula são desligadas do programa.
- Linha sem `programa_id` ou sem `aluno_id` não é importada. Ela aparece no resumo como erro para a equipe corrigir.
- A importação nunca sobrescreve o trabalho feito no sistema: status, responsável alterado manualmente, prazos editados e anotações.
- Rodar a mesma importação duas vezes não pode duplicar nada (idempotência).
- Antes de gravar, a importação mostra um resumo para confirmação: X novos, Y atualizados, Z cancelados.

Como está implementado (`app/importacao/base_alunos.py`):
- A prévia roda a sincronização inteira e desfaz (rollback); a confirmação roda de novo e grava. Se as contagens não baterem (o banco mudou no meio), a confirmação é recusada.
- As linhas lidas ficam em `importacao.dados_lidos` entre a prévia e a confirmação, só com as colunas usadas (nada de CPF, passaporte, contatos). São apagadas ao confirmar ou descartar.
- Linha sem programa_id, aluno_id, nome e compras é ignorada sem erro. A planilha real tem "Sim" na coluna "Enviado" em centenas de linhas abaixo dos dados.
- Coluna opcional ausente no arquivo não apaga o valor que já existe.
- Aviso de segurança quando mais de 20% dos programas ativos (e pelo menos 10) seriam cancelados: pode ser arquivo errado ou filtrado.
- Colunas usadas: programa_id, aluno_id, aluno_name, compra_id, Consultor, Mês embarque, programa_data_embarque, Visto normalizado, pais_name, cidade_name, escola_name, acomodacao_tipo, grupo, pt_prog.

### 2. Checklist (`checklistServicoNew.csv`)

É a exportação de checklist do sistema da Egali, com cerca de 2000 linhas. A coluna "Procedimento" segue o formato `SA - <trilha> - <etapa>`. Veja o parsing em `referencia/importar_checklist_clickup.py`.

Colunas de identificação:
- `#`: ID do item de checklist no sistema da Egali. É a chave de cada linha, e reimportar o mesmo `#` atualiza o item em vez de duplicar.
- `Id da Compra`: um único ID por linha. Liga o item ao programa: o item pertence ao programa que tem esse ID na sua lista de `compra_id`.
- `ID Aluno`: deve ser igual ao `aluno_id` do programa encontrado. Serve como conferência.
- `NEG`: observação que o consultor registra no sistema da Egali, por um botão. Pode ser uma anotação sobre o aluno ou a justificativa de um procedimento não concluído no prazo. Costuma começar com uma data (ex.: `17/09 - ...`).

Regras para o `NEG`:
- Guardar num campo próprio, "Observação do sistema Egali", separado das anotações feitas no sistema novo. A reimportação atualiza esse campo, mas nunca toca nas anotações feitas no sistema novo.
- Mostrar o `NEG` junto da tarefa nas filas de trabalho, com destaque quando a tarefa está atrasada, porque nesse caso ele costuma ser a justificativa do atraso.
- Nas visões, permitir filtrar tarefas atrasadas com e sem justificativa.

Ciclo de vida do item (a equipe continua marcando as etapas no sistema da Egali):
- Item novo no CSV: cria a tarefa.
- Item que some do CSV: foi finalizado ou cancelado na Egali. A tarefa vira Concluída, com `encerrada_egali_em` e motivo (cancelado se a compra ou o programa saiu da planilha; senão finalizado).
- Enquanto o CSV for exportado por período, o sumiço só vale para itens com prazo dentro do período da importação. Quando a leitura for direta da ferramenta da Egali, sem período, vale para tudo.
- Item que reaparece: a tarefa é reaberta.

Compras do CSV que não estão em nenhum programa da planilha:
- Visto ou avulso, e o aluno tem um programa na planilha: a compra é juntada a esse programa (`origem = checklist`). A importação da planilha nunca desliga essas compras.
- Visto, e o aluno não está na planilha: aluno só de visto (não é erro). Cria um "programa só de visto", sem `programa_id`, com o consultor do CSV. Quando o aluno aparecer na planilha com curso, o programa só de visto é incorporado a ele.
- Curso: erro "programa faltando na planilha".
- Aluno com 2 ou mais programas: aviso para escolher à mão.

Como está implementado (`app/importacao/checklist.py`, mesmo fluxo prévia -> confirmação de `comum.py`):
- O CSV vem em cp1252 e o "?" em "Documentação OK ? Envio" está no arquivo mesmo (não é problema de codificação).
- Período: sem informar, usa o menor e o maior prazo do arquivo. `periodo_completo` = exportação sem filtro.
- Item que está no arquivo mas não pôde ser importado (órfão, divergência) não é encerrado.
- Toda tarefa cujo item estava no arquivo recebe `ultima_importacao_id` da importação (mesmo se a linha deu erro). Assim, "fora do período" = tarefa não encerrada com `ultima_importacao_id` mais antigo que a importação.
- Tarefas fora do período (ex.: prazo 17/04/2025 num CSV que começa em 17/09/2026) não são encerradas sozinhas. Na página da importação de checklist mais recente, o admin marca e encerra à mão (`checklist.encerrar_a_mao`). Decisão da equipe: o checklist novo está correto; o que ficou para trás já foi ajustado ou finalizado na Egali. O encerramento à mão fica no histórico com o nome de quem fez, e a tarefa é reaberta se o item voltar. Na lista, só vêm marcadas as tarefas com prazo antes do início do período. As de prazo depois do fim (ou sem data) vêm desmarcadas, com aviso: elas só não estavam no arquivo porque a exportação terminava antes, e em geral continuam pendentes.
- Encerramento: motivo "cancelado" se o programa não está ativo ou a compra foi desligada; senão "finalizado". A tarefa aberta vira Concluída. Se reaparecer, volta para A fazer.
- Programas só de visto: consultor, país e embarque vêm do CSV (não estão na planilha).
- Procedimento novo entra no catálogo (`criada_automaticamente`), com aviso. Serviço desconhecido entra como "não classificado"; itens de compras fora da planilha com esse serviço não são importados até alguém classificar.
- Problemas repetidos são agrupados (uma ocorrência por compra, por serviço, por par de consultores).
- Mudanças de prazo, NEG, programa, procedimento e status automático ficam em `historico_tarefa`.
- O checklist é recusado se ainda não houver nenhum programa da planilha (sem a planilha, todo visto viraria "só de visto": aconteceu no primeiro teste da equipe, com 634 programas só de visto). Se a última planilha confirmada tiver mais de 7 dias, a prévia avisa.
- Ordem recomendada toda semana: primeiro a planilha, depois o CSV, exportados no mesmo dia. Com a planilha mais antiga que o CSV, as vendas novas aparecem como "programa faltando na planilha" e as trocas de consultor como divergência.

Outros casos que aparecem no resumo e nunca são descartados em silêncio:
- `ID Aluno` diferente do `aluno_id` do programa encontrado: divergência de cadastro.
- Consultor do CSV diferente do da planilha: aviso. Vale o da planilha.
- Etapa VIP em programa com menos de 85 pontos: aviso para correção.

## Atribuição de consultor

O nome do consultor na planilha é texto livre e nem sempre bate com o cadastro de usuários. A regra atual, em `referencia/atualizar_consultor_alunos_clickup.py`, usa correspondência parcial mais um dicionário de exceções manual. Isso precisa ser mantido, com as exceções editáveis pela interface, não só no código.

## Visões obrigatórias

- Por consultor
- Fila por status (a fila de trabalho da equipe)
- "Minha fila": tarefas em que o usuário logado é o responsável

## Andamento até o embarque

Na página do programa aparece a % de procedimentos finalizados. Clicar nela abre a lista simples, com ✓ finalizado, ● em aberto e ○ ainda não criado. A regra está em `app/andamento.py`.

A Egali cria os procedimentos aos poucos, e o sistema só vê o que estava em aberto nas importações. Por isso a conta é uma estimativa, com o catálogo como roteiro:
- Entram a trilha Geral (menos nos programas só de visto), as trilhas em que o programa tem tarefa e as trilhas com um procedimento específico que vale para o aluno.
- A Geral termina no "Realizar contato de relacionamento pré-embarque", o último procedimento de todos os alunos. O pós-embarque (pré-NPS) fica fora.
- Procedimento sem tarefa conta como finalizado se vem antes do primeiro em aberto da trilha. Se vem depois, conta como pendente ("ainda não criado pela Egali"). Quem já embarcou tem finalizado tudo o que não está em aberto.
- Os procedimentos que só valem para parte dos alunos ficam em `SO_PARA_ALGUNS`. Hoje são três:
  - o CAQ, só para visto Canadá - Quebec;
  - a consultoria Canada Leap, só para quem comprou Canada Leap (`servico_name` da planilha ou serviço da compra);
  - o teste de nivelamento, que só algumas escolas pedem. Não há lista das escolas, então ele só entra quando a Egali cria a tarefa.

A última observação feita neste sistema (anotação) aparece embaixo da NEG nas filas, e o "+ observação" permite anotar sem sair da fila. A observação não vai para a Egali e não conta como justificativa: justificativa é só a NEG.

## Público teen

A equipe de Teens é separada do Suporte, mas usa as mesmas estruturas no sistema da Egali. Os alunos teen NÃO são excluídos: ficam marcados (`Aluno.teen`, `teen_motivo`) e as filas têm o filtro "Público" (Todos / Suporte / Teen).

- A regra é a mesma do painel VEG. É teen o aluno inteiro que tiver, em qualquer programa ou compra, um serviço marcado como teen (padrão: Summer Schools, Winter Schools, Viagem Cultural, Vancouver Experience), a tag `summer` ou um consultor da equipe teen.
- Serviços e consultores teen são editáveis em Administração → Público teen (`/cadastros/publico-teen`).
- A marca é recalculada em `app/publico_teen.py:recalcular()` a cada importação (planilha e checklist) e a cada alteração na tela.

## Painel VEG (Grupo 2 · Backlog do Suporte)

Há um painel HTML de arquivo único feito por outro analista, a partir do modelo base VEG (`checklist_VEG_dd-mm-aaaa.html`). O Grupo 1 dele analisa o que já foi finalizado. `app/painel_veg.py` pega esse HTML, sem alterar o que já existe, e encaixa o Grupo 2 com as tarefas abertas deste sistema. As regras são as que vêm escritas no próprio HTML:
- a navegação entra em `renderGruposDeDados()`, sempre acima do grupo Sistema;
- as rotas entram em `go(page)`;
- o grupo ganha uma seção no Manual (as seções seguintes são renumeradas), uma seção no `CHECKLIST` da aba Testes e uma entrada no `CHANGELOG`;
- `APP_DESCRICAO` é atualizada;
- as funções e classes de tela do modelo são reaproveitadas.

Como funciona:
- Tudo o que o sistema insere fica entre marcadores `>>> GRUPO BACKLOG DO SUPORTE · ... >>>`. `retirar_grupo()` volta exatamente ao original, e gerar de novo não duplica nada.
- O Grupo 2 leva só códigos agregados: nenhum nome ou ID de aluno (os alunos viram números sequenciais).
- Tela: Dados → Painel VEG (`/painel-veg`). O administrador envia o HTML base, que fica em `instance/painel_veg/`. Todos podem baixar o painel gerado na hora, sempre como anexo.
- Os testes usam um HTML sintético (`tests/test_painel_veg.py`). Nunca usar o arquivo real nos testes: ele contém dados.

## Pasta `referencia/`

Contém os scripts da versão ClickUp. Servem para entender as regras de negócio e os formatos de arquivo. Não devem ser copiados, e todas as chamadas à API do ClickUp desaparecem no sistema novo.

## Pasta `amostras/`

Deveria conter versões reduzidas e anonimizadas dos arquivos reais. Hoje contém dados reais (CPF, passaporte, contatos) e está no `.gitignore`. Nunca commitar dados reais de alunos. Os testes usam só dados fictícios.

## Decisões já tomadas

- A planilha tem uma linha por programa. Programas só de visto não estão nela.
- O CSV é importado periodicamente e traz só os itens pendentes (todos "Aguardando"). No futuro, a leitura será direta da ferramenta da Egali: a leitura do arquivo fica separada do resto da importação.
- Roda num servidor interno com Windows e Excel instalado (exigência do win32com). A equipe envia a planilha e o CSV por upload na tela. O servidor precisa de HTTPS. Detalhes em "Servidor (decidido)".
- Login com Microsoft 365 (Entra ID, biblioteca MSAL). Depende da TI registrar o aplicativo no tenant. Só entra quem estiver cadastrado na tabela de usuários.

## Estrutura do código

- `app/models/`: modelo do banco (SQLAlchemy). IDs da Egali em texto normalizado, enums como texto + CHECK, nomes de constraints fixos: tudo pronto para Postgres.
- `migrations/`: Alembic (Flask-Migrate). Depois de mudar um modelo: `flask db migrate -m "..."` e revisar o arquivo gerado (o autogenerate duplica os CHECK dos enums; manter só os `ck_...` com `op.f()`). O `env.py` desliga as chaves estrangeiras do SQLite durante a migração (o modo batch recria tabelas referenciadas, como `usuario`) e confere as referências no fim. `tests/test_migracoes.py` roda todas as migrações num banco com dados: não apagar.
- `app/catalogo_inicial.py`: trilhas, etapas e serviços iniciais.
- `app/importacao/`: `comum.py` (fluxo prévia -> confirmação, `Coletor` de erros e avisos), `leitor_excel.py` (win32com; a única parte que depende do Excel), `leitor_csv.py` (trocar por leitura direta da Egali no futuro), `valores.py` (IDs, datas, números), `consultores.py` (nome -> usuário), `base_alunos.py` (planilha semanal), `checklist.py` (CSV; cria as tarefas).
- `app/cli.py`: comandos de instalação e teste (`flask importar base ARQUIVO`, `flask importar checklist ARQUIVO [--de/--ate | --completo]`, `flask usuarios adicionar/listar/apelido`). O uso do dia a dia vai ser pelas telas.
- `app/consultas.py`: regras das filas (na fila, responsável, prazo, atrasada com/sem justificativa) e o resumo por consultor.
- Visualizações de Minha fila e Fila da equipe (`app/web/filas.py`, `app/templates/filas/`): Lista, Kanban (colunas por status; arrastar muda o status via POST com `X-Requested-With: fetch`, que responde JSON), Quadro por aluno (um cartão por programa, o mais urgente primeiro) e Calendário (pelo prazo, semanas de segunda a domingo). A escolha fica em `usuario.visao_fila`; links com `fixar=0` abrem outra visão sem trocar a preferida.
  - Quadro por aluno: uma linha por aluno que abre as tarefas (`<details>`), com visto, embarque, abertas e atrasadas no resumo. Padrão: próximos embarques primeiro, agrupados por mês; no fim, o grupo "Embarque já passou" (do mais recente ao mais antigo).
  - "Organizar por" (`consultas.Organizar`). Na lista, agrupa as tarefas por data prevista, procedimento, tipo de visto, embarque, responsável ou status. No quadro, ordena os alunos (embarque, urgência, visto ou consultor). A escolha fica em `usuario.organizar_lista` / `organizar_quadro` (texto validado no código, não enum, porque as duas colunas criariam CHECKs com o mesmo nome).
- Tipo de visto (`app/vistos.py`): vem da coluna "Visto normalizado" da planilha, que distingue turista, estudante, eTA e outros ("Turista - EUA,eTA - Canadá" vira "Visto - EUA - Turista" e "Visto - Canadá - eTA"). Os serviços das compras não dizem o tipo e só valem de reserva para os programas só de visto. Aparece em todas as visões, como filtro e na página do aluno.
- Concluídas (`/concluidas`): concluídas e "não se aplica" de qualquer programa, a mais recente primeiro. Mostra a origem ("Neste sistema", "Saiu do checklist da Egali" ou "Encerrada à mão"), quem concluiu e se foi no prazo.
- Para lançar na Egali (`/para-lancar`, com o contador na barra lateral): o que foi feito aqui e ainda precisa ir para a Egali. Não há integração automática, porque não se sabe se o TM tem API (perguntar à TI).
  - Procedimentos concluídos ou "não se aplica" aqui, ainda abertos no CSV: a pessoa lança na Egali e clica em "Lancei na Egali" (`Tarefa.lancada_egali_em`).
  - Observações deste sistema: "Lancei como NEG" ou "Não precisa" (`Anotacao.lancada_egali_em` / `nao_precisa_lancar`).
  - Confirmação: quando o item some do CSV, sai da lista. Se uma importação posterior à marcação ainda traz o item, ele vai para "Marcadas como lançadas, mas ainda abertas na Egali".
  - Reabrir a tarefa desfaz o "lancei".
- `app/acoes_tarefa.py`: o que a equipe faz na tarefa (status, responsável, prazo, anotação, lançamento na Egali), sempre com histórico.
- `app/web/`: telas (Flask blueprints) e `app/templates/`, `app/static/estilo.css`. Sem framework de JavaScript.
  - Visual no padrão das ferramentas internas da Victoria/Egali, copiado de `APP_Checklist_Suporte_ao_Aluno.html` (mesmas variáveis de cor, fontes e medidas): cabeçalho `#0c2b4c` com o logotipo (`app/static/logo-victoria.png`, extraído desse arquivo), barra lateral `#07203a` com grupos, destaque verde-azulado `#0f9a94`, fundo `#eef2f6`, títulos em Archivo e texto em Inter (Google Fonts; sem internet, cai para as fontes do sistema). A tela de entrada é o cartão branco sobre o degradê azul-marinho. Abaixo de 900 px a barra lateral vira o botão ☰. As cores ficam nas variáveis do `:root` do `estilo.css`; não usar cor fixa fora delas.
  - `auth.py`: login PROVISÓRIO (escolhe o nome, sem senha) enquanto a TI não registra o app no Entra ID. Ligado por `LOGIN_PROVISORIO` (padrão "1"). Trocar pelo Microsoft 365 (MSAL) antes de abrir para a equipe pela rede.
  - Todo POST exige o token CSRF (`{{ m.csrf() }}` nos formulários).
  - Importar arquivos e mexer nos cadastros: só papel admin. Filas, tarefas e busca: todos.
  - Em templates, não usar `pagina` como variável no `base.html`/includes: é o número da página da paginação.
- `app/texto.py`: `separar_neg()` quebra o NEG (várias observações coladas, cada uma terminando em "(Nome, dd-mm-aaaa, HHhMM)") para mostrar uma por linha.
- `tests/`: `python -m pytest`. Só dados fictícios.

## Como rodar (desenvolvimento)

Atalho: dois cliques em `iniciar.cmd` (ou no atalho "Checklist Pós-Venda" da Área de Trabalho). Ele instala o que faltar, atualiza o banco, sobe em http://localhost:5000 e abre o navegador; se já estiver rodando, só abre o navegador. O `iniciar.cmd` é uma linha ASCII que chama `scripts/iniciar_local.ps1`: não pôr acentos no .cmd (o cmd se perde com UTF-8).

Modo equipe (PROVISÓRIO, até a instalação no servidor): o atalho "Checklist Pós-Venda (equipe)" chama `iniciar_equipe.cmd`, que chama `scripts/iniciar_equipe.ps1`. O sistema roda nesta máquina, aberto para a rede na porta 8080.
- Na primeira vez, `scripts/preparar_equipe.py` faz a preparação:
  - copia o banco de `instance/` para `C:\ChecklistEgali\dados`, fora do OneDrive, pela API de backup;
  - copia o `painel_veg/`;
  - cria o `config.py` com uma chave nova, a senha da equipe (digitada pela pessoa, ou gerada) e `SERVIDOR_HOST = "0.0.0.0"`.
- Depois disso, `iniciar_local.ps1` também passa a abrir o modo equipe, para nunca haver dois bancos. O `instance/checklist.db` antigo fica parado como cópia.
- Roda o `servidor.py` (waitress) e impede a suspensão do computador enquanto a janela estiver aberta.
- A liberação da porta no firewall é feita pela própria pessoa (regra "Checklist Egali (porta 8080)"). O script só avisa quando ela falta.
- Não tem HTTPS: usar só na rede da empresa.

À mão:

1. `python -m pip install -r requirements.txt`
2. `flask --app wsgi db upgrade` e `flask --app wsgi catalogo carregar`
3. Primeiro administrador: `flask --app wsgi usuarios adicionar "Nome" email@egali.com.br --papel admin`
4. `flask --app wsgi run` e abrir http://localhost:5000. O resto (usuários, importações) é pela tela.
- Datas gravadas em UTC; para mostrar, usar `hora_local()` de `app/models/base.py`.
- `servidor.py`: servidor de produção (waitress), com reinício automático e log em `<dados>/logs`. Recusa subir com a SECRET_KEY padrão ou com login provisório sem SENHA_PROVISORIA.
- `app/manutencao.py`: `flask backup` (API de backup do SQLite, guarda os 30 mais recentes) e `flask diagnostico [--planilha ARQ]`.
- `instalar/`: `instalar.ps1`, `atualizar.ps1`, `comum.ps1`, `iis/web.config` e o `LEIAME.md` para a TI. Qualquer mudança de configuração do servidor deve ser refletida no LEIAME.
- Configuração: padrões em `create_app`, depois `<dados>/config.py` (gerado pelo instalador), depois o dicionário de teste. A pasta de dados é `CHECKLIST_DADOS`; sem ela, `instance/`.

## Servidor (decidido)

- Windows, em `C:\ChecklistEgali` (`app\` código, `venv\`, `dados\`, `flask.cmd` para os comandos de manutenção). Nunca no OneDrive.
- Roda por tarefa agendada ("Checklist Egali - servidor", ao ligar, reinicia se cair), não como serviço pywin32. Backup diário às 02:00 por outra tarefa.
- IIS na frente com HTTPS (URL Rewrite + ARR), repassando para 127.0.0.1:8080. `ATRAS_DE_PROXY = True` liga o ProxyFix e os cookies seguros.
- SQLite em modo WAL com busy_timeout, para vários usuários ao mesmo tempo.
- Risco conhecido: automação do Excel pela conta SYSTEM não é garantida pela Microsoft, e planilhas com rótulo de confidencialidade podem exigir uma conta com licença. O LEIAME recomenda uma conta de serviço própria e o `diagnostico --planilha` para testar.

## Em aberto

- Login com Microsoft 365: depende da TI registrar o aplicativo no Entra ID e do endereço HTTPS do servidor.

(Decidido: acomodação vem de `acomodacao_tipo`, ex.: "Homestay (Egali)".)

## Forma de trabalhar

- Propor um plano e esperar aprovação antes de mudanças grandes.
- Construir em etapas: (1) modelo do banco, (2) importação da base de alunos, (3) geração de tarefas por trilha, (4) telas e visões, (5) integração.
- Textos da interface e mensagens de erro em português.
