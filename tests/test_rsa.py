"""RSA - Checklist do Suporte embutido e barra lateral. Só HTML sintético (o arquivo real tem nomes)."""

import io

import pytest

from app import rsa
from app.models import Papel, Usuario

# HTML mínimo com as mesmas âncoras do app do modelo base VEG.
RSA_SINTETICO = """<!doctype html><html><body>
<div id="login"></div>
<div id="app" class="hidden"><header class="topbar"></header><nav class="sidebar"></nav><main class="content" id="content"></main></div>
<script>
const APP_NOME_PADRAO='Checklist';
let DB={appNome:''}, SESSION=null, activePage='visao';
function saveDB(){}
function revealApp(u){ go(activePage); }
function go(page){ document.getElementById('content').textContent=page; }
</script>
</body></html>
"""


@pytest.fixture
def cliente(app, db, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))  # não mexe no instance/ de verdade
    admin = Usuario(nome="Admin Teste", email="admin@exemplo.com", papel=Papel.ADMIN)
    consultora = Usuario(nome="Consultora Teste", email="consultora@exemplo.com", papel=Papel.CONSULTOR)
    db.session.add_all([admin, consultora])
    db.session.commit()
    c = app.test_client()
    c.ids = {"admin": admin.id, "consultora": consultora.id}

    def entrar(quem):
        with c.session_transaction() as sessao:
            sessao["usuario_id"], sessao["csrf"] = c.ids[quem], "t"

    c.entrar = entrar
    return c


def enviar(cliente, conteudo, nome="APP_Checklist_Suporte_ao_Aluno.html"):
    return cliente.post("/rsa/enviar", data={"csrf": "t", "pagina": "visao", "arquivo": (io.BytesIO(conteudo), nome)},
                        content_type="multipart/form-data", follow_redirects=True)


def test_encaixe_abre_a_pagina_sem_login():
    saida = rsa.encaixar(RSA_SINTETICO, "atrasos", "Nome </script> Teste", admin=False)
    assert saida.startswith(RSA_SINTETICO[:RSA_SINTETICO.rfind("</body>")])
    assert 'activePage = "atrasos"' in saida and "revealApp(SESSION)" in saida
    assert '"Leitura"' in saida and "</script> Teste" not in saida  # nome não fecha a tag


def test_envio_e_paginas(cliente):
    cliente.entrar("admin")
    assert "Ainda não há o HTML do RSA" in cliente.get("/rsa/visao").get_data(as_text=True)
    assert "modelo base VEG" in enviar(cliente, b"<html></html>").get_data(as_text=True)
    assert "HTML do RSA guardado" in enviar(cliente, RSA_SINTETICO.encode()).get_data(as_text=True)

    pagina = cliente.get("/rsa/procedimentos").get_data(as_text=True)
    assert 'src="/rsa/procedimentos/app"' in pagina
    resposta = cliente.get("/rsa/procedimentos/app")
    assert resposta.status_code == 200
    assert resposta.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert 'activePage = "procedimentos"' in resposta.get_data(as_text=True)
    assert cliente.get("/rsa/credenciais/app").status_code == 200
    assert cliente.get("/rsa/nao-existe").status_code == 404


def test_consultor_nao_ve_sistema_nem_administracao(cliente):
    cliente.entrar("admin")
    enviar(cliente, RSA_SINTETICO.encode())
    menu_admin = cliente.get("/rsa/visao").get_data(as_text=True)
    assert "Sistema do RSA" in menu_admin and "Administração" in menu_admin

    cliente.entrar("consultora")
    menu = cliente.get("/rsa/visao").get_data(as_text=True)
    assert "RSA - Checklist do Suporte" in menu and "Prazos e Atrasos" in menu
    assert "Sistema do RSA" not in menu and "Administração" not in menu and "Importações" not in menu
    assert cliente.get("/rsa/credenciais").status_code == 403
    assert cliente.get("/rsa/testes/app").status_code == 403
    assert enviar(cliente, RSA_SINTETICO.encode()).status_code == 403


def test_menu_lateral(cliente):
    cliente.entrar("consultora")
    html = cliente.get("/minha-fila").get_data(as_text=True)
    for texto in ("Buscar aluno", "Filas de trabalho", "Minha fila", "Fila da equipe", "Por consultor", "Concluídas",
                  "Total de pautas", "Ação pendente da UN", "Quebrou na nossa UN", "Recolher menu"):
        assert texto in html, texto
    lateral = html[html.find('<nav class="sidebar"'):html.find("</nav>")]
    # Estes ficam só no menu do nome, não na lateral.
    for texto in ("Trocar senha", "Para lançar na Egali", "Quando usar NEG"):
        assert texto not in lateral and texto in html, texto
