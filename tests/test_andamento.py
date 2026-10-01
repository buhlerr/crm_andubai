from datetime import date, timedelta

import pytest

from app import andamento
from app.andamento import Situacao
from app.catalogo_inicial import carregar_catalogo
from app.importacao import base_alunos, checklist
from app.models import Papel, Programa, StatusTarefa, Tarefa, Usuario

HOJE = date.today()
VOO = "SA - GERAL - Cadastrar flight details"
PRE_EMBARQUE = "SA - GERAL - Realizar contato de relacionamento pré - embarque"


def item(n, numero, compra, aluno, procedimento, servico="Curso Premium"):
    return {"linha": n, "valores": {"#": numero, "id da compra": compra, "id aluno": aluno, "procedimento": procedimento,
                                    "data": (HOJE + timedelta(days=5)).strftime("%d/%m/%Y"), "status": "Aguardando",
                                    "serviço": servico}}


@pytest.fixture
def programas(db):
    carregar_catalogo()
    db.session.add(Usuario(nome="Consultora Ana", email="ana@exemplo.test", papel=Papel.ADMIN))
    db.session.commit()
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "1", "aluno_id": "10", "aluno_name": "Aluno Quebec", "compra_id": "100, 101",
                                 "consultor": "Consultora Ana", "visto normalizado": "Canadá/Quebec - Canadá"}},
        {"linha": 3, "valores": {"programa_id": "2", "aluno_id": "20", "aluno_name": "Aluno Toronto", "compra_id": "200, 201",
                                 "consultor": "Consultora Ana", "visto normalizado": "Estudante - Canadá"}},
    ]))
    visto = "SA - VISTOS - Ter uma cópia do visto/negativa"
    checklist.confirmar(checklist.criar_previa([
        item(2, "901", "100", "10", VOO), item(3, "902", "101", "10", visto),
        item(4, "903", "200", "20", VOO), item(5, "904", "201", "20", visto),
    ], periodo_completo=True))
    return {p.programa_id_egali: p for p in db.session.execute(db.select(Programa)).scalars()}


def nomes(a, situacao=None):
    return [p.etapa.nome for p in a.passos if situacao is None or p.situacao == situacao]


def test_geral_termina_no_pre_embarque_e_estima_o_que_ja_passou(programas):
    a = andamento.calcular(programas["1"])
    geral = [p for p in a.passos if p.etapa.trilha.codigo == "GERAL"]
    assert "pré - embarque" in geral[-1].etapa.nome  # último procedimento antes do embarque
    assert not any("pós embarque" in n for n in nomes(a))  # pós-embarque fora
    i = next(i for i, p in enumerate(geral) if p.situacao == Situacao.EM_ABERTO)
    assert all(p.situacao == Situacao.FINALIZADO_ESTIMADO for p in geral[:i])  # antes do primeiro em aberto: já passou
    assert all(p.situacao == Situacao.PENDENTE for p in geral[i + 1:])  # depois: ainda não criado pela Egali
    assert a.estimado and 0 < a.porcentagem < 100
    assert a.feitos == sum(p.feito for p in a.passos)


def test_so_entram_as_trilhas_do_aluno(programas):
    trilhas = {p.etapa.trilha.codigo for p in andamento.calcular(programas["1"]).passos}
    assert trilhas == {"GERAL", "VISTOS"}  # sem EUA, Dubai, VIP nem Primeiro contato


def test_caq_so_para_visto_quebec(programas):
    assert any("CAQ" in n for n in nomes(andamento.calcular(programas["1"])))
    assert not any("CAQ" in n for n in nomes(andamento.calcular(programas["2"])))


def test_quebec_sem_tarefa_de_visto_ainda_mostra_o_caq(db, programas):
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "1", "aluno_id": "10", "aluno_name": "Aluno Quebec", "compra_id": "100, 101",
                                 "consultor": "Consultora Ana", "visto normalizado": "Canadá/Quebec - Canadá"}},
        {"linha": 3, "valores": {"programa_id": "2", "aluno_id": "20", "aluno_name": "Aluno Toronto", "compra_id": "200, 201",
                                 "consultor": "Consultora Ana", "visto normalizado": "Estudante - Canadá"}},
        {"linha": 4, "valores": {"programa_id": "3", "aluno_id": "30", "aluno_name": "Aluno Novo Quebec", "compra_id": "300",
                                 "consultor": "Consultora Ana", "visto normalizado": "Canadá/Quebec - Canadá"}},
    ]))
    novo = db.session.execute(db.select(Programa).filter_by(programa_id_egali="3")).scalar_one()
    a = andamento.calcular(novo)
    assert any("CAQ" in n for n in nomes(a, Situacao.PENDENTE))
    assert a.porcentagem == 0


