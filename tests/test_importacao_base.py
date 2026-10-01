from datetime import date
from decimal import Decimal

import pytest

from app.catalogo_inicial import buscar_etapa_por_texto, carregar_catalogo
from app.importacao import ErroImportacao
from app.importacao.base_alunos import confirmar, criar_previa, descartar
from app.models import (
    Aluno,
    ApelidoConsultor,
    Compra,
    Gravidade,
    Importacao,
    OrigemCompra,
    Programa,
    SituacaoImportacao,
    SituacaoPrograma,
    StatusTarefa,
    Tarefa,
    TipoOcorrencia,
    TipoPrograma,
    Usuario,
)
from app.texto import normalizar_texto


def linha(n, programa_id, aluno_id, nome="Aluno Fictício", compras="100, 101", consultor="Consultora Um", **extras):
    valores = {
        "programa_id": programa_id,
        "aluno_id": aluno_id,
        "aluno_name": nome,
        "compra_id": compras,
        "consultor": consultor,
        "mês embarque": "2027-01-01",
        "programa_data_embarque": "2027-01-08",
        "pais_name": "Canadá",
        "pt_prog": 71.0,
    }
    valores.update(extras)
    return {"linha": n, "valores": valores}


def importar(linhas):
    return confirmar(criar_previa(linhas))


def programa(db, programa_id):
    return db.session.execute(db.select(Programa).filter_by(programa_id_egali=programa_id)).scalar_one()


def ocorrencias(importacao, tipo):
    return [o for o in importacao.ocorrencias if o.tipo == tipo]


@pytest.fixture
def usuarios(db):
    um = Usuario(nome="Consultora Um da Silva", email="um@exemplo.test")
    dois = Usuario(nome="Consultor Dois", email="dois@exemplo.test")
    db.session.add_all([um, dois])
    db.session.commit()
    return {"um": um, "dois": dois}


BASE = [
    linha(2, 402668.0, 2147975.0, "Ana Teste", "5703996, 5703997, 5703998"),
    linha(3, "425463", "2159249", "Bruno Teste", "6139906,6139907", consultor="Consultor Dois"),
]


# ---------------------------------------------------------------- prévia e confirmação


def test_previa_nao_grava_nada(db, usuarios):
    importacao = criar_previa(BASE)
    assert importacao.situacao == SituacaoImportacao.PREVIA
    assert importacao.resumo["programas_novos"] == 2
    assert importacao.resumo["alunos_novos"] == 2
    assert importacao.resumo["compras_ligadas"] == 5
    assert db.session.query(Programa).count() == 0
    assert db.session.query(Aluno).count() == 0
    assert db.session.query(Compra).count() == 0


def test_confirmar_grava_o_que_a_previa_mostrou(db, usuarios):
    importacao = importar(BASE)
    assert importacao.situacao == SituacaoImportacao.CONFIRMADA
    assert importacao.dados_lidos is None
    p = programa(db, "402668")
    assert p.aluno.aluno_id_egali == "2147975"
    assert p.aluno.nome == "Ana Teste"
    assert sorted(c.compra_id_egali for c in p.compras) == ["5703996", "5703997", "5703998"]
    assert p.consultor is usuarios["um"]  # "Consultora Um" bate parcialmente com "Consultora Um da Silva"
    assert p.mes_embarque == date(2027, 1, 1)
    assert p.pontuacao == Decimal("71.00")
    assert p.ultima_importacao_id == importacao.id


def test_descartar(db, usuarios):
    importacao = descartar(criar_previa(BASE))
    assert importacao.situacao == SituacaoImportacao.DESCARTADA
    assert importacao.dados_lidos is None
    with pytest.raises(ErroImportacao):
        confirmar(importacao)
    assert db.session.query(Programa).count() == 0


def test_previa_guarda_so_as_colunas_usadas(db, usuarios):
    importacao = criar_previa([linha(2, "1", "1", aluno_cpf="000.000.000-00", aluno_email="a@b.test")])
    assert "aluno_cpf" not in importacao.dados_lidos[0]["valores"]
    assert "aluno_email" not in importacao.dados_lidos[0]["valores"]


def test_confirmacao_recusada_se_o_banco_mudou_desde_a_previa(db, usuarios):
    previa_antiga = criar_previa(BASE)
    importar(BASE)
    with pytest.raises(ErroImportacao, match="mudaram"):
        confirmar(previa_antiga)
    assert previa_antiga.situacao == SituacaoImportacao.PREVIA


def test_importar_duas_vezes_nao_duplica(db, usuarios):
    importar(BASE)
    segunda = importar(BASE)
    r = segunda.resumo
    assert (r["programas_novos"], r["alunos_novos"], r["compras_ligadas"]) == (0, 0, 0)
    assert r["programas_sem_mudanca"] == 2
    assert db.session.query(Programa).count() == 2
    assert db.session.query(Compra).count() == 5


