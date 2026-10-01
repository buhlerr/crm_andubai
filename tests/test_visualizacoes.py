"""Quadro por embarque, tipo de visto, "Organizar por", Concluídas e Para lançar na Egali."""

from datetime import date, timedelta

import pytest

from app import acoes_tarefa, consultas, vistos
from app.catalogo_inicial import carregar_catalogo
from app.consultas import Filtros, Organizar
from app.importacao import base_alunos, checklist
from app.models import Papel, Programa, StatusTarefa, Tarefa, Usuario

HOJE = date.today()
TOKEN = "t"


def br(d):
    return d.strftime("%d/%m/%Y")


@pytest.fixture
def dados(db):
    carregar_catalogo()
    ana = Usuario(nome="Consultora Ana", email="ana@exemplo.test", papel=Papel.ADMIN)
    bia = Usuario(nome="Consultora Bia", email="bia@exemplo.test")
    db.session.add_all([ana, bia])
    db.session.commit()

    def linha(n, pid, aid, nome, compra, consultor, visto, embarque):
        return {"linha": n, "valores": {"programa_id": pid, "aluno_id": aid, "aluno_name": nome, "compra_id": compra,
                                        "consultor": consultor, "visto normalizado": visto,
                                        "programa_data_embarque": br(embarque)}}

    base_alunos.confirmar(base_alunos.criar_previa([
        linha(2, "1", "10", "Aluno Longe", "100", "Consultora Ana", "Turista - EUA,eTA - Canadá", HOJE + timedelta(days=200)),
        linha(3, "2", "20", "Aluno Perto", "200", "Consultora Bia", "Estudante - Canadá", HOJE + timedelta(days=20)),
        linha(4, "3", "30", "Aluno Quebec", "300", "Consultora Ana", "Canadá/Quebec - Canadá", HOJE + timedelta(days=90)),
    ]))

    def item(n, numero, compra, aluno, proc, prazo):
        return {"linha": n, "valores": {"#": numero, "id da compra": compra, "id aluno": aluno, "procedimento": proc,
                                        "data": br(prazo), "status": "Aguardando", "serviço": "Curso Premium"}}

    checklist.confirmar(checklist.criar_previa([
        item(2, "901", "100", "10", "SA - GERAL - Cadastrar flight details", HOJE - timedelta(days=5)),
        item(3, "902", "200", "20", "SA - GERAL - Ter a cópia do passaporte do aluno", HOJE + timedelta(days=3)),
        item(4, "903", "300", "30", "SA - GERAL - Cadastrar flight details", HOJE + timedelta(days=30)),
    ], periodo_completo=True))
    return {"ana": ana, "bia": bia}


def tarefa(db, numero) -> Tarefa:
    return db.session.execute(db.select(Tarefa).filter_by(item_checklist_egali=numero)).scalar_one()


def entrar(cliente, usuario):
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = usuario.id, TOKEN


def test_rotulo_do_visto():
    assert vistos.rotulo("Turista - EUA") == "Visto - EUA - Turista"
    assert vistos.rotulo("eTA - Canadá") == "Visto - Canadá - eTA"
    assert vistos.rotulo("Canadá/Quebec - Canadá") == "Visto - Canadá - Quebec"
    assert vistos.rotulo("ESTA U.S - EUA") == "Visto - EUA - ESTA"
    assert vistos.tokens("Sem visto informado") == [] and vistos.tokens(None) == []


def test_quadro_vem_por_embarque_e_mostra_visto(db, dados, app):
    cartoes, total = consultas.quadro_por_aluno(Filtros(hoje=HOJE))
    assert [c.programa.aluno.nome for c in cartoes] == ["Aluno Perto", "Aluno Quebec", "Aluno Longe"]
    assert cartoes[0].grupo.startswith("Embarque em ")
    assert cartoes[2].atrasadas == 1 and cartoes[0].atrasadas == 0
    cliente = app.test_client()
    entrar(cliente, dados["ana"])
    pagina = cliente.get("/fila?visao=quadro").get_data(as_text=True)
    assert pagina.count('<details class="cartao-aluno') == 3
    assert "Visto - EUA - Turista" in pagina and "Visto - Canadá - eTA" in pagina and "1 atrasada(s)" in pagina


def test_quem_ja_embarcou_vai_para_o_fim(db, dados):
    longe = db.session.execute(db.select(Programa).filter_by(programa_id_egali="1")).scalar_one()
    longe.data_embarque = HOJE - timedelta(days=30)
    db.session.commit()
    cartoes, _ = consultas.quadro_por_aluno(Filtros(hoje=HOJE))
    assert [c.programa.aluno.nome for c in cartoes] == ["Aluno Perto", "Aluno Quebec", "Aluno Longe"]
    assert cartoes[-1].grupo == "Embarque já passou"
    lista, _ = consultas.tarefas(Filtros(hoje=HOJE), organizar=Organizar.EMBARQUE)
    assert lista[-1].item_checklist_egali == "901"


def test_filtro_por_visto(db, dados):
    so_eta = consultas.tarefas(Filtros(visto="eTA - Canadá", hoje=HOJE))[0]
    assert [t.item_checklist_egali for t in so_eta] == ["901"]
    assert consultas.contar(Filtros(visto="Estudante - Canadá", hoje=HOJE)) == 1
    assert ("Canadá/Quebec - Canadá", "Visto - Canadá - Quebec") in consultas.vistos_na_fila()


