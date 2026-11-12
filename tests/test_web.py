import io
import os
from datetime import date, timedelta

import pytest

from app.catalogo_inicial import carregar_catalogo
from app.importacao import base_alunos, checklist
from app.importacao.leitor_csv import ler_texto_csv
from app.models import (
    ApelidoConsultor,
    CategoriaServico,
    HistoricoTarefa,
    Importacao,
    Papel,
    Programa,
    ServicoEgali,
    SituacaoImportacao,
    StatusTarefa,
    Tarefa,
    Usuario,
    VisaoFila,
)
from app.web.auth import destino_seguro

TOKEN = "token-de-teste"
HOJE = date.today()


def br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


@pytest.fixture
def dados(db):
    carregar_catalogo()
    admin = Usuario(nome="Admin Teste", email="admin@exemplo.test", papel=Papel.ADMIN)
    ana = Usuario(nome="Consultora Ana", email="ana@exemplo.test")
    bia = Usuario(nome="Consultora Bia", email="bia@exemplo.test")
    estagiaria = Usuario(nome="Estagiária Cida", email="cida@exemplo.test", papel=Papel.ESTAGIARIO)
    db.session.add_all([admin, ana, bia, estagiaria])
    db.session.commit()
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "1", "aluno_id": "10", "aluno_name": "Aluno Um", "compra_id": "100, 101",
                                 "consultor": "Consultora Ana", "pais_name": "Canadá", "pt_prog": 90.0}},
        {"linha": 3, "valores": {"programa_id": "2", "aluno_id": "20", "aluno_name": "Aluno Dois", "compra_id": "200",
                                 "consultor": "Consultora Bia", "pais_name": "EUA"}},
        {"linha": 4, "valores": {"programa_id": "3", "aluno_id": "30", "aluno_name": "Aluno Três", "compra_id": "300",
                                 "consultor": "Nome Desconhecido"}},
    ]))

    def item(n, numero, compra, aluno, procedimento, prazo, neg=""):
        return {"linha": n, "valores": {"#": numero, "id da compra": compra, "id aluno": aluno, "procedimento": procedimento,
                                        "data": br(prazo), "status": "Aguardando", "neg": neg, "serviço": "Curso Premium"}}

    checklist.confirmar(checklist.criar_previa([
        item(2, "901", "100", "10", "SA - GERAL - Cadastrar flight details", HOJE - timedelta(days=5), "17/09 - aguardando visto"),
        item(3, "902", "101", "10", "SA - VISTOS - Ter uma cópia do visto/negativa", HOJE - timedelta(days=3)),
        item(4, "903", "200", "20", "SA - EUA - Agendamento do aluno", HOJE + timedelta(days=10)),
        item(5, "904", "300", "30", "SA - GERAL - Cadastrar flight details", HOJE + timedelta(days=20)),
    ], periodo_completo=True))
    return {"admin": admin, "ana": ana, "bia": bia, "estagiaria": estagiaria}


@pytest.fixture
def cliente(app):
    return app.test_client()


def entrar(cliente, usuario):
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"] = usuario.id
        sessao["csrf"] = TOKEN


def tarefa(db, numero) -> Tarefa:
    return db.session.execute(db.select(Tarefa).filter_by(item_checklist_egali=numero)).scalar_one()


def texto(resposta) -> str:
    """A página sem o formulário de filtros: o seletor de procedimento lista os nomes das etapas,
    e os testes querem saber o que aparece como resultado da fila."""
    html = resposta.get_data(as_text=True)
    inicio = html.find('<form class="filtros"')
    if inicio >= 0:
        html = html[:inicio] + html[html.find("</form>", inicio) + len("</form>"):]
    return html


# ---------------------------------------------------------------- acesso


def test_sem_login_vai_para_a_tela_de_entrar(cliente, dados):
    resposta = cliente.get("/minha-fila")
    assert resposta.status_code == 302
    assert "/entrar" in resposta.headers["Location"]


