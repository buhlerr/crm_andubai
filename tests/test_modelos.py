from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from app.catalogo_inicial import buscar_etapa_por_texto, carregar_catalogo
from app.models import (
    Aluno,
    Programa,
    SituacaoPrograma,
    StatusTarefa,
    Tarefa,
    TipoPrograma,
    Usuario,
)
from app.texto import normalizar_texto


@pytest.fixture
def cenario(db):
    carregar_catalogo()
    consultora = Usuario(nome="Consultora Teste", email="consultora@exemplo.test")
    estagiaria = Usuario(nome="Estagiária Teste", email="estagiaria@exemplo.test")
    aluno = Aluno(aluno_id_egali="9000001", nome="Aluno Fictício")
    programa = Programa(programa_id_egali="800001", aluno=aluno, consultor=consultora, pontuacao=Decimal("78"))
    tarefa = Tarefa(
        item_checklist_egali="7000001",
        programa=programa,
        etapa=buscar_etapa_por_texto("SA - GERAL - Cadastrar flight details"),
        prazo_egali=date(2026, 9, 10),
    )
    db.session.add_all([consultora, estagiaria, tarefa])
    db.session.commit()
    return {"consultora": consultora, "estagiaria": estagiaria, "aluno": aluno, "programa": programa, "tarefa": tarefa}


def test_responsavel_segue_consultor_ate_ser_trocado(db, cenario):
    tarefa = cenario["tarefa"]
    assert tarefa.responsavel is cenario["consultora"]
    tarefa.responsavel_manual = cenario["estagiaria"]
    assert tarefa.responsavel is cenario["estagiaria"]


def test_data_planejada_nao_muda_o_atraso(cenario):
    tarefa = cenario["tarefa"]
    hoje = date(2026, 9, 29)
    assert tarefa.data_prevista == date(2026, 9, 10)
    assert tarefa.atrasada(hoje) and tarefa.dias_de_atraso(hoje) == 19
    tarefa.data_planejada = date(2026, 10, 1)
    assert tarefa.data_prevista == date(2026, 10, 1)
    assert tarefa.prazo_egali == date(2026, 9, 10)  # a do procedimento continua fixa
    assert tarefa.atrasada(hoje) and tarefa.dias_de_atraso(hoje) == 19  # e o atraso também
    assert tarefa.planejada_apos_prazo
    tarefa.data_planejada = date(2026, 9, 5)
    assert not tarefa.planejada_apos_prazo


def test_atrasada_e_justificativa(cenario):
    tarefa = cenario["tarefa"]
    assert tarefa.atrasada(hoje=date(2026, 9, 29))
    assert not tarefa.tem_justificativa
    tarefa.obs_egali = "17/09 - aguardando retorno do visto"
    assert tarefa.tem_justificativa
    tarefa.status = StatusTarefa.CONCLUIDA
    assert not tarefa.atrasada(hoje=date(2026, 9, 29))


def test_programa_cancelado_tira_tarefa_da_fila(cenario):
    assert cenario["tarefa"].na_fila
    cenario["programa"].situacao = SituacaoPrograma.CANCELADO
    assert not cenario["tarefa"].na_fila


def test_vip(cenario):
    programa = cenario["programa"]
    assert not programa.vip
    programa.pontuacao = Decimal("85")
    assert programa.vip


def test_item_checklist_nao_duplica(db, cenario):
    db.session.add(Tarefa(item_checklist_egali="7000001", programa=cenario["programa"], etapa=cenario["tarefa"].etapa))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_aluno_id_nao_duplica(db, cenario):
    db.session.add(Aluno(aluno_id_egali="9000001", nome="Outro nome"))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_varios_programas_so_de_visto_sem_programa_id(db, cenario):
    outro = Aluno(aluno_id_egali="9000002", nome="Aluno Só Visto")
    db.session.add_all([
        Programa(aluno=cenario["aluno"], tipo=TipoPrograma.SO_VISTO),
        Programa(aluno=outro, tipo=TipoPrograma.SO_VISTO),
    ])
    db.session.commit()


def test_um_so_programa_so_de_visto_ativo_por_aluno(db, cenario):
    aluno = cenario["aluno"]
    db.session.add(Programa(aluno=aluno, tipo=TipoPrograma.SO_VISTO, situacao=SituacaoPrograma.INCORPORADO))
    db.session.add(Programa(aluno=aluno, tipo=TipoPrograma.SO_VISTO))
    db.session.commit()
    db.session.add(Programa(aluno=aluno, tipo=TipoPrograma.SO_VISTO))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_status_invalido_e_recusado(db, cenario):
    cenario["tarefa"].status = "feito"
    with pytest.raises(StatementError):
        db.session.commit()


def test_chave_estrangeira_e_respeitada(db):
    db.session.add(Programa(programa_id_egali="1", aluno_id=999))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_hora_local_trata_data_sem_fuso_como_utc():
    from datetime import datetime, timezone

    from app.models.base import hora_local

    sem_fuso = datetime(2026, 9, 29, 13, 48)
    assert hora_local(sem_fuso) == datetime(2026, 9, 29, 13, 48, tzinfo=timezone.utc)
    assert hora_local(sem_fuso).utcoffset() == datetime.now().astimezone().utcoffset()
    assert hora_local(None) is None


def test_normalizar_texto():
    assert normalizar_texto("  SA - CAN – Verificar   status ") == "sa - can - verificar status"
    assert normalizar_texto("didn`t") == normalizar_texto("didn't")
    assert normalizar_texto(None) == ""