def test_organizar_lista_agrupa_e_fica_guardado(db, dados, app):
    lista, _ = consultas.tarefas(Filtros(hoje=HOJE), organizar=Organizar.RESPONSAVEL)
    grupos = consultas.agrupar(lista, Organizar.RESPONSAVEL)
    assert [g for g, _ in grupos] == ["Consultora Ana", "Consultora Bia"]
    assert [len(ts) for _, ts in grupos] == [2, 1]

    cliente = app.test_client()
    entrar(cliente, dados["ana"])
    pagina = cliente.get("/fila?visao=lista&organizar=embarque").get_data(as_text=True)
    assert 'class="grupo-linha"' in pagina and "Embarque em " in pagina
    assert db.session.get(Usuario, dados["ana"].id).organizar_lista == "embarque"
    assert db.session.get(Usuario, dados["ana"].id).organizar_quadro == "embarque"  # o do quadro não mudou
    cliente.get("/fila?visao=quadro&organizar=status")  # "status" não vale no quadro: ignora
    assert db.session.get(Usuario, dados["ana"].id).organizar_quadro == "embarque"


def test_concluidas_mostra_origem(db, dados, app):
    acoes_tarefa.mudar_status(tarefa(db, "902"), StatusTarefa.CONCLUIDA, dados["bia"])
    # 903 some do próximo checklist: encerrada pela Egali.
    csv = [{"linha": 2, "valores": {"#": "901", "id da compra": "100", "id aluno": "10",
                                    "procedimento": "SA - GERAL - Cadastrar flight details",
                                    "data": br(HOJE - timedelta(days=5)), "status": "Aguardando", "serviço": "Curso Premium"}},
           {"linha": 3, "valores": {"#": "902", "id da compra": "200", "id aluno": "20",
                                    "procedimento": "SA - GERAL - Ter a cópia do passaporte do aluno",
                                    "data": br(HOJE + timedelta(days=3)), "status": "Aguardando", "serviço": "Curso Premium"}}]
    checklist.confirmar(checklist.criar_previa(csv, periodo_completo=True))
    linhas, total = consultas.concluidas(Filtros(hoje=HOJE))
    origem = {l.tarefa.item_checklist_egali: (l.origem, l.quem) for l in linhas}
    assert total == 2
    assert origem["902"] == ("Neste sistema", "Consultora Bia")
    assert origem["903"] == ("Saiu do checklist da Egali", None)
    assert next(l for l in linhas if l.tarefa.item_checklist_egali == "902").dias_depois_do_prazo == 0

    cliente = app.test_client()
    entrar(cliente, dados["ana"])
    pagina = cliente.get("/concluidas").get_data(as_text=True)
    assert "Neste sistema" in pagina and "Saiu do checklist da Egali" in pagina and "no prazo" in pagina


def test_para_lancar_ate_a_egali_confirmar(db, dados, app):
    t = tarefa(db, "902")  # da Bia
    acoes_tarefa.mudar_status(t, StatusTarefa.CONCLUIDA, dados["bia"])
    obs = acoes_tarefa.anotar(tarefa(db, "901"), "aluno enviou o passaporte", dados["ana"])
    assert consultas.tarefas_para_lancar(dados["bia"].id) == [t]
    assert consultas.tarefas_para_lancar(dados["ana"].id) == []  # não é dela
    assert consultas.anotacoes_para_lancar(dados["ana"].id) == [obs]
    assert consultas.contar_para_lancar(dados["bia"].id) == 1

    cliente = app.test_client()
    entrar(cliente, dados["bia"])
    assert "Lancei na Egali" in cliente.get("/para-lancar").get_data(as_text=True)
    cliente.post(f"/tarefas/{t.id}/lancada-na-egali", data={"csrf": TOKEN})
    assert t.lancada_egali_em is not None and consultas.tarefas_para_lancar(dados["bia"].id) == []

    # A importação seguinte AINDA traz o item: aparece em "conferir".
    csv = [{"linha": 2, "valores": {"#": "902", "id da compra": "200", "id aluno": "20",
                                    "procedimento": "SA - GERAL - Ter a cópia do passaporte do aluno",
                                    "data": br(HOJE + timedelta(days=3)), "status": "Aguardando", "serviço": "Curso Premium"}}]
    checklist.confirmar(checklist.criar_previa(csv, periodo_inicio=HOJE + timedelta(days=1), periodo_fim=HOJE + timedelta(days=10)))
    assert consultas.lancadas_mas_abertas(dados["bia"].id) == [t]
    # Quando some do checklist, a Egali confirmou: sai de tudo.
    so_901 = [{"linha": 2, "valores": {"#": "901", "id da compra": "100", "id aluno": "10",
                                       "procedimento": "SA - GERAL - Cadastrar flight details",
                                       "data": br(HOJE - timedelta(days=5)), "status": "Aguardando", "serviço": "Curso Premium"}}]
    checklist.confirmar(checklist.criar_previa(so_901, periodo_completo=True))
    assert consultas.lancadas_mas_abertas() == [] and consultas.tarefas_para_lancar() == []

    entrar(cliente, dados["ana"])
    cliente.post(f"/tarefas/anotacoes/{obs.id}/lancada-na-egali", data={"csrf": TOKEN, "nao_precisa": "1"})
    assert obs.nao_precisa_lancar and consultas.anotacoes_para_lancar() == []


def test_reabrir_desfaz_o_lancado(db, dados):
    t = tarefa(db, "902")
    acoes_tarefa.mudar_status(t, StatusTarefa.CONCLUIDA, dados["bia"])
    acoes_tarefa.marcar_lancada(t, dados["bia"])
    acoes_tarefa.mudar_status(t, StatusTarefa.A_FAZER, dados["bia"])
    assert t.lancada_egali_em is None
    assert not acoes_tarefa.marcar_lancada(t, dados["bia"])  # aberta: não marca
