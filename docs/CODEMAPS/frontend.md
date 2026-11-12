<!-- Generated: 2026-11-12 | Files scanned: 179 | Token estimate: ~550 -->
# Frontend

Server-rendered Jinja2. Pure CSS (`app/static/estilo.css`, 417 lines) — no Tailwind/Bootstrap.
JS: `app/static/lateral.js` (48 lines, sidebar). No build step, no SPA, no client state store.

## Template tree (app/templates/)
```
base.html  (topbar + sidebar; uses dados_do_topo counts, token_csrf())
├─ _macros.html            shared form/table macros
├─ entrar.html  trocar_senha.html  erro.html (400/403/404/413)
├─ fila.html               queues: minha-fila / fila
│   └─ filas/_lista  _kanban  _quadro  _calendario   (per-user VisaoFila)
├─ concluidas.html  para_lancar.html  consultores.html  andamento_vistos.html
├─ tarefa.html             task detail: status, owner, planned date, notes, history
├─ programa.html  busca.html
├─ importacoes/lista  nova  detalhe   (preview → confirm/discard)
├─ painel/inicio.html      Painel VEG upload/download
├─ pautas.html  pauta.html Pautas TM list/detail  [PROTECTED]
├─ rsa/pagina.html         wraps uploaded RSA HTML
├─ ajuda_neg.html
└─ cadastros/_menu  usuarios  usuario  apelidos  servicos  publico_teen  catalogo  etapa  pautas
```

## Jinja filters / globals (app/web/__init__.py)
filters: data, data_hora (local time), status, separar_neg, vistos
globals: token_csrf, ROTULOS_STATUS, StatusTarefa, hoje, timedelta

## Interaction pattern
Plain HTML forms POST → redirect. Some fetch() JSON calls send `X-CSRF-Token`.
All user-facing text in plain Portuguese (AGENTS.md rule 6).
