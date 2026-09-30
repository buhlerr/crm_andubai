"""Integração com o painel VEG (checklist_VEG_*.html, do modelo base VEG).

O painel é um HTML de arquivo único, feito por outro analista: o Grupo 1
analisa o que já foi FINALIZADO no TM (pontualidade). Este módulo pega esse
HTML, sem mudar nada do que já existe nele, e encaixa um novo grupo de dados
com o BACKLOG (tarefas abertas) deste sistema, seguindo as regras do modelo:
- navegação em renderGruposDeDados(), sempre acima do grupo Sistema;
- rotas em go(page);
- uma seção no Manual de Instrução e uma seção na aba Testes (CHECKLIST);
- a melhoria registrada no CHANGELOG;
- APP_DESCRICAO atualizada;
- mesmas classes de CSS e mesmas funções de tela (kcard, itable, esc, nBR, pBR).

Tudo o que entra fica entre marcadores ">>> GRUPO ... BACKLOG DO SUPORTE >>>", para
poder ser tirado e posto de novo sem duplicar. Nenhum nome ou ID de aluno vai para
o arquivo: o HTML é feito para ser baixado e repassado.
"""

import json
import os
import re
from collections import Counter
from datetime import date

from app.extensions import db
from app.models import (
    STATUS_ABERTOS,
    ROTULOS_STATUS,
    Aluno,
    EtapaModelo,
    Programa,
    SituacaoPrograma,
    Tarefa,
    Trilha,
    Usuario,
)
from app.models.base import agora, hora_local

ESCOPO = "Suporte ao Aluno · BR-América do Norte e Dubai"
TITULO_GRUPO = "Backlog do Suporte"
AUTOR_CHANGELOG = "Sistema de filas do Suporte ao Aluno"
DESCRICAO_APP = "Procedimentos e backlog do Suporte ao Aluno"
DESC_CHANGELOG = (
    "Backlog do Suporte: retrato das tarefas abertas do checklist (atrasos, justificativas por NEG, "
    "vencimentos e carteira por consultor e responsável), gerado pelo sistema de filas do Suporte ao Aluno, "
    "sem nomes de alunos e com o público teen marcado."
)


class ErroPainel(Exception):
    pass


def _marcas(tipo: str) -> tuple[str, str]:
    return f">>> GRUPO BACKLOG DO SUPORTE · {tipo} >>>", f"<<< GRUPO BACKLOG DO SUPORTE · {tipo} <<<"


# ---------------------------------------------------------------- dados do retrato


def dados_backlog(hoje: date | None = None) -> dict:
    """Tarefas abertas de programas ativos, só com códigos (sem aluno)."""
    hoje = hoje or date.today()
    linhas = db.session.execute(
        db.select(
            Tarefa.prazo_egali, Tarefa.data_planejada, Tarefa.status, Tarefa.obs_egali,
            Trilha.nome, EtapaModelo.texto_egali, Programa.consultor_texto, Programa.consultor_id,
            Tarefa.responsavel_manual_id, Programa.pais, Aluno.id, Aluno.teen,
        )
        .join(Tarefa.programa).join(Programa.aluno).join(Tarefa.etapa).join(EtapaModelo.trilha)
        .where(Programa.situacao == SituacaoPrograma.ATIVO, Tarefa.status.in_(STATUS_ABERTOS))
        .order_by(Trilha.ordem, EtapaModelo.ordem)
    ).all()
    nomes = dict(db.session.execute(db.select(Usuario.id, Usuario.nome)).all())

    dic: dict[str, list[str]] = {k: [] for k in ("trilha", "proc", "cons", "resp", "status", "pais", "publico")}
    dic["publico"] = ["Suporte", "Teen"]
    indices: dict[str, dict[str, int]] = {k: {} for k in dic}
    for i, v in enumerate(dic["publico"]):
        indices["publico"][v] = i

    def cod(dim: str, valor: str) -> int:
        if valor not in indices[dim]:
            indices[dim][valor] = len(dic[dim])
            dic[dim].append(valor)
        return indices[dim][valor]

    col: dict[str, list[int]] = {k: [] for k in (*dic, "al", "atr", "neg", "plan", "venc")}
    alunos: dict[int, int] = {}
    for (prazo, planejada, status, neg, trilha, proc, consultor_texto, consultor_id,
         resp_manual, pais, aluno_id, teen) in linhas:
        consultor = nomes.get(consultor_id) or consultor_texto or "Sem consultor"
        responsavel = nomes.get(resp_manual) or nomes.get(consultor_id) or "Sem responsável"
        prevista = planejada or prazo
        col["trilha"].append(cod("trilha", trilha))
        col["proc"].append(cod("proc", proc))
        col["cons"].append(cod("cons", consultor))
        col["resp"].append(cod("resp", responsavel))
        col["status"].append(cod("status", ROTULOS_STATUS[status]))
        col["pais"].append(cod("pais", pais or "Não informado"))
        col["publico"].append(1 if teen else 0)
        col["al"].append(alunos.setdefault(aluno_id, len(alunos)))  # número sequencial, não o ID
        col["atr"].append(max(0, (hoje - prazo).days) if prazo else 0)
        col["neg"].append(1 if neg and neg.strip() else 0)
        col["plan"].append(1 if planejada else 0)
        col["venc"].append((prevista - hoje).days if prevista else -99999)

    from app.models import Importacao, SituacaoImportacao, TipoImportacao

    def ultima(tipo):
        quando = db.session.execute(
            db.select(Importacao.concluida_em)
            .filter_by(tipo=tipo, situacao=SituacaoImportacao.CONFIRMADA)
            .order_by(Importacao.concluida_em.desc())
        ).scalars().first()
        return hora_local(quando).strftime("%d/%m/%Y %H:%M") if quando else "—"

    programas = db.session.execute(
        db.select(db.func.count()).select_from(Programa).filter_by(situacao=SituacaoPrograma.ATIVO)
    ).scalar_one()
    return {
        "meta": {
            "n": len(linhas), "alunos": len(alunos), "programas_ativos": programas,
            "gerado_em": hora_local(agora()).strftime("%d/%m/%Y %H:%M"), "hoje": hoje.strftime("%d/%m/%Y"),
            "planilha": ultima(TipoImportacao.BASE_ALUNOS), "checklist": ultima(TipoImportacao.CHECKLIST),
            "escopo": ESCOPO,
        },
        "dic": dic,
        "col": col,
    }