def test_mesmo_arquivo_gera_aviso(db, usuarios):
    confirmar(criar_previa(BASE, arquivo_hash="abc"))
    importacao = criar_previa(BASE, arquivo_hash="abc")
    assert ocorrencias(importacao, TipoOcorrencia.ARQUIVO_JA_IMPORTADO)


# ---------------------------------------------------------------- atualização, cancelamento, reativação


def test_atualiza_cadastro_e_nome_sem_criar_outro_aluno(db, usuarios):
    importar(BASE)
    alterada = [
        linha(2, "402668", "2147975", "Ana Teste Sobrenome", "5703996, 5703997, 5703998", consultor="Consultor Dois",
              pais_name="EUA"),
        BASE[1],
    ]
    importacao = importar(alterada)
    r = importacao.resumo
    assert r["programas_atualizados"] == 1
    assert r["alunos_renomeados"] == 1
    assert set(r["detalhes"]["programas_atualizados"][0]["campos"]) == {"Consultor", "País"}
    p = programa(db, "402668")
    assert p.aluno.nome == "Ana Teste Sobrenome"
    assert p.pais == "EUA"
    assert p.consultor is usuarios["dois"]
    assert db.session.query(Aluno).count() == 2


def test_coluna_ausente_nao_apaga_valor(db, usuarios):
    importar(BASE)
    sem_pais = []
    for b in BASE:
        valores = dict(b["valores"])
        del valores["pais_name"]
        sem_pais.append({"linha": b["linha"], "valores": valores})
    importar(sem_pais)
    assert programa(db, "402668").pais == "Canadá"


def test_programa_que_sumiu_e_cancelado_e_volta_se_reaparecer(db, usuarios):
    carregar_catalogo()
    outro_programa_do_mesmo_aluno = linha(4, "999", "2147975", "Ana Teste", "777")
    importar([*BASE, outro_programa_do_mesmo_aluno])
    p = programa(db, "402668")
    tarefa = Tarefa(item_checklist_egali="1", programa=p, etapa=buscar_etapa_por_texto("SA - GERAL - Cadastrar flight details"))
    db.session.add(tarefa)
    db.session.commit()

    importacao = importar([BASE[1], outro_programa_do_mesmo_aluno])
    assert importacao.resumo["programas_cancelados"] == 1
    assert p.situacao == SituacaoPrograma.CANCELADO
    assert p.cancelado_em is not None
    assert not tarefa.na_fila
    assert db.session.get(Tarefa, tarefa.id) is not None  # histórico preservado
    assert programa(db, "999").situacao == SituacaoPrograma.ATIVO  # outro programa do mesmo aluno não é afetado

    importacao = importar([*BASE, outro_programa_do_mesmo_aluno])
    assert importacao.resumo["programas_reativados"] == 1
    assert p.situacao == SituacaoPrograma.ATIVO
    assert p.reativado_em is not None
    assert tarefa.na_fila


def test_aviso_de_cancelamento_em_massa(db, usuarios):
    importar([linha(i, str(1000 + i), str(5000 + i), compras=str(9000 + i)) for i in range(2, 32)])
    importacao = criar_previa([linha(2, "1002", "5002", compras="9002")])
    assert importacao.resumo["programas_cancelados"] == 29
    assert ocorrencias(importacao, TipoOcorrencia.CANCELAMENTO_EM_MASSA)


def test_importacao_nao_mexe_no_trabalho_da_equipe(db, usuarios):
    carregar_catalogo()
    importar(BASE)
    p = programa(db, "402668")
    tarefa = Tarefa(
        item_checklist_egali="1", programa=p, etapa=buscar_etapa_por_texto("SA - GERAL - Cadastrar flight details"),
        status=StatusTarefa.EM_ANDAMENTO, responsavel_manual=usuarios["dois"], data_planejada=date(2027, 1, 1),
    )
    db.session.add(tarefa)
    db.session.commit()
    importar([linha(2, "402668", "2147975", "Ana Teste", "5703996, 5703997, 5703998", consultor="Consultor Dois"), BASE[1]])
    assert tarefa.status == StatusTarefa.EM_ANDAMENTO
    assert tarefa.responsavel_manual is usuarios["dois"]
    assert tarefa.data_planejada == date(2027, 1, 1)


# ---------------------------------------------------------------- compras