def test_quem_ja_embarcou_sem_nada_aberto_fica_completo(db, programas):
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "1", "aluno_id": "10", "aluno_name": "Aluno Quebec", "compra_id": "100, 101",
                                 "consultor": "Consultora Ana", "visto normalizado": "Canadá/Quebec - Canadá"}},
        {"linha": 3, "valores": {"programa_id": "2", "aluno_id": "20", "aluno_name": "Aluno Toronto", "compra_id": "200, 201",
                                 "consultor": "Consultora Ana", "visto normalizado": "Estudante - Canadá"}},
        {"linha": 4, "valores": {"programa_id": "4", "aluno_id": "40", "aluno_name": "Aluno Embarcado", "compra_id": "400",
                                 "consultor": "Consultora Ana", "programa_data_embarque": (HOJE - timedelta(days=10)).strftime("%d/%m/%Y")}},
    ]))
    embarcado = db.session.execute(db.select(Programa).filter_by(programa_id_egali="4")).scalar_one()
    a = andamento.calcular(embarcado)
    assert a.total > 0 and a.porcentagem == 100
    # Quem ainda não embarcou e não tem nada no sistema fica em 0% (a Egali ainda não criou os procedimentos).
    assert andamento.calcular(embarcado, hoje=HOJE - timedelta(days=30)).porcentagem == 0


def test_canada_leap_so_para_quem_comprou_e_nivelamento_so_quando_criado(db, programas):
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "1", "aluno_id": "10", "aluno_name": "Aluno Quebec", "compra_id": "100, 101",
                                 "consultor": "Consultora Ana", "visto normalizado": "Canadá/Quebec - Canadá", "pt_prog": 90.0,
                                 "servico_name": "Canada Leap,Seguro Viagem"}},
        {"linha": 3, "valores": {"programa_id": "2", "aluno_id": "20", "aluno_name": "Aluno Toronto", "compra_id": "200, 201",
                                 "consultor": "Consultora Ana", "visto normalizado": "Estudante - Canadá", "pt_prog": 90.0,
                                 "servico_name": "Curso Premium"}},
    ]))
    checklist.confirmar(checklist.criar_previa([
        item(2, "901", "100", "10", VOO), item(3, "902", "101", "10", "SA - VISTOS - Ter uma cópia do visto/negativa"),
        item(4, "903", "200", "20", VOO), item(5, "904", "201", "20", "SA - VISTOS - Ter uma cópia do visto/negativa"),
        item(6, "905", "100", "10", "SA - GERAL - Primeiro contato de relacionamento com aluno"),
        item(7, "906", "200", "20", "SA - GERAL - Primeiro contato de relacionamento com aluno"),
    ], periodo_completo=True))
    com_leap, sem_leap = andamento.calcular(programas["1"]), andamento.calcular(programas["2"])
    assert any("Canadá Leap" in n for n in nomes(com_leap)) and not any("Canadá Leap" in n for n in nomes(sem_leap))
    assert not any("nivelamento" in n for n in nomes(com_leap) + nomes(sem_leap))  # nenhum dos dois tem a tarefa

    checklist.confirmar(checklist.criar_previa([
        item(2, "901", "100", "10", VOO), item(3, "902", "101", "10", "SA - VISTOS - Ter uma cópia do visto/negativa"),
        item(4, "903", "200", "20", VOO), item(5, "904", "201", "20", "SA - VISTOS - Ter uma cópia do visto/negativa"),
        item(6, "905", "100", "10", "SA - GERAL - Primeiro contato de relacionamento com aluno"),
        item(7, "906", "200", "20", "SA - GERAL - Primeiro contato de relacionamento com aluno"),
        item(8, "907", "100", "10", "SA - GERAL - Ter confirmação de realização do teste de nivelamento (requisito para embarque)"),
    ], periodo_completo=True))
    assert any("nivelamento" in n for n in nomes(andamento.calcular(programas["1"]), Situacao.EM_ABERTO))


def test_concluir_aumenta_o_andamento(db, programas):
    antes = andamento.calcular(programas["1"])
    voo = db.session.execute(db.select(Tarefa).filter_by(item_checklist_egali="901")).scalar_one()
    voo.status = StatusTarefa.CONCLUIDA
    db.session.commit()
    depois = andamento.calcular(programas["1"])
    assert depois.feitos == antes.feitos + 1
    assert VOO.split(" - ")[-1] in nomes(depois, Situacao.FINALIZADO)


def test_pagina_do_aluno_mostra_o_andamento(db, app, programas):
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = db.session.execute(db.select(Usuario)).scalar_one().id, "t"
    pagina = cliente.get(f"/programas/{programas['1'].id}").get_data(as_text=True)
    a = andamento.calcular(programas["1"])
    assert "Andamento até o embarque" in pagina and f"{a.porcentagem}%" in pagina
    assert f"{a.feitos} de {a.total} procedimentos" in pagina
    assert "Ainda não criado pela Egali" in pagina and "Estimativa" in pagina