# ---------------------------------------------------------------- código do grupo (JavaScript)

_JS_GRUPO = r"""
/* ===================== GRUPO __N__ · BACKLOG DO SUPORTE =====================
   Retrato das tarefas ABERTAS do checklist, gerado pelo sistema de filas do Suporte ao
   Aluno (Flask) na data de DADOS_BACKLOG.meta.gerado_em. Complementa o Grupo 1: lá, o que
   já foi finalizado (pontualidade); aqui, o que ainda está pendente (backlog e aderência).
   Sem nomes nem IDs de alunos (cada aluno é só um número sequencial). O público teen vem
   marcado, não excluído: o filtro Público = Suporte deixa a base comparável ao Grupo 1.
   Nada aqui grava no localStorage. Para atualizar, gere o HTML de novo no sistema de filas
   (Dados → Painel VEG); este bloco inteiro é substituído, o resto do arquivo não muda. */
const DADOS_BACKLOG = __DADOS__;
const DBL = (function(){ const R = DADOS_BACKLOG; return {meta:R.meta, dic:R.dic, col:R.col, n:R.meta.n}; })();

/* dimensões filtráveis, na ordem em que aparecem na barra de filtros */
const DIMS_BL = [
  ['trilha','Trilha'], ['proc','Procedimento'], ['cons','Consultor do programa'], ['resp','Responsável'],
  ['status','Status'], ['pais','País de destino'], ['publico','Público']
];
let FBL = {};           /* filtros ativos do grupo: dimensão -> índice do rótulo */

function linhasBL(){
  const ks = Object.keys(FBL).filter(k => FBL[k] != null), out = [];
  for (let i = 0; i < DBL.n; i++){
    let ok = true;
    for (const k of ks){ if (DBL.col[k][i] !== FBL[k]){ ok = false; break; } }
    if (ok) out.push(i);
  }
  return out;
}
function medianaBL(a){ if(!a.length) return null; a.sort((x,y)=>x-y); const m=a.length>>1; return a.length%2 ? a[m] : (a[m-1]+a[m])/2; }
function agregaBL(dim, rows){
  const g = new Map();
  for (const i of rows){
    const k = DBL.col[dim][i];
    let o = g.get(k);
    if(!o){ o = {k, n:0, atr:0, semNeg:0, dias:[], al:new Set()}; g.set(k,o); }
    o.n++; o.al.add(DBL.col.al[i]);
    if (DBL.col.atr[i] > 0){ o.atr++; o.dias.push(DBL.col.atr[i]); if(!DBL.col.neg[i]) o.semNeg++; }
  }
  return [...g.values()].map(o => ({k:o.k, rot:DBL.dic[dim][o.k], n:o.n, atr:o.atr, semNeg:o.semNeg,
    alunos:o.al.size, pAtr:o.n?o.atr/o.n:0, med:medianaBL(o.dias)})).sort((a,b)=>b.n-a.n);
}
function resumoBL(rows){
  let atr=0, semNeg=0, plan=0, venc7=0; const al=new Set(), d=[];
  for (const i of rows){
    al.add(DBL.col.al[i]);
    if (DBL.col.plan[i]) plan++;
    if (DBL.col.atr[i] > 0){ atr++; d.push(DBL.col.atr[i]); if(!DBL.col.neg[i]) semNeg++; }
    else if (DBL.col.venc[i] >= 0 && DBL.col.venc[i] <= 7) venc7++;
  }
  return {n:rows.length, alunos:al.size, atr, semNeg, plan, venc7, med:medianaBL(d)};
}

/* ---- filtros ---- */
function setFBL(dim, idx){ FBL[dim] = (FBL[dim]===idx) ? null : idx; if (FBL[dim]==null) delete FBL[dim]; go(activePage); }
function setFSelBL(dim, v){ if(v==='') delete FBL[dim]; else FBL[dim]=+v; go(activePage); }
function limparFBL(){ FBL={}; go(activePage); }
function barraFiltrosBL(){
  let sel='';
  for (const [k,rot] of DIMS_BL){
    const opts = DBL.dic[k].map((v,i)=>[i,v]).sort((a,b)=>a[1].localeCompare(b[1],'pt-BR'));
    sel += `<div class="dashf"><label>${esc(rot)}</label><select onchange="setFSelBL('${k}',this.value)">
      <option value="">Todos</option>${opts.map(([i,v])=>`<option value="${i}" ${FBL[k]===i?'selected':''}>${esc(v)}</option>`).join('')}
    </select></div>`;
  }
  const ativos = DIMS_BL.filter(([k])=>FBL[k]!=null);
  const chips = ativos.map(([k,rot])=>`<span class="fchip">${esc(rot)}: <b>${esc(DBL.dic[k][FBL[k]])}</b>
      <button onclick="setFBL('${k}',${FBL[k]})" title="Remover filtro">×</button></span>`).join('')
    + (ativos.length>1?`<button class="flimpar" onclick="limparFBL()">limpar todos</button>`:'');
  return `<div class="card dashbar"><div class="card-b">
      <div class="dashgrid">${sel}</div>
      ${ativos.length?`<div class="fchips">${chips}</div>`:''}
    </div></div>`;
}

function kpisBL(rows){
  const r = resumoBL(rows);
  return `<div class="kpis">
    ${kcard('Tarefas abertas', nBR(r.n), 'no retrato de '+DBL.meta.gerado_em, 'accent')}
    ${kcard('Alunos com pendência', nBR(r.alunos), r.alunos?('média de '+dBR(r.n/r.alunos)+' por aluno'):'')}
    ${kcard('Atrasadas', pBR(r.atr,r.n), nBR(r.atr)+' itens'+(r.med!=null?' · mediana de '+nBR(r.med)+'d':''), r.n&&r.atr/r.n>0.08?'neg':'pos')}
    ${kcard('Atrasadas sem NEG', nBR(r.semNeg), r.atr?(pBR(r.semNeg,r.atr)+' das atrasadas, sem justificativa'):'nenhuma atrasada', r.semNeg?'neg':'pos')}
    ${kcard('Vencem em 7 dias', nBR(r.venc7), 'ainda no prazo, pela data prevista')}
    ${kcard('Replanejadas', nBR(r.plan), 'data planejada pelo consultor')}
  </div>`;
}

/* ---- gráficos (SVG, mesmas cores do Grupo 1) ---- */
function barrasBL(rows, dim, top){
  const g = agregaBL(dim, rows).slice(0, top);
  if(!g.length) return '<div class="empty">Sem pendências no filtro atual.</div>';
  const W=1000, L=340, H=27, max=g[0].n;
  let s=`<svg viewBox="0 0 ${W} ${g.length*H+8}">`;
  g.forEach((o,i)=>{
    const y=i*H+4, w=(W-L-110)*o.n/max;
    const nome=o.rot.length>44?o.rot.slice(0,43)+'…':o.rot;
    s+=`<text class="sxn" x="${L-12}" y="${y+15}" text-anchor="end">${esc(nome)}</text>`;
    s+=`<rect class="bub" x="${L}" y="${y+3}" width="${Math.max(1,w)}" height="15" rx="2" fill="#0f9a94" fill-opacity=".28"
      onclick="setFBL('${dim}',${o.k})"><title>${esc(o.rot)}
${nBR(o.n)} abertas · ${nBR(o.alunos)} alunos · ${pBR(o.atr,o.n)} atrasadas · ${nBR(o.semNeg)} sem NEG</title></rect>`;
    s+=`<rect x="${L}" y="${y+3}" width="${Math.max(0,w*o.pAtr)}" height="15" rx="2" fill="#c8443b" fill-opacity=".85" pointer-events="none"/>`;
    s+=`<text class="sx" x="${L+w+10}" y="${y+15}">${nBR(o.n)} · ${pBR(o.atr,o.n)}</text>`;
  });
  s+='</svg>';
  return s+'<div class="dashnote">Barra clara = tarefas abertas. Trecho vermelho = parte já atrasada (pela data do procedimento na Egali).</div>';
}
function tabelaFaixasBL(titulo, faixas, contar){
  const fx = faixas.map(([rot,a,b])=>({rot, n:contar(a,b)}));
  const tot = fx.reduce((s,o)=>s+o.n,0) || 1, max = Math.max(1, ...fx.map(o=>o.n));
  return `<div class="card"><div class="card-h"><h3>${esc(titulo)}</h3></div><div class="card-b">
    <table class="data"><thead><tr><th>Faixa</th><th style="text-align:right">Itens</th><th style="text-align:right">%</th><th></th></tr></thead>
    <tbody>${fx.map(o=>`<tr><td>${o.rot}</td><td style="text-align:right">${nBR(o.n)}</td><td style="text-align:right">${pBR(o.n,tot)}</td>
      <td style="width:38%"><span class="minibar"><i style="width:${100*o.n/max}%"></i></span></td></tr>`).join('')}</tbody></table></div></div>`;
}
function vencimentosBL(rows){
  const v = rows.map(i=>DBL.col.venc[i]);
  return tabelaFaixasBL('Quando vence', [['Data prevista já passou',-99998,-1],['Hoje',0,0],['1 a 7 dias',1,7],['8 a 14 dias',8,14],
    ['15 a 30 dias',15,30],['31 a 60 dias',31,60],['mais de 60 dias',61,1e9],['Sem data',-1e9,-99999]],
    (a,b)=>v.filter(d=>d>=a&&d<=b).length);
}
function faixasAtrasoBL(rows){
  const d = rows.map(i=>DBL.col.atr[i]).filter(x=>x>0);
  return tabelaFaixasBL('Há quanto tempo está atrasada', [['1 dia',1,1],['2 a 3 dias',2,3],['4 a 7 dias',4,7],['8 a 15 dias',8,15],
    ['16 a 30 dias',16,30],['31 a 90 dias',31,90],['mais de 90 dias',91,1e9]], (a,b)=>d.filter(x=>x>=a&&x<=b).length);
}

/* ---- tabela padrão de uma dimensão ---- */
function tabelaBL(id, dim, rows, rotulo){
  const g = agregaBL(dim, rows);
  if(!g.length) return '<div class="empty">Sem pendências no filtro atual.</div>';
  return itable(id, [
    {h:rotulo, get:r=>r.rot, fmt:(v,r)=>`<a class="flink" onclick="setFBL('${dim}',${r.k})">${esc(v)}</a>`},
    {h:'Abertas', type:'num', get:r=>r.n, fmt:v=>nBR(v)},
    {h:'Alunos', type:'num', get:r=>r.alunos, fmt:v=>nBR(v)},
    {h:'Atrasadas', type:'num', get:r=>r.atr, fmt:v=>nBR(v)},
    {h:'% atraso', type:'num', get:r=>r.pAtr, fmt:(v,r)=>`<span class="${v>0.15&&r.n>=20?'warnv':''}">${pBR(r.atr,r.n)}</span>`},
    {h:'Atrasadas sem NEG', type:'num', get:r=>r.semNeg, fmt:v=>`<span class="${v>0?'warnv':''}">${nBR(v)}</span>`},
    {h:'Atraso mediano', type:'num', get:r=>r.med==null?'':r.med, fmt:v=>v===''?'—':nBR(v)+'d'}
  ], g, 1, 'desc');
}

function cabecalhoBL(titulo, texto){
  return `<div class="page-head"><div class="eyebrow">Backlog do Suporte</div><h1>${esc(titulo)}</h1><p>${texto}</p></div>`;
}
function retratoBL(){
  const m = DBL.meta;
  return `<div class="test-note">Retrato de <b>${esc(m.gerado_em)}</b> · planilha de alunos de ${esc(m.planilha)} · checklist de ${esc(m.checklist)}
    · escopo: ${esc(m.escopo)}. O público teen está <b>marcado, não excluído</b>: use Público = Suporte para comparar com o Grupo 1.</div>`;
}

/* ---- páginas ---- */
function renderBacklogVisao(){
  const rows = linhasBL();
  return cabecalhoBL('Visão do Backlog',
    `Tarefas abertas do checklist no sistema de filas, em ${esc(DBL.meta.programas_ativos)} programas ativos. É o que o Grupo 1 não mede:
     lá, o que já foi finalizado; aqui, o que ainda falta fazer e o quanto disso já passou do prazo.`)
    + retratoBL() + barraFiltrosBL() + kpisBL(rows)
    + `<div class="dash2">
      <div class="card"><div class="card-h"><h3>Por trilha</h3><span class="sub">clique para filtrar</span></div>
        <div class="card-b">${barrasBL(rows,'trilha',10)}</div></div>
      ${vencimentosBL(rows)}
    </div>
    <div class="card"><div class="card-h"><h3>Procedimentos com mais pendências</h3><span class="sub">top 12</span></div>
      <div class="card-b">${barrasBL(rows,'proc',12)}</div></div>`;
}
function renderBacklogProc(){
  const rows = linhasBL();
  return cabecalhoBL('Pendências por Procedimento',
    'Quantas tarefas de cada procedimento estão abertas, quantas já passaram do prazo e quantas estão atrasadas sem NEG. Clique no nome para filtrar o grupo inteiro.')
    + retratoBL() + barraFiltrosBL() + kpisBL(rows)
    + `<div class="card-h" style="border:0;padding-left:0"><h3>Todos os procedimentos</h3></div>
      ${tabelaBL('tb_bl_proc','proc',rows,'Procedimento')}`;
}
function renderBacklogPessoas(){
  const rows = linhasBL();
  return cabecalhoBL('Carteira por Consultor',
    `<b>Consultor</b> é o dono do programa, que vem da planilha de alunos. <b>Responsável</b> é quem vai executar a tarefa: é o consultor,
     a não ser que a tarefa tenha sido passada a outra pessoa no sistema (ex.: a estagiária).`)
    + retratoBL() + barraFiltrosBL()
    + `<div class="card"><div class="card-h"><h3>Pendências por responsável</h3><span class="sub">top 12</span></div>
        <div class="card-b">${barrasBL(rows,'resp',12)}</div></div>
      <div class="card-h" style="border:0;padding-left:0"><h3>Consultores do programa</h3></div>
      ${tabelaBL('tb_bl_cons','cons',rows,'Consultor')}
      <div class="card-h" style="border:0;padding-left:0;margin-top:22px"><h3>Responsáveis</h3></div>
      ${tabelaBL('tb_bl_resp','resp',rows,'Responsável')}`;
}
function renderBacklogAtrasos(){
  const rows = linhasBL();
  const g = agregaBL('proc', rows).filter(o=>o.atr>0).sort((a,b)=>b.semNeg-a.semNeg || b.atr-a.atr).slice(0,15);
  const rk = g.map(o=>`<tr><td><a class="flink" onclick="setFBL('proc',${o.k})">${esc(o.rot)}</a></td>
      <td style="text-align:right">${nBR(o.n)}</td><td style="text-align:right">${nBR(o.atr)}</td>
      <td style="text-align:right"><span class="${o.semNeg?'warnv':''}">${nBR(o.semNeg)}</span></td>
      <td style="text-align:right">${o.med==null?'—':nBR(o.med)+'d'}</td></tr>`).join('');
  return cabecalhoBL('Atrasos e Justificativas',
    `Atrasada = tarefa aberta cuja <b>data do procedimento</b> na Egali (fixa) já passou no dia do retrato. A data planejada pelo consultor
     não muda o atraso. Justificativa = observação no botão NEG do TM. Atrasada sem NEG é o que precisa de atenção primeiro.`)
    + retratoBL() + barraFiltrosBL() + kpisBL(rows)
    + `<div class="card"><div class="card-h"><h3>Onde estão as atrasadas sem justificativa</h3><span class="sub">top 15 procedimentos</span></div>
      <div class="card-b"><table class="data"><thead><tr><th>Procedimento</th><th style="text-align:right">Abertas</th>
        <th style="text-align:right">Atrasadas</th><th style="text-align:right">Sem NEG</th><th style="text-align:right">Mediana</th></tr></thead>
        <tbody>${rk||'<tr><td colspan="5" class="empty">Nenhuma tarefa atrasada no filtro atual.</td></tr>'}</tbody></table></div></div>
    <div class="dash2">${faixasAtrasoBL(rows)}${vencimentosBL(rows)}</div>`;
}
"""

