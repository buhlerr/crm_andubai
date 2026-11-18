from datetime import date, timedelta

import pytest

from app import consultas, publico_teen
from app.catalogo_inicial import carregar_catalogo
from app.consultas import FiltroPublico, Filtros
from app.importacao import base_alunos, checklist
from app.models import Aluno, ConsultorTeen, Papel, ServicoEgali, Usuario
from app.texto import normalizar_texto

HOJE = date.today()


def linha_base(n, programa_id, aluno_id, nome, compras, consultor="Consultora Ana", servicos=None, tags=None):
    return {"linha": n, "valores": {"programa_id": programa_id, "aluno_id": aluno_id, "aluno_name": nome, "compra_id": compras,
                                    "consultor": consultor, "servico_name": servicos, "tags": tags}}


def item(n, numero, compra, aluno, servico="Curso Premium", tags=""):
    return {"linha": n, "valores": {"#": numero, "id da compra": compra, "id aluno": aluno,
                                    "procedimento": "SA - GERAL - Cadastrar flight details",
                                    "data": (HOJE + timedelta(days=5)).strftime("%d/%m/%Y"), "status": "Aguardando",
                                    "serviço": servico, "tags": tags}}


def aluno(db, aluno_id) -> Aluno:
    return db.session.execute(db.select(Aluno).filter_by(aluno_id_egali=aluno_id)).scalar_one()


@pytest.fixture
def cenario(db):
    carregar_catalogo()
    db.session.add(Usuario(nome="Consultora Ana", email="ana@exemplo.test", papel=Papel.ADMIN))
    db.session.commit()
    base_alunos.confirmar(base_alunos.criar_previa([
        linha_base(2, "1", "10", "Aluno Suporte", "100", servicos="Seguro Viagem,Curso Premium,Visto - Canadá - eTA"),
        linha_base(3, "2", "20", "Aluno Summer", "200", servicos="Summer Schools,Transfer (chegada e saída)"),
        linha_base(4, "3", "30", "Aluno Tag", "300", servicos="Curso Premium", tags="Nunca avaliou atendimento,summer"),
        linha_base(5, "4", "40", "Aluno Consultor Teen", "400", consultor="Pessoa Da Equipe Teen", servicos="Curso Premium"),
    ]))


def test_servicos_teen_padrao_vem_marcados(db):
    carregar_catalogo()
    teen = {s.nome for s in db.session.execute(db.select(ServicoEgali).filter_by(teen=True)).scalars()}
    assert teen == {"Summer Schools", "Winter Schools", "Viagem Cultural", "Vancouver Experience"}


def test_marca_por_servico_e_por_tag(db, cenario):
    assert not aluno(db, "10").teen
    assert aluno(db, "20").teen and aluno(db, "20").teen_motivo == "Summer Schools"
    assert aluno(db, "30").teen and aluno(db, "30").teen_motivo == "tag summer"
    assert not aluno(db, "40").teen  # consultor ainda não está na lista da equipe teen


def test_marca_por_consultor_da_equipe_teen(db, cenario):
    db.session.add(ConsultorTeen(nome="Pessoa da Equipe Teen", nome_normalizado=normalizar_texto("Pessoa da Equipe Teen")))
    publico_teen.recalcular()
    assert aluno(db, "40").teen and "consultor teen" in aluno(db, "40").teen_motivo


def test_marca_pelo_checklist_servico_e_tag(db, cenario):
    checklist.confirmar(checklist.criar_previa([item(2, "901", "100", "10")], periodo_completo=True))
    assert not aluno(db, "10").teen
    checklist.confirmar(checklist.criar_previa([item(2, "901", "100", "10", tags="summer")], periodo_completo=True))
    assert aluno(db, "10").teen and aluno(db, "10").teen_motivo == "tag summer"


def test_compra_teen_nova_no_checklist_marca_o_aluno(db, cenario):
    # Sem a planilha, a compra nova entra no programa do aluno, e o serviço teen marca o aluno inteiro.
    checklist.confirmar(checklist.criar_previa([
        item(2, "901", "100", "10"), item(3, "902", "555", "10", servico="Vancouver Experience"),
    ], periodo_completo=True))
    assert aluno(db, "10").teen and "Vancouver Experience" in aluno(db, "10").teen_motivo


def test_marca_e_do_aluno_inteiro(db, cenario):
    # Aluno Summer tem também um visto: todas as tarefas dele contam como teen.
    checklist.confirmar(checklist.criar_previa([item(2, "910", "200", "20", servico="Visto - Canadá - eTA")], periodo_completo=True))
    teen = consultas.tarefas(Filtros(publico=FiltroPublico.TEEN, hoje=HOJE))[0]
    assert [t.item_checklist_egali for t in teen] == ["910"]


def test_filtro_publico_nas_filas(db, cenario):
    checklist.confirmar(checklist.criar_previa([item(2, "901", "100", "10"), item(3, "902", "200", "20")], periodo_completo=True))
    todos = consultas.contar(Filtros(hoje=HOJE))
    suporte = consultas.contar(Filtros(publico=FiltroPublico.SUPORTE, hoje=HOJE))
    so_teen = consultas.contar(Filtros(publico=FiltroPublico.TEEN, hoje=HOJE))
    assert (todos, suporte, so_teen) == (2, 1, 1)
    linhas = {l.usuario.nome if l.usuario else None: l for l in consultas.resumo_por_consultor(HOJE, FiltroPublico.SUPORTE)}
    # Da Ana, só o Aluno Suporte fica: Summer e Tag são teen (o Consultor Teen tem outro consultor).
    assert linhas["Consultora Ana"].abertas == 1 and linhas["Consultora Ana"].programas == 1
    todos_ana = {l.usuario.nome if l.usuario else None: l for l in consultas.resumo_por_consultor(HOJE)}["Consultora Ana"]
    assert todos_ana.programas == 3


def test_tela_publico_teen(db, cenario, app):
    cliente = app.test_client()
    admin = db.session.execute(db.select(Usuario)).scalar_one()
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = admin.id, "t"
    assert "Alunos teen hoje" in cliente.get("/cadastros/publico-teen").get_data(as_text=True)
    # Nome com aspas não quebra o confirm() da remoção (nem vira script).
    db.session.add(ConsultorTeen(nome="Pessoa D'Teste", nome_normalizado=normalizar_texto("Pessoa D'Teste")))
    db.session.commit()
    pagina = cliente.get("/cadastros/publico-teen").get_data(as_text=True)
    assert "confirm('Remover" not in pagina and 'confirm("Remover Pessoa D\\u0027Teste da equipe teen?")' in pagina
    cliente.post("/cadastros/publico-teen", data={"csrf": "t", "acao": "adicionar_consultor", "nome": "Pessoa Da Equipe Teen"})
    assert aluno(db, "40").teen
    summer = db.session.execute(db.select(ServicoEgali).filter_by(nome="Summer Schools")).scalar_one()
    outros = [str(s.id) for s in db.session.execute(db.select(ServicoEgali).filter_by(teen=True)).scalars() if s.id != summer.id]
    cliente.post("/cadastros/publico-teen", data={"csrf": "t", "acao": "servicos", "servico": outros})  # desmarca Summer
    assert not aluno(db, "20").teen
    pagina = cliente.get("/fila?publico=teen").get_data(as_text=True)
    assert 'value="teen" selected' in pagina
