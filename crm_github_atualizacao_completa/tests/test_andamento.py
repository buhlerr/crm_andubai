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
    assert a.total == 0 and a.porcentagem == 0
    assert not a.estimado


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
    assert VOO.split(" - ")[-1] in nomes(antes, Situacao.EM_ABERTO)
    voo = db.session.execute(db.select(Tarefa).filter_by(item_checklist_egali="901")).scalar_one()
    voo.status = StatusTarefa.CONCLUIDA
    db.session.commit()
    depois = andamento.calcular(programas["1"])
    assert depois.feitos == antes.feitos + 1
    assert depois.porcentagem > antes.porcentagem
    assert VOO.split(" - ")[-1] in nomes(depois, Situacao.FINALIZADO)


def test_pendente_fica_fora_do_percentual(programas):
    a = andamento.calcular(programas["1"])
    pendentes = [p for p in a.passos if p.situacao == Situacao.PENDENTE]
    assert pendentes  # continua visível para informar o que ainda não foi criado pela Egali
    assert a.total == len([p for p in a.passos if p.situacao != Situacao.PENDENTE])
    assert a.porcentagem == round(100 * a.feitos / a.total)


def test_nao_se_aplica_conta_como_feito(db, programas):
    antes = andamento.calcular(programas["1"])
    voo = db.session.execute(db.select(Tarefa).filter_by(item_checklist_egali="901")).scalar_one()
    voo.status = StatusTarefa.NAO_SE_APLICA
    db.session.commit()
    depois = andamento.calcular(programas["1"])
    assert depois.feitos == antes.feitos + 1
    assert VOO.split(" - ")[-1] in nomes(depois, Situacao.NAO_SE_APLICA)


def test_pagina_do_aluno_mostra_o_andamento(db, app, programas):
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = db.session.execute(db.select(Usuario)).scalar_one().id, "t"
    pagina = cliente.get(f"/programas/{programas['1'].id}").get_data(as_text=True)
    a = andamento.calcular(programas["1"])
    assert "Andamento até o embarque" in pagina and f"{a.porcentagem}%" in pagina
    assert f"{a.feitos} de {a.total} procedimentos" in pagina
    assert "Ainda não criado pela Egali" in pagina and "Estimativa" in pagina


# ---------------------------------------------------------------- andamento do processo de visto
CARTA = "SA - VISTOS - Ter a primeira versão da carta de intenções/GS form e formulário de visto preenchido"
ENTREGA = "SA - VISTOS - Entrega da 1a documentação e envio de chamado com pendências de documentação/Solicitar LOA (CAD)"
DOC_OK = "SA - VISTOS - Documentação OK ? Envio para embaixada/consulado"


def _visto(db, linhas):
    """Programa "2" (Estudante - Canadá) com as tarefas de visto informadas: (número, procedimento, neg)."""
    checklist.confirmar(checklist.criar_previa([
        {"linha": i + 2, "valores": {**item(i + 2, numero, "201", "20", procedimento)["valores"], "neg": neg}}
        for i, (numero, procedimento, neg) in enumerate(linhas)
    ]))
    programa = db.session.execute(db.select(Programa).filter_by(programa_id_egali="2")).scalar_one()
    db.session.refresh(programa)
    return [l for l in andamento.andamentos_de_visto([programa]) if l.trilha.codigo == "VISTOS"][0]


def test_visto_termina_no_documentacao_ok(db, programas):
    a = _visto(db, [("910", ENTREGA, "17/09 - aguardando passaporte")])
    assert "Documentação OK" in a.passos[-1].etapa.nome  # biometria, status e cópia do visto ficam fora
    assert not any("biometria" in p.etapa.nome for p in a.passos)
    assert a.atual.etapa.nome in ENTREGA and a.neg == "17/09 - aguardando passaporte"
    assert 0 < a.porcentagem < 100 and not a.concluido


def test_visto_100_quando_documentacao_ok_finalizado(db, programas):
    a = _visto(db, [("911", DOC_OK, "")])
    tarefa = a.passos[-1].tarefa
    tarefa.status = StatusTarefa.CONCLUIDA
    db.session.commit()
    a = andamento.calcular_visto(a.programa, a.trilha)
    assert a.concluido and a.porcentagem == 100


def test_visto_sem_documentacao_ok_nunca_chega_a_100(db, programas):
    a = _visto(db, [("912", DOC_OK, "Documentos com tradução")])
    assert a.porcentagem < 100 and a.neg == "Documentos com tradução"


@pytest.mark.parametrize("visto", ["Estudante - EUA", "Turista - EUA", "eTA - Canadá", "Turista - EUA,eTA - Canadá"])
def test_vistos_eua_e_eta_canada_ficam_fora(db, programas, visto):
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "5", "aluno_id": "50", "aluno_name": "Aluno Fora", "compra_id": "500",
                                 "consultor": "Consultora Ana", "visto normalizado": visto}},
    ]))
    novo = db.session.execute(db.select(Programa).filter_by(programa_id_egali="5")).scalar_one()
    assert andamento.andamentos_de_visto([novo]) == []