def test_compras_novas_entram_e_as_que_sairam_sao_desligadas(db, usuarios):
    importar(BASE)
    importacao = importar([linha(2, "402668", "2147975", "Ana Teste", "5703996, 5703999"), BASE[1]])
    assert importacao.resumo["compras_ligadas"] == 1
    assert importacao.resumo["compras_desligadas"] == 2
    p = programa(db, "402668")
    assert sorted(c.compra_id_egali for c in p.compras) == ["5703996", "5703999"]
    desligada = db.session.execute(db.select(Compra).filter_by(compra_id_egali="5703997")).scalar_one()
    assert desligada.programa is None and desligada.desligada_em is not None

    religada = importar(BASE)
    assert religada.resumo["compras_ligadas"] == 2
    assert desligada.programa is p and desligada.desligada_em is None


def test_compra_juntada_pelo_checklist_nao_e_desligada(db, usuarios):
    importar(BASE)
    p = programa(db, "402668")
    db.session.add(Compra(compra_id_egali="8888", programa=p, origem=OrigemCompra.CHECKLIST))
    db.session.commit()
    importacao = importar(BASE)
    assert importacao.resumo["compras_desligadas"] == 0
    assert "8888" in {c.compra_id_egali for c in p.compras}


def test_compra_que_muda_de_programa_leva_as_tarefas(db, usuarios):
    carregar_catalogo()
    importar(BASE)
    compra = db.session.execute(db.select(Compra).filter_by(compra_id_egali="5703998")).scalar_one()
    tarefa = Tarefa(item_checklist_egali="1", programa=compra.programa, compra=compra,
                    etapa=buscar_etapa_por_texto("SA - GERAL - Cadastrar flight details"))
    db.session.add(tarefa)
    db.session.commit()

    importacao = importar([
        linha(2, "402668", "2147975", "Ana Teste", "5703996, 5703997"),
        linha(3, "425463", "2159249", "Bruno Teste", "6139906,6139907, 5703998", consultor="Consultor Dois"),
    ])
    assert importacao.resumo["compras_movidas"] == 1
    assert importacao.resumo["compras_desligadas"] == 0
    assert compra.programa.programa_id_egali == "425463"
    assert tarefa.programa.programa_id_egali == "425463"


def test_compra_repetida_em_dois_programas_fica_no_primeiro(db, usuarios):
    importacao = importar([
        linha(2, "1", "10", compras="500, 501"),
        linha(3, "2", "20", compras="501, 502"),
    ])
    assert ocorrencias(importacao, TipoOcorrencia.LINHA_INVALIDA)
    compra = db.session.execute(db.select(Compra).filter_by(compra_id_egali="501")).scalar_one()
    assert compra.programa.programa_id_egali == "1"


# ---------------------------------------------------------------- linhas com problema


def test_linhas_sem_id_viram_erro_e_nao_sao_importadas(db, usuarios):
    importacao = importar([
        *BASE,
        linha(4, None, "3000", "Sem Programa"),
        linha(5, "4000", "", "Sem Aluno"),
        linha(6, "402668", "2147975", "Repetido"),
        linha(7, "abc", "1", "ID com letra"),
    ])
    erros = [o for o in importacao.ocorrencias if o.gravidade == Gravidade.ERRO]
    assert {(o.linha, o.tipo) for o in erros} == {
        (4, TipoOcorrencia.SEM_PROGRAMA_ID),
        (5, TipoOcorrencia.SEM_ALUNO_ID),
        (6, TipoOcorrencia.LINHA_INVALIDA),
        (7, TipoOcorrencia.LINHA_INVALIDA),
    }
    assert importacao.resumo["erros"] == 4
    assert db.session.query(Programa).count() == 2
    assert programa(db, "402668").aluno.nome == "Ana Teste"


def test_linha_so_com_coluna_auxiliar_e_ignorada_sem_erro(db, usuarios):
    sobra = {"linha": 9, "valores": {"programa_id": None, "aluno_id": None, "aluno_name": None, "compra_id": None,
                                      "consultor": "", "enviado": "Sim"}}
    importacao = importar([*BASE, sobra])
    assert importacao.resumo["erros"] == 0
    assert importacao.resumo["linhas_sem_dados_ignoradas"] == 1


def test_planilha_sem_coluna_obrigatoria(db):
    bruta = linha(2, "1", "1")
    del bruta["valores"]["compra_id"]
    with pytest.raises(ErroImportacao, match="compra_id"):
        criar_previa([bruta])


def test_planilha_vazia(db):
    with pytest.raises(ErroImportacao):
        criar_previa([])


def test_valor_invalido_gera_aviso_e_mantem_o_resto(db, usuarios):
    importacao = importar([linha(2, "1", "1", pt_prog="muito")])
    assert ocorrencias(importacao, TipoOcorrencia.LINHA_INVALIDA)
    assert programa(db, "1").pais == "Canadá"
    assert programa(db, "1").pontuacao is None


# ---------------------------------------------------------------- consultor


