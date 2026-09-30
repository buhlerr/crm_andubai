from datetime import date
import pytest
from app import create_app
from app.extensions import db
from app.models import Aluno, EtapaModelo, Programa, StatusTarefa, Tarefa, TipoPrograma, Trilha
from app import andamento


@pytest.fixture
def app_ctx():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_calcular_andamento_basico(app_ctx):
    # Setup test tracks and steps
    trilha = Trilha(codigo="GERAL", nome="Geral", ordem=1)
    db.session.add(trilha)
    db.session.flush()

    e1 = EtapaModelo(trilha_id=trilha.id, nome="Passo 1", texto_egali="passo 1", ordem=1, ativa=True)
    e2 = EtapaModelo(trilha_id=trilha.id, nome="Passo 2", texto_egali="passo 2", ordem=2, ativa=True)
    e3 = EtapaModelo(trilha_id=trilha.id, nome="Realizar contato de relacionamento pré-embarque", texto_egali="realizar contato de relacionamento pre-embarque", ordem=3, ativa=True)
    e4 = EtapaModelo(trilha_id=trilha.id, nome="Contato pós embarque", texto_egali="contato pos embarque", ordem=4, ativa=True)
    db.session.add_all([e1, e2, e3, e4])
    db.session.flush()

    aluno = Aluno(aluno_id_egali="12345", nome="Aluno Teste")
    db.session.add(aluno)
    db.session.flush()

    programa = Programa(aluno_id=aluno.id, tipo=TipoPrograma.NORMAL, mes_embarque=date(2026, 11, 1), data_embarque=date(2026, 11, 10))
    db.session.add(programa)
    db.session.flush()

    # Task for Passo 2 is open
    t2 = Tarefa(item_checklist_egali="1001", programa_id=programa.id, etapa_id=e2.id, status=StatusTarefa.A_FAZER, prazo_egali=date(2026, 10, 1))
    db.session.add(t2)
    db.session.commit()

    resultado = andamento.calcular(programa, hoje=date(2026, 9, 30))
    # Post-embarque excluded. Remaining: e1, e2, e3. Total = 3.
    # e1 is before e2 (open) -> finalizado_estimado (done)
    # e2 is open -> em_aberto
    # e3 is after -> pendente
    # done = 1/3 -> 33%
    assert resultado.total == 3
    assert resultado.feitos == 1
    assert resultado.porcentagem == 33
