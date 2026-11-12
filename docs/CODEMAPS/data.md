<!-- Generated: 2026-11-12 | Files scanned: 179 | Token estimate: ~800 -->
# Data

SQLite `<CHECKLIST_DADOS>/checklist.db` (default `instance/`), PRAGMA foreign_keys=ON, WAL, busy_timeout 30s.
SQLAlchemy 2.x typed `Mapped[]`. `ComDatas` mixin = criado_em/atualizado_em (app/models/base.py).
Match external records ONLY by Egali IDs (aluno_id_egali, compra_id_egali, programa_id_egali, item_checklist_egali).

## Tables (app/models/)
cadastro.py
  usuario            papel(consultor|estagiario|admin), senha_hash (PBKDF2), visao_fila
  apelido_consultor  texto → usuario_id, criado_por_id → usuario
  aluno              aluno_id_egali, teen flag
  programa           aluno_id → aluno, consultor_id → usuario, incorporado_ao_programa_id → programa,
                     ultima_importacao_id → importacao; TipoPrograma, SituacaoPrograma;
                     vip_egali (SA - VIP procedure or VIP tag); programa_id_egali empty when created by checklist
  compra             programa_id → programa; OrigemCompra
  servico_egali      CategoriaServico (incl. "ignorado")
  consultor_teen
catalogo.py
  trilha · etapa_modelo (trilha_id → trilha) · apelido_etapa (etapa_id → etapa_modelo)
tarefas.py
  tarefa             programa_id, compra_id, etapa_id → etapa_modelo, responsavel_manual_id → usuario,
                     ultima_importacao_id, lancada_egali_por_id; status StatusTarefa,
                     prazo_egali (defines lateness) vs data_planejada (estimate only), obs_egali (NEG)
  anotacao           tarefa_id, autor_id, lancada_egali_por_id   (team notes ≠ NEG)
  historico_tarefa   tarefa_id, usuario_id, importacao_id
importacoes.py
  importacao         TipoImportacao(BASE_ALUNOS|CHECKLIST), SituacaoImportacao(PREVIA|CONFIRMADA|…), iniciada_por_id
  ocorrencia_importacao  importacao_id, Gravidade, TipoOcorrencia, resolvida_por_id
pautas.py  [PROTECTED]
  pauta              consultor_id, estado_interno_por_id → usuario
  pauta_anotacao     pauta_id (CASCADE), autor_id
  pauta_historico    pauta_id (CASCADE), usuario_id
  colaborador_setor  name → sector map

StatusTarefa: a_fazer, em_andamento, aguardando_aluno (open) · concluida, nao_se_aplica

## Relationships
```
aluno 1─* programa 1─* compra
           │  └─* tarefa *─1 etapa_modelo *─1 trilha
           │        ├─* anotacao
           │        └─* historico_tarefa *─? importacao 1─* ocorrencia_importacao
usuario ─ consultor of programa/pauta, responsável of tarefa, author of notes/history
pauta 1─* pauta_anotacao, pauta_historico
```

## Migrations (migrations/versions/, linear, batch mode, idempotent)
7ff23d970b05 modelo_inicial
a1c3e5f70201 servico_ignorado
c182388d0923 importacao_da_base
af5ef57dd310 visualizacao_da_fila
b7d41e0c9a12 data_planejada
b863f41b75c9 publico_teen
a750f5567f2c organizar_por_e_lancamento_na_egali
ec1a54ac4fe8 senha_e_pautas
f4b7c9d2e1a0 origem_consultor_checklist
2d9c4a7e1b30 estado_interno_pautas
e3b9c1d7a520 vip_do_checklist        ← HEAD (programa.vip_egali)

Static data: app/dados/pautas_sla.csv (SLA hours per pauta category)
File data: <CHECKLIST_DADOS>/rsa/base.json (RSA panel base, built by checklist import, not in Git)