def test_consultor_nao_encontrado_gera_um_aviso_por_nome(db, usuarios):
    importacao = importar([
        linha(2, "1", "1", consultor="Fulana Desconhecida"),
        linha(3, "2", "2", compras="200", consultor="Fulana Desconhecida"),
    ])
    avisos = ocorrencias(importacao, TipoOcorrencia.CONSULTOR_NAO_ENCONTRADO)
    assert len(avisos) == 1 and "2 programa(s)" in avisos[0].mensagem
    assert programa(db, "1").consultor is None
    assert programa(db, "1").consultor_texto == "Fulana Desconhecida"


def test_sem_consultor_de_proposito_nao_gera_aviso(db, usuarios):
    importacao = importar([linha(2, "1", "1", consultor="(Sem consultor)")])
    assert not ocorrencias(importacao, TipoOcorrencia.CONSULTOR_NAO_ENCONTRADO)
    assert importacao.resumo["programas_sem_consultor"] == 1


def test_nome_ambiguo_nao_escolhe_ninguem(db, usuarios):
    db.session.add(Usuario(nome="Consultor Dois Outro", email="outro@exemplo.test"))
    db.session.commit()
    importacao = importar([linha(2, "1", "1", consultor="Consultor Dois")])
    # O nome exato continua valendo, mesmo havendo outro parecido.
    assert programa(db, "1").consultor is usuarios["dois"]
    importacao = importar([linha(2, "1", "1", consultor="Consultor")])
    assert programa(db, "1").consultor is None
    assert "mais de um" in ocorrencias(importacao, TipoOcorrencia.CONSULTOR_NAO_ENCONTRADO)[0].mensagem


def test_excecao_de_nome_tem_prioridade(db, usuarios):
    db.session.add(ApelidoConsultor(texto_planilha="Apelido Estranho", texto_normalizado=normalizar_texto("Apelido Estranho"),
                                    usuario=usuarios["dois"]))
    db.session.commit()
    importar([linha(2, "1", "1", consultor="  apelido   estranho ")])
    assert programa(db, "1").consultor is usuarios["dois"]


def test_consultor_resolvido_depois_de_cadastrado(db):
    importar([linha(2, "1", "1", consultor="Nova Consultora")])
    assert programa(db, "1").consultor is None
    db.session.add(Usuario(nome="Nova Consultora", email="nova@exemplo.test"))
    db.session.commit()
    importacao = importar([linha(2, "1", "1", consultor="Nova Consultora")])
    assert importacao.resumo["programas_atualizados"] == 1
    assert programa(db, "1").consultor.nome == "Nova Consultora"


# ---------------------------------------------------------------- programa só de visto


def test_programa_so_de_visto_e_juntado_ao_curso(db, usuarios):
    carregar_catalogo()
    aluno = Aluno(aluno_id_egali="2147975", nome="Ana Teste")
    so_visto = Programa(aluno=aluno, tipo=TipoPrograma.SO_VISTO)
    compra_visto = Compra(compra_id_egali="7777", programa=so_visto, origem=OrigemCompra.CHECKLIST)
    tarefa = Tarefa(item_checklist_egali="1", programa=so_visto, compra=compra_visto,
                    etapa=buscar_etapa_por_texto("SA - VISTOS - Ter uma cópia do visto/negativa"))
    db.session.add_all([so_visto, tarefa])
    db.session.commit()

    importacao = importar(BASE)
    assert importacao.resumo["programas_so_visto_incorporados"] == 1
    curso = programa(db, "402668")
    assert so_visto.situacao == SituacaoPrograma.INCORPORADO
    assert so_visto.incorporado_ao_programa_id == curso.id
    assert compra_visto.programa is curso
    assert compra_visto.origem == OrigemCompra.CHECKLIST
    assert tarefa.programa is curso

    # A compra juntada não é desligada nas próximas importações.
    assert importar(BASE).resumo["compras_desligadas"] == 0
    assert compra_visto.programa is curso


def test_programa_so_de_visto_com_dois_cursos_pede_decisao(db, usuarios):
    aluno = Aluno(aluno_id_egali="2147975", nome="Ana Teste")
    so_visto = Programa(aluno=aluno, tipo=TipoPrograma.SO_VISTO)
    db.session.add(so_visto)
    db.session.commit()
    importacao = importar([*BASE, linha(4, "999", "2147975", "Ana Teste", "777")])
    assert ocorrencias(importacao, TipoOcorrencia.ALUNO_COM_VARIOS_PROGRAMAS)
    assert so_visto.situacao == SituacaoPrograma.ATIVO


def test_importacao_registrada(db, usuarios):
    importar(BASE)
    assert db.session.query(Importacao).filter_by(situacao=SituacaoImportacao.CONFIRMADA).count() == 1