def test_login_por_email_e_senha(db, cliente, dados):
    dados["ana"].definir_senha("senha-da-ana-123")
    db.session.commit()
    pagina = cliente.get("/entrar")
    assert 'name="email"' in texto(pagina) and "Consultora Ana" not in texto(pagina)  # não lista os nomes
    with cliente.session_transaction() as sessao:
        token = sessao["csrf"]
    resposta = cliente.post("/entrar?proximo=/fila", data={"email": "ANA@exemplo.test", "senha": "senha-da-ana-123", "csrf": token})
    assert resposta.headers["Location"] == "/fila"
    assert cliente.get("/minha-fila").status_code == 200


def test_login_limita_tentativas(db, cliente, dados):
    from app.web import auth

    auth._tentativas.clear()
    cliente.get("/entrar")
    with cliente.session_transaction() as sessao:
        token = sessao["csrf"]
    for _ in range(auth.TENTATIVAS_MAXIMAS):
        cliente.post("/entrar", data={"email": "ana@exemplo.test", "senha": "errada", "csrf": token})
    bloqueada = cliente.post("/entrar", data={"email": "ana@exemplo.test", "senha": "errada", "csrf": token})
    assert bloqueada.status_code == 429 and "Muitas tentativas" in texto(bloqueada)
    auth._tentativas.clear()


def test_usuario_inativo_perde_acesso(db, cliente, dados):
    entrar(cliente, dados["ana"])
    dados["ana"].ativo = False
    db.session.commit()
    assert cliente.get("/minha-fila").status_code == 302