def test_eta_junto_com_visto_de_estudante_entra(db, programas):
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": 2, "valores": {"programa_id": "6", "aluno_id": "60", "aluno_name": "Aluno Misto", "compra_id": "600",
                                 "consultor": "Consultora Ana", "visto normalizado": "Turista - EUA,Estudante - Canadá"}},
    ]))
    novo = db.session.execute(db.select(Programa).filter_by(programa_id_egali="6")).scalar_one()
    [a] = andamento.andamentos_de_visto([novo])
    assert a.trilha.codigo == "VISTOS" and a.porcentagem == 0


def test_tela_andamento_dos_vistos(app, db, programas):
    cliente = app.test_client()
    ana = db.session.execute(db.select(Usuario)).scalars().first()
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"] = ana.id
    resposta = cliente.get("/andamento-vistos")
    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "Aluno Quebec" in html and "Aluno Toronto" in html and "Consultora Ana" in html
    assert "NEG do procedimento" in html and "Andamento dos vistos" in html and "Embarque" in html


def test_visto_com_passos_depois_do_documentacao_ok_ja_esta_em_100(db, programas):
    # Caso real: o sistema só conhece "Verificar status" e "Confirmar envio do passaporte" (depois do Documentação OK).
    # Antes, o corte no Documentação OK vinha antes da estimativa, e o aluno aparecia com 0%.
    a = _visto(db, [("920", "SA - CAN - Verificar status da aplicação do visto", ""),
                    ("921", "SA - CAN - Confirmar envio do passaporte após aprovação", "")])
    for passo in a.programa.tarefas:
        passo.status = StatusTarefa.CONCLUIDA
    db.session.commit()
    a = andamento.calcular_visto(a.programa, a.trilha)
    assert a.concluido and a.porcentagem == 100
    assert "Documentação OK" in a.passos[-1].etapa.nome and a.passos[-1].situacao == Situacao.FINALIZADO_ESTIMADO


def test_filtros_de_embarque_e_etapa_na_tela(app, db, programas):
    from app.models import EtapaModelo

    programas["1"].data_embarque = HOJE + timedelta(days=40)
    programas["2"].data_embarque = HOJE - timedelta(days=10)  # já embarcou
    db.session.commit()
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"] = db.session.execute(db.select(Usuario)).scalars().first().id

    def alunos(**args):
        html = cliente.get("/andamento-vistos", query_string=args).get_data(as_text=True)
        return {n for n in ("Aluno Quebec", "Aluno Toronto") if n in html}

    assert alunos() == {"Aluno Quebec"}  # primeira abertura: embarque de hoje em diante
    assert alunos(embarque_de="", sem_data="1") == {"Aluno Quebec", "Aluno Toronto"}
    assert alunos(embarque_de="", embarque_ate=(HOJE - timedelta(days=1)).isoformat()) == {"Aluno Toronto"}

    # Os dois do cenário têm "cópia do visto" em aberto (depois do Documentação OK): processo concluído.
    assert alunos(embarque_de="", etapa="concluido") == {"Aluno Quebec", "Aluno Toronto"}

    # Alunos no começo do processo: o Quebec novo começa pelo CAQ; o Canadá estudante, pela carta de intenções.
    base_alunos.confirmar(base_alunos.criar_previa([
        {"linha": i + 2, "valores": {"programa_id": p, "aluno_id": a, "aluno_name": n, "compra_id": c,
                                     "consultor": "Consultora Ana", "visto normalizado": v}}
        for i, (p, a, n, c, v) in enumerate([
            ("1", "10", "Aluno Quebec", "100, 101", "Canadá/Quebec - Canadá"),
            ("2", "20", "Aluno Toronto", "200, 201", "Estudante - Canadá"),
            ("7", "70", "Aluna Quebec Nova", "700", "Canadá/Quebec - Canadá"),
            ("8", "80", "Aluna Vancouver Nova", "800", "Estudante - Canadá"),
        ])]))

    def novos(**args):
        html = cliente.get("/andamento-vistos", query_string={"embarque_de": "", "sem_data": "1", **args}).get_data(as_text=True)
        return {n for n in ("Aluna Quebec Nova", "Aluna Vancouver Nova", "Aluno Quebec", "Aluno Toronto") if n in html}

    carta = db.session.execute(db.select(EtapaModelo).filter_by(texto_egali=CARTA)).scalar_one()
    caq = db.session.execute(db.select(EtapaModelo).where(EtapaModelo.nome.contains("CAQ"))).scalar_one()
    html = cliente.get("/andamento-vistos", query_string={"embarque_de": ""}).get_data(as_text=True)
    assert "Etapa do processo de visto" in html and "Concluído (Documentação OK finalizada)" in html
    assert novos(etapa=str(caq.id)) == {"Aluna Quebec Nova"}
    assert novos(etapa=str(carta.id)) == {"Aluna Vancouver Nova"}
    # Sem marcar "Incluir sem data de embarque", quem não tem data fica de fora.
    assert "Aluna Quebec Nova" not in cliente.get("/andamento-vistos", query_string={"embarque_de": ""}).get_data(as_text=True)