_MANUAL = """
      <h2>__SECAO__. Grupo __N__ · Backlog do Suporte</h2>
      <p>Este grupo é gerado pelo <b>sistema de filas do Suporte ao Aluno</b> (o sistema onde a equipe trabalha as tarefas do checklist no dia a dia) e mostra o que ainda está <b>aberto</b>. Ele completa o Grupo 1: lá, a pontualidade do que já foi finalizado; aqui, o backlog. É um <b>retrato</b>: vale para a data e a hora mostradas no topo de cada página. Para atualizar, gere o HTML de novo no sistema de filas, em <b>Dados → Painel VEG</b>; só este grupo é substituído, o resto do arquivo continua igual.</p>
      <ul>
        <li><b>Visão do Backlog</b>: totais, pendências por trilha, quando cada tarefa vence e os procedimentos com mais pendências.</li>
        <li><b>Pendências por Procedimento</b>: abertas, atrasadas e atrasadas sem NEG de cada procedimento.</li>
        <li><b>Carteira por Consultor</b>: por consultor do programa (dono do aluno, vem da planilha) e por responsável (quem executa, que pode ser outra pessoa, como a estagiária).</li>
        <li><b>Atrasos e Justificativas</b>: onde estão as atrasadas sem NEG, há quanto tempo estão atrasadas e quando o restante vence.</li>
      </ul>
      <h3>Como os números são contados</h3>
      <p>Entram as tarefas abertas (A fazer, Em andamento, Aguardando aluno) de programas ativos. <b>Atrasada</b> é a tarefa cuja <b>data do procedimento</b> na Egali, que é fixa, já passou no dia do retrato. A <b>data planejada</b> que o consultor escolhe no sistema de filas não muda o atraso: ela só define quando a tarefa aparece em "Quando vence". <b>Justificativa</b> é ter observação no botão NEG do TM.</p>
      <h3>Escopo e público teen</h3>
      <p>O sistema de filas cobre a unidade <b>__ESCOPO__</b>, enquanto o Grupo 1 traz todas as empresas e destinos: compare os dois com isso em mente. O <b>público teen</b> não é excluído deste grupo, e sim <b>marcado</b>, pela mesma regra do Grupo 1 (Summer Schools, Winter Schools, Viagem Cultural, Vancouver Experience, tag <code>summer</code> ou consultor da equipe teen). Use o filtro <b>Público = Suporte</b> para deixar a base comparável ao Grupo 1.</p>
      <div class="callout"><b>Sem nomes de alunos:</b> este arquivo é feito para ser baixado e repassado, então leva só números e códigos. O detalhe de cada aluno e de cada tarefa fica no sistema de filas.</div>
"""

