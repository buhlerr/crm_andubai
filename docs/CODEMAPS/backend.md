<!-- Generated: 2026-11-12 | Files scanned: 179 | Token estimate: ~950 -->
# Backend

Blueprints registered in order by `app/web/__init__.py:MODULOS_WEB`.
Global: before_request CSRF check · after_request security headers · context `dados_do_topo` (sidebar counts)
Auth: L = login_obrigatorio, A = admin_obrigatorio (Papel.ADMIN). Roles: consultor, estagiario, admin.

## Routes
auth (no prefix) — app/web/auth.py (158)
GET|POST /entrar          → entrar (rate-limited, PBKDF2, optional LOGIN_PROVISORIO, never admin)
GET|POST /trocar-senha    → trocar_senha
POST     /sair            → sair

filas — app/web/filas.py (280) → consultas.*, andamento.*
GET /  /minha-fila  /fila  /concluidas  /para-lancar  /consultores  /andamento-vistos
    views: lista | kanban | quadro | calendario (Usuario.visao_fila)

tarefas /tarefas — app/web/tarefas.py (134) → acoes_tarefa.*
GET  /<id>                       → detalhe
POST /<id>/status                → acoes_tarefa.mudar_status
POST /<id>/responsavel           → acoes_tarefa.mudar_responsavel
POST /<id>/data-planejada        → acoes_tarefa.mudar_data_planejada
POST /<id>/lancada-na-egali      → acoes_tarefa.marcar_lancada
POST /anotacoes/<id>/lancada-na-egali → acoes_tarefa.marcar_anotacao
POST /<id>/anotacoes             → acoes_tarefa.anotar

programas — app/web/programas.py (41)
GET /programas/<id> → andamento.calcular   ·  GET /busca

importacoes /importacoes — app/web/importacoes.py (165) → importacao.checklist (only type accepted)
GET /  ·  GET|POST /nova (checklist CSV → criar_previa)  ·  GET /<id> (preview + ocorrências)
POST /<id>/encerrar-fora-do-periodo → checklist.encerrar_a_mao
POST /<id>/confirmar  → *.confirmar      POST /<id>/descartar → comum.descartar

painel /painel-veg — app/web/painel.py (57) → painel_veg.*
GET / · POST /enviar (A, upload base HTML) · GET /baixar (HTML + backlog data injected)

cadastros /cadastros — app/web/cadastros.py (359), mostly A
/usuarios  /usuarios/<id>  /apelidos  /apelidos/<id>/remover  /servicos
/publico-teen  /catalogo  /etapas/<id>  /pautas (colaborador→setor)  /ajuda-neg

pautas /pautas — app/web/pautas.py (429) → importacao.pautas.*   [PROTECTED]
GET / (filters, SLA)  ·  GET /<id>  ·  POST /<id>/estado  ·  POST /<id>/observacao
POST /enviar (CSV/MHTML upload → sync)  ·  GET /exportar-json

rsa /rsa — app/web/rsa.py (77) → rsa.*, rsa_checklist.base_guardada
GET /  ·  GET /<pagina>  ·  GET /<pagina>/app (HTML layout + base.json injected)  ·  POST /enviar (A)

## Services (app/)
consultas.py (589)      Filtros, tarefas(), contar(), kanban(), quadro_por_aluno(), concluidas(), tarefas_para_lancar()
acoes_tarefa.py (110)   every team edit → writes HistoricoTarefa
andamento.py (294)      calcular(programa), calcular_visto(), andamentos_de_visto()
painel_veg.py (576)     dados_backlog(), encaixar_grupo(), guardar_base()
rsa.py (180)            validar/guardar/encaixar(html, pagina, nome, admin, base) uploaded HTML
publico_teen.py (67)    teen-audience classification · vistos.py (71) visa labels filter
texto.py (36)           normalizar_texto, separar_neg · catalogo_inicial.py (535) seed trilhas/etapas/NEG
manutencao.py (163)     fazer_backup(), diagnosticar()

## Import pipeline (app/importacao/)
leitor_excel.py (170)  ler_planilha (calamine → openpyxl fallback, retries)
leitor_csv.py (54)     decodificar/ler_csv (finds header row by "#" column)
comum.py (139)         Coletor, criar_previa, confirmar, descartar, hash_arquivo
checklist.py (770)     SOLE import: interpretar, periodo_do_arquivo, tarefas_fora_do_periodo, encerrar_a_mao
                       creates Aluno + 1 Programa/aluno + Compra + Tarefa; vip_egali; then RSA base
rsa_checklist.py (256) montar_base, codigo_da_trilha, tipo_de_programa, guardar_base/base_guardada (<data>/rsa/base.json)
base_alunos.py (393)   weekly sheet — no longer imported (UI/CLI removed), kept for tests
consultores.py (47)    ResolvedorConsultor (name/apelido → Usuario)
pautas.py (599)        extrair_linhas_csv, SLA, membros (env PAUTAS_MEMBROS_UNIDADE), sync Pauta
valores.py (88)        normalizar_id_egali, para_data, para_decimal, separar_compras
rotulos.py (54)        UI labels for preview summaries
