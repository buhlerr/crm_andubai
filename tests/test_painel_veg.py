import io
import re
from datetime import date, timedelta

import pytest

from app import painel_veg
from app.catalogo_inicial import carregar_catalogo
from app.importacao import base_alunos, checklist
from app.models import Papel, Usuario

HOJE = date.today()

# HTML mínimo com as mesmas âncoras do modelo base VEG (nunca o arquivo real, que tem dados).
VEG_SINTETICO = """<!doctype html><html><head><title>Checklist</title></head><body>
<script>
const SNAPSHOT = {"appNome":"Painel de Teste"};
const APP_DESCRICAO = 'Procedimentos de teste'; /* PERSONALIZAR */
const CHANGELOG=[
  {data:'01/09/2026', area:'Base', desc:'Carga inicial.', status:'Concluído'},
];
function esc(s){ return String(s); }
function nBR(n){ return String(n); }
function pBR(n){ return String(n); }
function dBR(n){ return String(n); }

/* ===================== NAV ===================== */
function renderGruposDeDados(){
  let h='';
  h+='<div class="nav-group"><div class="gh">1 · Checklist do Suporte</div>';
  h+=navItem('visao','Visão Geral','ok');
  h+='</div>';
  return h;
}
function renderGrupoSistema(){
  let h='<div class="nav-group"><div class="gh">Sistema</div>';
  h+=navItem('manual','Manual de Instrução','');
  h+='</div>';
  return h;
}
function navItem(page,label,tag){ return label; }
function go(page){
  const c=document.getElementById('content');
  if(page==='manual') c.innerHTML=renderManual();
  else if(page==='visao') c.innerHTML=renderVisao();
  c.scrollTop=0;
}
function kcard(a){ return a; }
function itable(a){ return a; }
function renderManual(){
  return `<div class="doc">
      <h2>1. O que é esta aplicação</h2>
      <p>Texto.</p>

      <h2>2. Grupo 1 · Checklist do Suporte</h2>
      <p>Texto.</p>

      <h2>3. Baixar HTML e compartilhar</h2>
      <p>Texto.</p>

      <h2>4. Salvar</h2>
      <p>Texto.</p>
    </div>`;
}
const CHECKLIST=[
  {sec:'A. Login e Sessão', itens:[
    {id:'A1', t:'Login funciona'},
  ]},
  {sec:'H. Estrutura de Navegação', itens:[
    {id:'H1', t:'Grupos acima do Sistema'},
  ]},
];
</script></body></html>
"""


def manual(html):
    inicio = html.find("function renderManual(){")
    return re.findall(r"<h2>(\d+\. [^<]+)</h2>", html[inicio:html.find("const CHECKLIST=[")])


def dados_vazios():
    return {"meta": {"escopo": painel_veg.ESCOPO}, "dic": {}, "col": {}}


def test_encaixa_grupo_acima_do_sistema_e_nas_regras_do_modelo():
    saida = painel_veg.encaixar_grupo(VEG_SINTETICO, dados_vazios(), date(2026, 9, 29))
    nav = saida[saida.find("function renderGruposDeDados(){"):saida.find("function renderGrupoSistema(){")]
    assert re.findall(r'class=\\?"gh\\?">([^<]+)<', nav) == ["1 · Checklist do Suporte", "2 · Backlog do Suporte"]
    assert saida.find("renderBacklogVisao()") < saida.find("c.scrollTop=0;")
    assert saida.find("const DADOS_BACKLOG") < saida.find("/* ===================== NAV")
    assert manual(saida) == ["1. O que é esta aplicação", "2. Grupo 1 · Checklist do Suporte", "3. Grupo 2 · Backlog do Suporte",
                             "4. Baixar HTML e compartilhar", "5. Salvar"]
    secoes = re.findall(r"\{sec:'([^']+)'", saida)
    assert secoes == ["A. Login e Sessão", "J. Backlog do Suporte (grupo de dados)", "H. Estrutura de Navegação"]
    assert "area:'Backlog do Suporte'" in saida and "data:'29/09/2026'" in saida
    assert f"const APP_DESCRICAO = '{painel_veg.DESCRICAO_APP}';" in saida