_TESTES = [
    ("1", "Visão do Backlog abre com os totais e o retrato mostra data, planilha, checklist e escopo"),
    ("2", "Os filtros do grupo se combinam entre si (ex.: trilha + responsável) e os totais acompanham"),
    ("3", "Clicar em uma barra ou no nome dentro de uma tabela filtra todas as páginas do grupo"),
    ("4", "Os filtros do Grupo 1 e os deste grupo são independentes: filtrar um não muda o outro"),
    ("5", "Público = Suporte esconde os alunos teen; Público = Teen mostra só eles"),
    ("6", "Pendências por Procedimento: busca e ordenação funcionam na tabela completa"),
    ("7", "Carteira por Consultor mostra consultores e responsáveis em tabelas separadas"),
    ("8", "Atrasos e Justificativas lista as atrasadas sem NEG, as faixas de atraso e os vencimentos"),
    ("9", "Nenhum nome ou ID de aluno aparece em qualquer página do grupo"),
    ("10", "O grupo aparece acima do grupo Sistema no menu"),
]


# ---------------------------------------------------------------- encaixe no HTML


def _achar(texto: str, trecho: str, onde: str, inicio: int = 0) -> int:
    i = texto.find(trecho, inicio)
    if i < 0:
        raise ErroPainel(
            f"O HTML não parece ser do modelo base VEG: não encontrei {onde}. "
            "Envie o arquivo checklist_VEG_*.html original, baixado do próprio painel."
        )
    return i


