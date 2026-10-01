from datetime import date, timedelta

from app import consultas
from app.catalogo_inicial import carregar_catalogo
from app.consultas import Filtros
from app.importacao import base_alunos, checklist
from app.models import Papel, Tarefa, Usuario

HOJE = date.today()


def item(n, numero, procedimento):
    return {"linha": n, "valores": {"#": numero, "id da compra": "100", "id aluno": "10", "procedimento": procedimento,
                                    "data": (HOJE + timedelta(days=5)).strftime("%d/%m/%Y"), "status": "Aguardando",
                                    "serviço": "Curso Premium"}}


def test_filtra_por_procedimento(db, app):
    carregar_catalogo()
    db.session.add(Usuario(nome="Consultora Ana", email="ana@exemplo.test", papel=Papel.ADMIN))
    db.session.commit()
    base_alunos.confirmar(base_alunos.criar_previa([{"linha": 2, "valores": {
        "programa_id": "1", "aluno_id": "10", "aluno_name": "Aluno Teste", "compra_id": "100", "consultor": "Consultora Ana"}}]))
    checklist.confirmar(checklist.criar_previa([
        item(2, "901", "SA - GERAL - Cadastrar flight details"),
        item(3, "902", "SA - GERAL - Procedimento de teste do filtro"),
    ], periodo_completo=True))
    voo = db.session.execute(db.select(Tarefa).filter_by(item_checklist_egali="901")).scalar_one()

    assert consultas.contar(Filtros(hoje=HOJE)) == 2
    assert [t.item_checklist_egali for t in consultas.tarefas(Filtros(etapa=voo.etapa_id, hoje=HOJE))[0]] == ["901"]
    assert {e.id for e in consultas.procedimentos_na_fila()} == {t.etapa_id for t in db.session.execute(db.select(Tarefa)).scalars()}

    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = db.session.execute(db.select(Usuario)).scalar_one().id, "t"
    pagina = cliente.get(f"/fila?visao=lista&procedimento={voo.etapa_id}").get_data(as_text=True)
    assert f'value="{voo.etapa_id}" selected' in pagina
    assert "Procedimento de teste do filtro" in pagina  # continua como opção no filtro