def test_post_sem_token_e_recusado(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    resposta = cliente.post(f"/tarefas/{t.id}/status", data={"status": "concluida"})
    assert resposta.status_code == 400
    assert t.status == StatusTarefa.A_FAZER


def test_paginas_de_admin(cliente, dados):
    entrar(cliente, dados["ana"])
    for url in ("/cadastros/usuarios", "/cadastros/apelidos", "/cadastros/servicos", "/cadastros/catalogo", "/importacoes/nova"):
        assert cliente.get(url).status_code == 403, url
    entrar(cliente, dados["admin"])
    for url in ("/cadastros/usuarios", "/cadastros/apelidos", "/cadastros/servicos", "/cadastros/catalogo", "/importacoes/nova"):
        assert cliente.get(url).status_code == 200, url


@pytest.mark.parametrize(("proximo", "esperado"), [
    ("/fila?x=1", "/fila?x=1"), ("https://outro.site", "/p"), ("//outro.site", "/p"), ("/\\outro", "/p"), (None, "/p"),
])
def test_destino_seguro(proximo, esperado):
    assert destino_seguro(proximo, "/p") == esperado


# ---------------------------------------------------------------- filas


def test_minha_fila_mostra_so_as_minhas(db, cliente, dados):
    entrar(cliente, dados["ana"])
    pagina = texto(cliente.get("/minha-fila"))
    assert "Aluno Um" in pagina and "Aluno Dois" not in pagina

    # A estagiária recebe uma tarefa da Ana: sai da fila da Ana e entra na dela.
    tarefa(db, "902").responsavel_manual = dados["estagiaria"]
    db.session.commit()
    entrar(cliente, dados["estagiaria"])
    pagina = texto(cliente.get("/minha-fila"))
    assert "Ter uma cópia do visto/negativa" in pagina and "Cadastrar flight details" not in pagina


def test_fila_mostra_neg_e_destaca_atraso(cliente, dados):
    entrar(cliente, dados["ana"])
    pagina = texto(cliente.get("/minha-fila"))
    assert "NEG (justificativa do atraso)" in pagina
    assert "17/09 - aguardando visto" in pagina
    assert "Atrasada e sem NEG" in pagina  # a tarefa 902


def test_nova_observacao_direto_da_fila(db, cliente, dados):
    entrar(cliente, dados["ana"])
    pagina = texto(cliente.get("/minha-fila"))
    assert pagina.count("+ observação") == 2  # uma por tarefa da Ana
    t = tarefa(db, "901")
    resposta = cliente.post(f"/tarefas/{t.id}/anotacoes", data={"csrf": TOKEN, "texto": "29/09 - aluno enviou o passaporte",
                                                               "voltar": "/minha-fila?visao=lista"})
    assert resposta.headers["Location"].endswith("/minha-fila?visao=lista")  # volta para a fila
    pagina = texto(cliente.get("/minha-fila?visao=lista"))
    assert "29/09 - aluno enviou o passaporte" in pagina and "17/09 - aguardando visto" in pagina
    assert t.obs_egali == "17/09 - aguardando visto"  # a NEG da Egali não muda
    sem = texto(cliente.get("/minha-fila?atraso=sem_justificativa"))
    assert "Ter uma cópia do visto/negativa" in sem  # observação do sistema não conta como NEG


def test_filtro_de_atraso(cliente, dados):
    entrar(cliente, dados["admin"])
    sem = texto(cliente.get("/fila?atraso=sem_justificativa"))
    assert "Ter uma cópia do visto/negativa" in sem and "aguardando visto" not in sem
    com = texto(cliente.get("/fila?atraso=com_justificativa"))
    assert "aguardando visto" in com and "Ter uma cópia do visto/negativa" not in com
    no_prazo = texto(cliente.get("/fila?atraso=no_prazo"))
    assert "Aluno Dois" in no_prazo and "Aluno Um" not in no_prazo


def test_filtros_de_pessoa_trilha_e_busca(cliente, dados):
    entrar(cliente, dados["admin"])
    assert "Aluno Dois" not in texto(cliente.get(f"/fila?consultor={dados['ana'].id}"))
    sem_consultor = texto(cliente.get("/fila?consultor=nenhum"))
    assert "Aluno Três" in sem_consultor and "Aluno Um" not in sem_consultor
    eua = texto(cliente.get("/fila?trilha=EUA"))
    assert "Aluno Dois" in eua and "Aluno Um" not in eua
    busca = texto(cliente.get("/fila?busca=aluno+dois"))
    assert "Aluno Dois" in busca and "Aluno Um" not in busca


def test_abas_por_status(db, cliente, dados):
    tarefa(db, "903").status = StatusTarefa.AGUARDANDO_ALUNO
    db.session.commit()
    entrar(cliente, dados["admin"])
    aguardando = texto(cliente.get("/fila?status=aguardando_aluno"))
    assert "Aluno Dois" in aguardando and "Aluno Um" not in aguardando


def test_concluida_e_programa_cancelado_saem_da_fila(db, cliente, dados):
    tarefa(db, "901").status = StatusTarefa.CONCLUIDA
    db.session.commit()
    entrar(cliente, dados["ana"])
    assert "Cadastrar flight details" not in texto(cliente.get("/minha-fila"))


def test_paginacao_da_fila(db, cliente, dados):
    programa = tarefa(db, "901").programa
    etapa = tarefa(db, "901").etapa
    db.session.add_all([
        Tarefa(item_checklist_egali=str(5000 + i), programa=programa, etapa=etapa, prazo_egali=HOJE + timedelta(days=i))
        for i in range(150)
    ])
    db.session.commit()
    entrar(cliente, dados["ana"])
    primeira = cliente.get("/minha-fila")
    assert primeira.status_code == 200
    assert "página 1 de 2" in texto(primeira) and "Próxima" in texto(primeira)
    segunda = cliente.get("/minha-fila?pagina=2")
    assert segunda.status_code == 200 and "Anterior" in texto(segunda)


def test_por_consultor(cliente, dados):
    entrar(cliente, dados["admin"])
    pagina = texto(cliente.get("/consultores"))
    assert "Consultora Ana" in pagina and "Consultora Bia" in pagina and "Sem consultor" in pagina
    assert "% atrasadas" in pagina
    linha_ana = pagina[pagina.find("Consultora Ana"):pagina.find("</tr>", pagina.find("Consultora Ana"))]
    assert "100%" in linha_ana  # 2 abertas, 2 atrasadas
    rodape = pagina[pagina.find("<tfoot>"):]
    assert "50%" in rodape  # 4 abertas, 2 atrasadas
    assert "Estagiária Cida" not in pagina  # sem programas nem tarefas


def test_resumo_por_consultor_conta_atrasadas(dados):
    from app.consultas import resumo_por_consultor

    linhas = {l.usuario.nome if l.usuario else None: l for l in resumo_por_consultor(HOJE)}
    ana = linhas["Consultora Ana"]
    assert (ana.programas, ana.abertas, ana.atrasadas, ana.sem_justificativa) == (1, 2, 2, 1)
    assert linhas[None].abertas == 1


# ---------------------------------------------------------------- visualizações


def test_escolher_visualizacao_fica_guardada(db, cliente, dados):
    entrar(cliente, dados["ana"])
    assert dados["ana"].visao_fila == VisaoFila.LISTA
    pagina = texto(cliente.get("/minha-fila?visao=kanban"))
    assert 'class="kanban"' in pagina
    assert dados["ana"].visao_fila == VisaoFila.KANBAN
    assert 'class="kanban"' in texto(cliente.get("/minha-fila"))  # abre no último modo usado
    # Link "ver na lista" a partir do kanban/calendário não troca a preferência.
    cliente.get("/minha-fila?visao=lista&fixar=0")
    assert dados["ana"].visao_fila == VisaoFila.KANBAN
    cliente.get("/fila?visao=nao-existe")
    assert dados["ana"].visao_fila == VisaoFila.KANBAN


def test_kanban_colunas_por_status(db, cliente, dados):
    tarefa(db, "902").status = StatusTarefa.AGUARDANDO_ALUNO
    db.session.commit()
    entrar(cliente, dados["admin"])
    pagina = texto(cliente.get("/fila?visao=kanban"))
    colunas = pagina.split('class="kanban-coluna')
    assert len(colunas) == 5  # 3 status + "concluir"
    assert "Cadastrar flight details" in colunas[1] and "Ter uma cópia do visto/negativa" not in colunas[1]
    assert "Ter uma cópia do visto/negativa" in colunas[3]
    assert 'draggable="true"' in pagina


def test_arrastar_no_kanban_muda_o_status(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    resposta = cliente.post(f"/tarefas/{t.id}/status", data={"csrf": TOKEN, "status": "em_andamento"},
                            headers={"X-Requested-With": "fetch"})
    assert resposta.status_code == 200
    assert resposta.get_json() == {"ok": True, "mudou": True, "status": "em_andamento", "rotulo": "Em andamento"}
    assert t.status == StatusTarefa.EM_ANDAMENTO
    assert db.session.execute(db.select(HistoricoTarefa).filter_by(tarefa_id=t.id)).scalar_one().usuario_id == dados["ana"].id
    sem_token = cliente.post(f"/tarefas/{t.id}/status", data={"status": "concluida"}, headers={"X-Requested-With": "fetch"})
    assert sem_token.status_code == 400 and t.status == StatusTarefa.EM_ANDAMENTO


def test_quadro_um_cartao_por_aluno(cliente, dados):
    entrar(cliente, dados["admin"])
    pagina = texto(cliente.get("/fila?visao=quadro&organizar=data"))
    cartoes = pagina.split('<details class="cartao-aluno')[1:]
    assert len(cartoes) == 3
    assert "Aluno Um" in cartoes[0]  # tem a tarefa mais atrasada
    assert "Cadastrar flight details" in cartoes[0] and "Ter uma cópia do visto/negativa" in cartoes[0]
    assert "NEG" in cartoes[0]


def test_quadro_paginado_por_aluno(dados):
    from app.consultas import Filtros, Organizar, quadro_por_aluno

    primeira, total = quadro_por_aluno(Filtros(hoje=HOJE), pagina=1, por_pagina=2, organizar=Organizar.DATA)
    segunda, _ = quadro_por_aluno(Filtros(hoje=HOJE), pagina=2, por_pagina=2, organizar=Organizar.DATA)
    assert total == 3
    assert [c.programa.aluno.nome for c in primeira] == ["Aluno Um", "Aluno Dois"]
    assert [len(c.tarefas) for c in primeira] == [2, 1]
    assert [c.programa.aluno.nome for c in segunda] == ["Aluno Três"]


def test_calendario(cliente, dados):
    entrar(cliente, dados["admin"])
    daqui_10 = HOJE + timedelta(days=10)
    pagina = texto(cliente.get(f"/fila?visao=calendario&mes={daqui_10:%Y-%m}"))
    assert 'class="calendario"' in pagina
    assert "Aluno · Agendamento do aluno" in pagina  # primeiro nome do aluno · etapa
    anterior = texto(cliente.get(f"/fila?visao=calendario&mes={(HOJE.replace(day=1) - timedelta(days=40)):%Y-%m}"))
    assert "Agendamento do aluno" not in anterior
    assert "com data antes deste período" not in anterior  # nada aberto antes daquele mês
    futuro = texto(cliente.get(f"/fila?visao=calendario&mes={(HOJE.replace(day=1) + timedelta(days=100)):%Y-%m}"))
    assert "2 tarefa(s) abertas com data antes deste período" in futuro
    assert cliente.get("/fila?visao=calendario&mes=bobagem").status_code == 200


def test_filtro_por_intervalo_de_prazo(cliente, dados):
    entrar(cliente, dados["admin"])
    daqui_10 = HOJE + timedelta(days=10)
    pagina = texto(cliente.get(f"/fila?visao=lista&prazo_de={daqui_10.isoformat()}&prazo_ate={daqui_10.isoformat()}"))
    assert "Aluno Dois" in pagina and "Aluno Um" not in pagina and "Aluno Três" not in pagina


# ---------------------------------------------------------------- ações na tarefa


def test_mudar_status_pela_fila(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    resposta = cliente.post(f"/tarefas/{t.id}/status", data={"status": "em_andamento", "csrf": TOKEN, "voltar": "/minha-fila"})
    assert resposta.headers["Location"] == "/minha-fila"
    assert t.status == StatusTarefa.EM_ANDAMENTO
    historico = db.session.execute(db.select(HistoricoTarefa).filter_by(tarefa_id=t.id)).scalar_one()
    assert historico.usuario_id == dados["ana"].id and historico.valor_novo == "em_andamento"

    cliente.post(f"/tarefas/{t.id}/status", data={"status": "concluida", "csrf": TOKEN})
    assert t.status == StatusTarefa.CONCLUIDA and t.concluida_em is not None


def test_status_invalido(db, cliente, dados):
    entrar(cliente, dados["ana"])
    assert cliente.post(f"/tarefas/{tarefa(db, '901').id}/status", data={"status": "feito", "csrf": TOKEN}).status_code == 400


def test_mudar_responsavel_e_voltar_ao_consultor(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    cliente.post(f"/tarefas/{t.id}/responsavel", data={"responsavel": dados["estagiaria"].id, "csrf": TOKEN})
    assert t.responsavel is dados["estagiaria"]
    cliente.post(f"/tarefas/{t.id}/responsavel", data={"responsavel": "", "csrf": TOKEN})
    assert t.responsavel_manual is None and t.responsavel is dados["ana"]


def test_data_planejada_pela_pagina_da_tarefa(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    procedimento = t.prazo_egali
    novo = HOJE + timedelta(days=7)
    resposta = cliente.post(f"/tarefas/{t.id}/data-planejada", data={"data": novo.isoformat(), "csrf": TOKEN}, follow_redirects=True)
    assert t.data_planejada == novo and t.data_prevista == novo
    assert t.prazo_egali == procedimento and t.atrasada()  # atraso continua pela data da Egali
    assert "depois da data do procedimento" in texto(resposta)
    historico = db.session.execute(db.select(HistoricoTarefa).filter_by(tarefa_id=t.id, campo="data_planejada")).scalar_one()
    assert historico.usuario_id == dados["ana"].id

    pagina = texto(cliente.get(f"/tarefas/{t.id}"))
    assert "Data do procedimento (Egali)" in pagina and "Data planejada" in pagina

    cliente.post(f"/tarefas/{t.id}/data-planejada", data={"data": novo.isoformat(), "usar_egali": "1", "csrf": TOKEN})
    assert t.data_planejada is None
    # Escolher a própria data do procedimento também volta a "igual à do procedimento".
    cliente.post(f"/tarefas/{t.id}/data-planejada", data={"data": procedimento.isoformat(), "csrf": TOKEN})
    assert t.data_planejada is None


def test_arrastar_no_calendario_muda_a_data_planejada(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    antes = HOJE - timedelta(days=10)
    resposta = cliente.post(f"/tarefas/{t.id}/data-planejada", data={"data": antes.isoformat(), "csrf": TOKEN},
                            headers={"X-Requested-With": "fetch"})
    assert resposta.get_json() == {"ok": True, "mudou": True, "data_prevista": antes.isoformat(), "planejada": True, "apos_prazo": False}
    depois = HOJE + timedelta(days=3)
    assert cliente.post(f"/tarefas/{t.id}/data-planejada", data={"data": depois.isoformat(), "csrf": TOKEN},
                        headers={"X-Requested-With": "fetch"}).get_json()["apos_prazo"] is True
    invalida = cliente.post(f"/tarefas/{t.id}/data-planejada", data={"data": "ontem", "csrf": TOKEN},
                            headers={"X-Requested-With": "fetch"})
    assert invalida.status_code == 400 and t.data_planejada == depois
    sem_token = cliente.post(f"/tarefas/{t.id}/data-planejada", data={"data": antes.isoformat()},
                             headers={"X-Requested-With": "fetch"})
    assert sem_token.status_code == 400 and t.data_planejada == depois


def test_calendario_e_fila_usam_a_data_planejada(db, cliente, dados):
    t = tarefa(db, "901")  # procedimento: 5 dias atrás
    t.data_planejada = HOJE + timedelta(days=15)
    db.session.commit()
    entrar(cliente, dados["admin"])
    no_dia = texto(cliente.get(f"/fila?visao=lista&prazo_de={t.data_planejada.isoformat()}&prazo_ate={t.data_planejada.isoformat()}"))
    assert "Cadastrar flight details" in no_dia and "planejada · procedimento" in no_dia
    # Mas continua contando como atrasada (pela data da Egali).
    assert "aguardando visto" in texto(cliente.get("/fila?visao=lista&atraso=com_justificativa"))
    calendario = texto(cliente.get(f"/fila?visao=calendario&mes={t.data_planejada:%Y-%m}"))
    assert f'data-dia="{t.data_planejada.isoformat()}"' in calendario
    assert "✎ Aluno · Cadastrar flight details" in calendario


def test_anotacao(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    cliente.post(f"/tarefas/{t.id}/anotacoes", data={"texto": "Liguei, vai mandar amanhã.", "csrf": TOKEN})
    assert t.anotacoes[0].texto == "Liguei, vai mandar amanhã." and t.anotacoes[0].autor is dados["ana"]
    pagina = texto(cliente.get(f"/tarefas/{t.id}"))
    assert "Liguei, vai mandar amanhã." in pagina
    assert "Observação do sistema Egali (NEG)" in pagina
    assert "Como fazer" in pagina  # orientações do PPT


def test_paginas_de_detalhe(db, cliente, dados):
    entrar(cliente, dados["ana"])
    t = tarefa(db, "901")
    assert "Aluno Um" in texto(cliente.get(f"/programas/{t.programa_id}"))
    assert "Aluno Um" in texto(cliente.get("/busca?q=um"))
    assert cliente.get("/tarefas/99999").status_code == 404
    assert "O que não é NEG" in texto(cliente.get("/cadastros/ajuda-neg"))


# ---------------------------------------------------------------- importação pela tela


CSV = (
    "#;Id da Compra;NEG;ID Aluno;Aluno ;Procedimento ;Data ;Status;Serviço\r\n"
    f"905;100;;10;Aluno Um;SA - GERAL - Ter a cópia do passaporte do aluno;{br(HOJE)};Aguardando;Curso Premium\r\n"
)


def test_importar_checklist_pela_tela(db, cliente, dados):
    entrar(cliente, dados["admin"])
    resposta = cliente.post("/importacoes/nova", data={
        "csrf": TOKEN, "tipo": "checklist", "arquivo": (io.BytesIO(CSV.encode("cp1252")), "checklistServicoNew.csv"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 302
    importacao = db.session.execute(db.select(Importacao).order_by(Importacao.id.desc())).scalars().first()
    assert importacao.situacao == SituacaoImportacao.PREVIA
    assert importacao.arquivo_nome == "checklistServicoNew.csv"
    pagina = texto(cliente.get(resposta.headers["Location"]))
    assert "Isto é uma prévia" in pagina and "Tarefas novas" in pagina
    assert db.session.query(Tarefa).count() == 4  # nada gravado ainda

    cliente.post(f"/importacoes/{importacao.id}/confirmar", data={"csrf": TOKEN})
    assert importacao.situacao == SituacaoImportacao.CONFIRMADA
    assert db.session.query(Tarefa).filter_by(item_checklist_egali="905").count() == 1
    assert os.listdir(os.path.join(cliente.application.instance_path, "envios")) == []  # arquivo temporário apagado


def test_planilha_semanal_nao_e_mais_importada(db, cliente, dados):
    entrar(cliente, dados["admin"])
    pagina = texto(cliente.get("/importacoes/nova"))
    assert "Relatório de checklist do TM" in pagina and "planilha semanal" not in pagina.lower()
    resposta = cliente.post("/importacoes/nova", data={
        "csrf": TOKEN, "tipo": "base_alunos", "arquivo": (io.BytesIO(b"x"), "Carteira por consultor.xlsx"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 400 and "Escolha o tipo de arquivo" in texto(resposta)


def test_importacao_com_extensao_errada(db, cliente, dados):
    entrar(cliente, dados["admin"])
    resposta = cliente.post("/importacoes/nova", data={
        "csrf": TOKEN, "tipo": "checklist", "arquivo": (io.BytesIO(b"x"), "arquivo.xlsx"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 400
    assert "precisa ser" in texto(resposta)


def test_importacao_com_arquivo_invalido_mostra_o_erro(db, cliente, dados):
    entrar(cliente, dados["admin"])
    resposta = cliente.post("/importacoes/nova", data={
        "csrf": TOKEN, "tipo": "checklist", "arquivo": (io.BytesIO("a;b\r\n1;2\r\n".encode()), "outro.csv"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 400
    assert "não tem a(s) coluna(s)" in texto(resposta)


def test_encerrar_fora_do_periodo_pela_tela(db, cliente, dados):
    # Novo checklist só com o item 903, período a partir de hoje: 901 e 902 (prazos passados) ficam fora do período.
    csv = ("#;Id da Compra;ID Aluno;Procedimento;Data;Status;Serviço\r\n"
           f"903;200;20;SA - EUA - Agendamento do aluno;{br(HOJE + timedelta(days=10))};Aguardando;Curso Premium\r\n"
           f"904;300;30;SA - GERAL - Cadastrar flight details;{br(HOJE + timedelta(days=20))};Aguardando;Curso Premium\r\n")
    importacao = checklist.confirmar(checklist.criar_previa(
        ler_texto_csv(csv), periodo_inicio=HOJE, periodo_fim=HOJE + timedelta(days=60)))

    entrar(cliente, dados["ana"])
    pagina = texto(cliente.get(f"/importacoes/{importacao.id}"))
    assert "fora do período (2)" in pagina and "Encerrar as marcadas" not in pagina  # só admin encerra
    assert cliente.post(f"/importacoes/{importacao.id}/encerrar-fora-do-periodo",
                        data={"csrf": TOKEN, "tarefa": [tarefa(db, "901").id]}).status_code == 403

    entrar(cliente, dados["admin"])
    assert "Encerrar as marcadas" in texto(cliente.get(f"/importacoes/{importacao.id}"))
    cliente.post(f"/importacoes/{importacao.id}/encerrar-fora-do-periodo", data={"csrf": TOKEN, "tarefa": [tarefa(db, "901").id]})
    assert tarefa(db, "901").status == StatusTarefa.CONCLUIDA
    assert tarefa(db, "902").status == StatusTarefa.A_FAZER
    assert "fora do período (1)" in texto(cliente.get(f"/importacoes/{importacao.id}"))


def test_fora_do_periodo_so_marca_o_que_ficou_para_tras(db, cliente, dados):
    # Tarefa com prazo DEPOIS do fim do período: só não veio porque o filtro da exportação acabava antes.
    depois = Tarefa(item_checklist_egali="950", programa=tarefa(db, "901").programa, etapa=tarefa(db, "901").etapa,
                    prazo_egali=HOJE + timedelta(days=90))
    db.session.add(depois)
    db.session.commit()
    csv = ("#;Id da Compra;ID Aluno;Procedimento;Data;Status;Serviço\r\n"
           f"903;200;20;SA - EUA - Agendamento do aluno;{br(HOJE + timedelta(days=10))};Aguardando;Curso Premium\r\n")
    importacao = checklist.confirmar(checklist.criar_previa(
        ler_texto_csv(csv), periodo_inicio=HOJE, periodo_fim=HOJE + timedelta(days=60)))
    entrar(cliente, dados["admin"])
    pagina = cliente.get(f"/importacoes/{importacao.id}").get_data(as_text=True)
    assert f'value="{tarefa(db, "901").id}" checked' in pagina  # prazo antes do período: marcada
    assert f'value="{depois.id}" checked' not in pagina and f'value="{depois.id}"' in pagina  # depois do período: desmarcada
    assert "depois do período: deve continuar pendente" in pagina and "vêm desmarcadas" in pagina
    assert 'checked aria-label="Marcar todas"' not in pagina


# ---------------------------------------------------------------- cadastros


def test_cadastrar_e_editar_usuario(db, cliente, dados):
    entrar(cliente, dados["admin"])
    cliente.post("/cadastros/usuarios", data={"csrf": TOKEN, "nome": "Nova Pessoa", "email": "Nova@Exemplo.test", "papel": "consultor"})
    nova = db.session.execute(db.select(Usuario).filter_by(email="nova@exemplo.test")).scalar_one()
    resposta = cliente.post("/cadastros/usuarios", data={"csrf": TOKEN, "nome": "Outra", "email": "nova@exemplo.test", "papel": "consultor"})
    assert "Já existe" in texto(resposta)
    cliente.post(f"/cadastros/usuarios/{nova.id}", data={"csrf": TOKEN, "nome": "Nova Pessoa", "email": "nova@exemplo.test", "papel": "admin"})
    assert nova.papel == Papel.ADMIN and not nova.ativo  # caixa "ativo" desmarcada


def test_admin_nao_tira_o_proprio_acesso(db, cliente, dados):
    entrar(cliente, dados["admin"])
    cliente.post(f"/cadastros/usuarios/{dados['admin'].id}", data={
        "csrf": TOKEN, "nome": "Admin Teste", "email": "admin@exemplo.test", "papel": "consultor", "ativo": "1"})
    assert dados["admin"].papel == Papel.ADMIN


def test_excecao_de_nome_do_consultor(db, cliente, dados):
    entrar(cliente, dados["admin"])
    pagina = texto(cliente.get("/cadastros/apelidos"))
    assert "Nome Desconhecido" in pagina  # sugerido: não bate com ninguém
    cliente.post("/cadastros/apelidos", data={"csrf": TOKEN, "texto": "Nome Desconhecido", "usuario_id": dados["bia"].id})
    apelido = db.session.execute(db.select(ApelidoConsultor)).scalar_one()
    assert apelido.usuario is dados["bia"]
    cliente.post(f"/cadastros/apelidos/{apelido.id}/remover", data={"csrf": TOKEN})
    assert db.session.query(ApelidoConsultor).count() == 0


def test_classificar_servico(db, cliente, dados):
    entrar(cliente, dados["admin"])
    servico = db.session.execute(db.select(ServicoEgali).filter_by(nome="Seguro Viagem")).scalar_one()
    cliente.post("/cadastros/servicos", data={"csrf": TOKEN, f"categoria_{servico.id}": "ignorado"})
    assert servico.categoria == CategoriaServico.IGNORADO


def test_editar_etapa_e_trilha(db, cliente, dados):
    entrar(cliente, dados["admin"])
    etapa = tarefa(db, "901").etapa
    cliente.post(f"/cadastros/etapas/{etapa.id}", data={
        "csrf": TOKEN, "nome": "Cadastrar flight details", "ordem": 3, "ativa": "1", "o_que_e": "Texto novo",
    })
    assert etapa.o_que_e == "Texto novo" and etapa.importancia is None and etapa.ordem == 3
    trilha = etapa.trilha
    cliente.post("/cadastros/catalogo", data={"csrf": TOKEN, f"nome_{trilha.id}": "Geral (todos)"})
    assert trilha.nome == "Geral (todos)"