def _fim_da_funcao(texto: str, inicio: int) -> int:
    """Posição do '\\n}' que fecha a função de primeiro nível que começa em `inicio`."""
    return _achar(texto, "\n}\n", "o fim da função", inicio)


def _renumerar_manual(texto: str, a_partir_de: int, fim: int, passo: int) -> str:
    trecho = texto[a_partir_de:fim]
    trecho = re.sub(r"<h2>(\d+)\. ", lambda m: f"<h2>{int(m.group(1)) + passo}. ", trecho)
    return texto[:a_partir_de] + trecho + texto[fim:]


def retirar_grupo(html: str) -> str:
    """Tira um Grupo Backlog colocado antes por este sistema (se houver), voltando ao arquivo original."""
    # Cada bloco é tirado com exatamente as quebras de linha que encaixar_grupo() pôs depois dele.
    for tipo, sufixo in (("DADOS", "\n\n"), ("NAV", "\n"), ("ROTAS", "\n"), ("TESTES", "\n"), ("CHANGELOG", "\n")):
        abre, fecha = _marcas(tipo)
        html = re.sub(r"[ \t]*/\* " + re.escape(abre) + r" \*/.*?/\* " + re.escape(fecha) + r" \*/" + sufixo, "", html, flags=re.S)
    abre, fecha = _marcas("MANUAL")
    m = re.search(r"[ \t]*<!-- " + re.escape(abre) + r" -->.*?<!-- " + re.escape(fecha) + r" -->\n\n", html, flags=re.S)
    if m:
        html = html[:m.start()] + html[m.end():]
        fim = _fim_da_funcao(html, m.start())
        html = _renumerar_manual(html, m.start(), fim, -1)
    abre, _ = _marcas("DESCRICAO")
    m = re.search(r"const APP_DESCRICAO = '[^']*'; /\* " + re.escape(abre) + r" original: (.*?) \*/", html)
    if m:
        html = html[:m.start()] + f"const APP_DESCRICAO = {m.group(1)};" + html[m.end():]
    return html