def test_retirar_devolve_o_original_e_nao_duplica():
    saida = painel_veg.encaixar_grupo(VEG_SINTETICO, dados_vazios(), date(2026, 9, 29))
    assert painel_veg.retirar_grupo(saida) == VEG_SINTETICO
    assert painel_veg.encaixar_grupo(saida, dados_vazios(), date(2026, 9, 29)) == saida
    assert painel_veg.encaixar_grupo(VEG_SINTETICO.replace("\n", "\r\n"), dados_vazios(), date(2026, 9, 29)) == saida


def test_recusa_html_que_nao_e_do_modelo():
    with pytest.raises(painel_veg.ErroPainel, match="modelo base VEG"):
        painel_veg.validar("<html><body>outra coisa</body></html>")
    with pytest.raises(painel_veg.ErroPainel):
        painel_veg.validar(VEG_SINTETICO.replace("function renderGrupoSistema(){", "function outra(){"))


def test_nome_do_arquivo_segue_o_modelo():
    assert painel_veg.nome_do_arquivo(VEG_SINTETICO, date(2026, 9, 29)) == "Painel_de_Teste_VEG_29-09-2026.html"


@pytest.fixture
def cenario(db):
    carregar_catalogo()
    db.session.add(Usuario(nome="Consultora Ana", email="ana@exemplo.test", papel=Papel.ADMIN))
    db.session.commit()
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "1", "aluno_id": "10", "aluno_name": "Fulana Beltrana Sicrano",
                                 "compra_id": "100", "consultor": "Consultora Ana", "pais": "Canadá"}},
    ]))
    checklist.confirmar(checklist.criar_previa([
        {"linha": 2, "valores": {"#": "901", "id da compra": "100", "id aluno": "10",
                                 "procedimento": "SA - GERAL - Cadastrar flight details",
                                 "data": (HOJE - timedelta(days=3)).strftime("%d/%m/%Y"), "status": "Aguardando",
                                 "serviço": "Curso Premium", "neg": ""}},
    ], periodo_completo=True))


def test_dados_do_backlog_sem_aluno(db, cenario):
    dados = painel_veg.dados_backlog(HOJE)
    assert dados["meta"]["n"] == 1 and dados["meta"]["alunos"] == 1
    assert dados["col"]["atr"] == [3] and dados["col"]["neg"] == [0] and dados["col"]["al"] == [0]
    saida = painel_veg.encaixar_grupo(VEG_SINTETICO, dados, HOJE)
    assert "Fulana" not in saida and '"10"' not in saida.split("const DADOS_BACKLOG")[1][:2000]


def test_tela_envio_e_download(db, cenario, app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))  # não mexe no instance/ de verdade
    cliente = app.test_client()
    admin = db.session.execute(db.select(Usuario)).scalar_one()
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = admin.id, "t"
    assert "Ainda não há painel guardado" in cliente.get("/painel-veg/").get_data(as_text=True)

    ruim = cliente.post("/painel-veg/enviar", data={"csrf": "t", "arquivo": (io.BytesIO(b"<html></html>"), "x.html")},
                        content_type="multipart/form-data", follow_redirects=True)
    assert "modelo base VEG" in ruim.get_data(as_text=True)

    cliente.post("/painel-veg/enviar", data={"csrf": "t", "arquivo": (io.BytesIO(VEG_SINTETICO.encode()), "checklist_VEG.html")},
                 content_type="multipart/form-data")
    assert "Baixar HTML com o Backlog do Suporte" in cliente.get("/painel-veg/").get_data(as_text=True)

    resposta = cliente.get("/painel-veg/baixar")
    assert resposta.status_code == 200
    assert "attachment" in resposta.headers["Content-Disposition"]
    assert f"Painel_de_Teste_VEG_{HOJE:%d-%m-%Y}.html" in resposta.headers["Content-Disposition"]
    html = resposta.get_data(as_text=True)
    assert "2 · Backlog do Suporte" in html and "Fulana" not in html