def encaixar_grupo(html: str, dados: dict, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    html = retirar_grupo(html.replace("\r\n", "\n"))

    # Confere que é o modelo VEG antes de mexer.
    inicio_nav = _achar(html, "function renderGruposDeDados(){", "a função renderGruposDeDados()")
    _achar(html, "function renderGrupoSistema(){", "a função renderGrupoSistema()")
    _achar(html, "function go(page){", "a função go(page)")
    _achar(html, "/* ===================== NAV ===================== */", "a seção NAV")
    _achar(html, "const CHECKLIST=[", "a lista CHECKLIST da aba Testes")
    _achar(html, "const CHANGELOG=[", "o CHANGELOG")
    _achar(html, "function renderManual(){", "a função renderManual()")
    # Funções de tela do modelo que o grupo reaproveita.
    for funcao in ("esc", "kcard", "itable", "nBR", "pBR", "dBR"):
        _achar(html, f"function {funcao}(", f"a função {funcao}()")

    # Próximo número de grupo livre (hoje: 2, porque o Grupo 1 é o Checklist do Suporte).
    fim_nav = _fim_da_funcao(html, inicio_nav)
    numeros = [int(n) for n in re.findall(r'<div class="gh">(\d+) · ', html[inicio_nav:fim_nav])]
    n = max(numeros, default=0) + 1

    # 1) dados + motor + páginas: logo antes da seção NAV, depois dos grupos que já existem
    abre, fecha = _marcas("DADOS")
    json_dados = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    bloco = f"/* {abre} */" + _JS_GRUPO.replace("__N__", str(n)).replace("__DADOS__", json_dados) + f"/* {fecha} */\n\n"
    i = _achar(html, "/* ===================== NAV ===================== */", "a seção NAV")
    html = html[:i] + bloco + html[i:]

    # 2) navegação: dentro de renderGruposDeDados(), antes do "return h;" (o Sistema continua vindo depois, pelo buildNav)
    inicio_nav = _achar(html, "function renderGruposDeDados(){", "renderGruposDeDados()")
    fim_nav = _fim_da_funcao(html, inicio_nav)
    ret = html.rfind("  return h;", inicio_nav, fim_nav)
    if ret < 0:
        raise ErroPainel("Não encontrei o 'return h;' de renderGruposDeDados().")
    abre, fecha = _marcas("NAV")
    nav = (f"  /* {abre} */\n"
           f"  h+='<div class=\"nav-group\"><div class=\"gh\">{n} · {TITULO_GRUPO}</div>';\n"
           "  h+=navItem('bl_visao','Visão do Backlog','ok');\n"
           "  h+=navItem('bl_proc','Pendências por Procedimento','ok');\n"
           "  h+=navItem('bl_pessoas','Carteira por Consultor','ok');\n"
           "  h+=navItem('bl_atrasos','Atrasos e Justificativas','ok');\n"
           "  h+='</div>';\n"
           f"  /* {fecha} */\n")
    html = html[:ret] + nav + html[ret:]

    # 3) rotas: em go(page), antes do c.scrollTop
    inicio_go = _achar(html, "function go(page){", "go(page)")
    fim_go = _fim_da_funcao(html, inicio_go)
    rolagem = html.rfind("  c.scrollTop=0;", inicio_go, fim_go)
    if rolagem < 0:
        raise ErroPainel("Não encontrei o 'c.scrollTop=0;' de go(page).")
    abre, fecha = _marcas("ROTAS")
    rotas = (f"  /* {abre} */\n"
             f"  /* Grupo {n} · {TITULO_GRUPO} */\n"
             "  else if(page==='bl_visao') c.innerHTML=renderBacklogVisao();\n"
             "  else if(page==='bl_proc') c.innerHTML=renderBacklogProc();\n"
             "  else if(page==='bl_pessoas') c.innerHTML=renderBacklogPessoas();\n"
             "  else if(page==='bl_atrasos') c.innerHTML=renderBacklogAtrasos();\n"
             f"  /* {fecha} */\n")
    html = html[:rolagem] + rotas + html[rolagem:]

    # 4) Manual: seção nova antes de "Baixar HTML" (logo depois dos grupos de dados), renumerando as seguintes
    inicio_manual = _achar(html, "function renderManual(){", "renderManual()")
    fim_manual = _fim_da_funcao(html, inicio_manual)
    m = re.search(r"[ \t]*<h2>(\d+)\. Baixar HTML", html[inicio_manual:fim_manual])
    if not m:
        raise ErroPainel("Não encontrei a seção 'Baixar HTML' do Manual de Instrução.")
    pos = inicio_manual + m.start()
    secao = int(m.group(1))
    html = _renumerar_manual(html, pos, fim_manual, +1)
    abre, fecha = _marcas("MANUAL")
    manual = (f"      <!-- {abre} -->" + _MANUAL.replace("__SECAO__", str(secao)).replace("__N__", str(n))
              .replace("__ESCOPO__", dados["meta"]["escopo"]) + f"      <!-- {fecha} -->\n\n")
    html = html[:pos] + manual + html[pos:]

    # 5) Testes: uma seção nova no CHECKLIST, antes da seção de Estrutura de Navegação (ou no fim)
    inicio_ck = _achar(html, "const CHECKLIST=[", "CHECKLIST")
    fim_ck = _achar(html, "\n];", "o fim do CHECKLIST", inicio_ck)
    letras_usadas = set(re.findall(r"\{sec:'([A-Z])\.", html[inicio_ck:fim_ck]))
    letra = next(c for c in "JKLMNOPQRSTUVWXYZ" if c not in letras_usadas)
    abre, fecha = _marcas("TESTES")
    itens = ",\n".join(f"    {{id:'{letra}{i}', t:'{t}'}}" for i, t in _TESTES)
    testes = (f"  /* {abre} */\n  {{sec:'{letra}. {TITULO_GRUPO} (grupo de dados)', itens:[\n{itens},\n  ]}},\n  /* {fecha} */\n")
    antes = html.find("  {sec:'H. Estrutura de Navegação'", inicio_ck, fim_ck)
    pos = antes if antes >= 0 else fim_ck + 1
    html = html[:pos] + testes + html[pos:]

    # 6) CHANGELOG: registra a melhoria (a migrate() do modelo leva para quem já tinha o app aberto)
    inicio_cl = _achar(html, "const CHANGELOG=[", "CHANGELOG")
    fim_cl = _achar(html, "\n];", "o fim do CHANGELOG", inicio_cl)
    abre, fecha = _marcas("CHANGELOG")
    entrada = (f"  /* {abre} */\n  {{data:'{hoje:%d/%m/%Y}', autor:'{AUTOR_CHANGELOG}', area:'{TITULO_GRUPO}', "
               f"desc:'Grupo {n} · {DESC_CHANGELOG}', status:'Concluído'}},\n  /* {fecha} */\n")
    html = html[:fim_cl + 1] + entrada + html[fim_cl + 1:]

    # 7) APP_DESCRICAO: o modelo pede para atualizar quando um grupo novo entra (guarda a original para poder desfazer)
    m = re.search(r"const APP_DESCRICAO = ('[^']*');", html)
    if m:
        abre, _ = _marcas("DESCRICAO")
        html = html[:m.start()] + f"const APP_DESCRICAO = '{DESCRICAO_APP}'; /* {abre} original: {m.group(1)} */" + html[m.end():]
    return html


def validar(html: str) -> str:
    """Confere que o HTML é do modelo VEG (encaixando o grupo com dados vazios) e devolve a base limpa."""
    base = retirar_grupo(html.replace("\r\n", "\n"))
    vazio = {"meta": {"escopo": ESCOPO}, "dic": {}, "col": {}}
    encaixar_grupo(base, vazio)
    return base


# ---------------------------------------------------------------- HTML base guardado (instance/painel_veg)


def _pasta() -> str:
    from flask import current_app

    pasta = os.path.join(current_app.instance_path, "painel_veg")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def guardar_base(conteudo: bytes, nome_original: str, usuario: str) -> dict:
    """Guarda o HTML do painel enviado pelo administrador, sem o grupo Backlog (se já viesse com ele)."""
    try:
        html = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErroPainel("O arquivo não está em UTF-8. Envie o HTML exatamente como foi baixado do painel.")
    base = validar(html)
    info = {
        "nome_original": nome_original,
        "app_nome": nome_do_arquivo(base).rsplit("_VEG_", 1)[0],
        "enviado_em": hora_local(agora()).strftime("%d/%m/%Y %H:%M"),
        "enviado_por": usuario,
        "tamanho_kb": round(len(conteudo) / 1024),
    }
    pasta = _pasta()
    with open(os.path.join(pasta, "base.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(base)
    with open(os.path.join(pasta, "base.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info


def base_guardada() -> tuple[str, dict] | None:
    pasta = _pasta()
    caminho = os.path.join(pasta, "base.html")
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as f:
        html = f.read()
    try:
        with open(os.path.join(pasta, "base.json"), encoding="utf-8") as f:
            info = json.load(f)
    except (OSError, ValueError):
        info = {}
    return html, info


def nome_do_arquivo(html: str, hoje: date | None = None) -> str:
    """Mesmo padrão do downloadHTML() do modelo: <nome do app>_VEG_dd-mm-aaaa.html."""
    hoje = hoje or date.today()
    m = re.search(r'"appNome":"([^"]+)"', html)
    base = re.sub(r"[^A-Za-z0-9]+", "_", (m.group(1) if m else "checklist")).strip("_") or "checklist"
    return f"{base}_VEG_{hoje:%d-%m-%Y}.html"
