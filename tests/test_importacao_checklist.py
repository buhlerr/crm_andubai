from datetime import date
from decimal import Decimal

import pytest

from app.catalogo_inicial import carregar_catalogo
from app.importacao import ErroImportacao
from app.importacao import base_alunos, checklist
from app.importacao.leitor_csv import decodificar, ler_texto_csv
from app.models import (
    Aluno,
    CategoriaServico,
    Compra,
    EtapaModelo,
    Gravidade,
    HistoricoTarefa,
    MotivoEncerramento,
    OrigemCompra,
    Programa,
    ServicoEgali,
    SituacaoPrograma,
    StatusTarefa,
    Tarefa,
    TipoOcorrencia,
    TipoPrograma,
    Trilha,
    Usuario,
)

FLIGHT = "SA - GERAL - Cadastrar flight details"
COPIA_VISTO = "SA - VISTOS - Ter uma cópia do visto/negativa"
VIP = "SA - VIP - Primeiro contato de relacionamento com aluno"


def item(n, numero, compra, aluno, procedimento=FLIGHT, data="15/10/2026", servico="Curso Premium", **extras):
    valores = {
        "#": numero, "id da compra": compra, "id aluno": aluno, "aluno": extras.pop("nome", "Aluno Fictício"),
        "procedimento": procedimento, "data": data, "status": "Aguardando", "serviço": servico,
        "consultor": extras.pop("consultor", "Consultora Um"), "neg": extras.pop("neg", ""),
        "país": "Canadá", "embarque": "08/01/2027",
    }
    valores.update(extras)
    return {"linha": n, "valores": valores}


def importar(linhas, **periodo):
    return checklist.confirmar(checklist.criar_previa(linhas, **periodo))


def tarefa(db, numero) -> Tarefa:
    return db.session.execute(db.select(Tarefa).filter_by(item_checklist_egali=numero)).scalar_one()


def ocorrencias(importacao, tipo):
    return [o for o in importacao.ocorrencias if o.tipo == tipo]


def base(linhas):
    return base_alunos.confirmar(base_alunos.criar_previa(linhas))


def linha_base(n, programa_id, aluno_id, compras, consultor="Consultora Um", nome="Aluno Fictício", pt_prog=71.0):
    return {"linha": n, "valores": {
        "programa_id": programa_id, "aluno_id": aluno_id, "aluno_name": nome, "compra_id": compras,
        "consultor": consultor, "pt_prog": pt_prog,
    }}


@pytest.fixture
def cenario(db):
    carregar_catalogo()
    um = Usuario(nome="Consultora Um", email="um@exemplo.test")
    dois = Usuario(nome="Consultor Dois", email="dois@exemplo.test")
    db.session.add_all([um, dois])
    db.session.commit()
    base([
        linha_base(2, "1000", "500", "100, 101", nome="Ana Teste"),
        linha_base(3, "2000", "600", "200", consultor="Consultor Dois", nome="Bruno Teste", pt_prog=90.0),
    ])
    return {"um": um, "dois": dois}


CHECKLIST = [
    item(2, "7001", "100", "500", FLIGHT, "15/10/2026", neg="17/09 - aguardando visto"),
    item(3, "7002", "101", "500", COPIA_VISTO, "20/10/2026", servico="Visto - Canadá - eTA"),
    item(4, "7003", "200", "600", FLIGHT, "01/11/2026", consultor="Consultor Dois"),
]


# ---------------------------------------------------------------- criação e idempotência


def test_previa_nao_grava(db, cenario):
    importacao = checklist.criar_previa(CHECKLIST)
    assert importacao.resumo["tarefas_novas"] == 3
    assert db.session.query(Tarefa).count() == 0


def test_cria_tarefas_ligadas_a_compra_e_programa(db, cenario):
    importar(CHECKLIST)
    t = tarefa(db, "7001")
    assert t.programa.programa_id_egali == "1000"
    assert t.compra.compra_id_egali == "100"
    assert t.etapa.texto_egali == FLIGHT
    assert t.etapa.trilha.codigo == "GERAL"
    assert t.prazo_egali == date(2026, 10, 15)
    assert t.obs_egali == "17/09 - aguardando visto"
    assert t.status == StatusTarefa.A_FAZER
    assert t.status_egali == "Aguardando"
    assert t.responsavel is cenario["um"]
    assert tarefa(db, "7003").responsavel is cenario["dois"]


def test_importar_de_novo_nao_duplica(db, cenario):
    importar(CHECKLIST)
    segunda = importar(CHECKLIST)
    assert segunda.resumo["tarefas_novas"] == 0
    assert segunda.resumo["tarefas_sem_mudanca"] == 3
    assert db.session.query(Tarefa).count() == 3


def test_previa_guarda_so_as_colunas_usadas(db, cenario):
    importacao = checklist.criar_previa([item(2, "1", "100", "500", **{"e-mail": "a@b.test", "telefone": "5,5E+12"})])
    assert "e-mail" not in importacao.dados_lidos[0]["valores"]
    assert "telefone" not in importacao.dados_lidos[0]["valores"]


# ---------------------------------------------------------------- atualização sem tocar no trabalho da equipe


def test_atualiza_prazo_e_neg_mas_nao_o_trabalho_da_equipe(db, cenario):
    importar(CHECKLIST)
    t = tarefa(db, "7001")
    t.status = StatusTarefa.AGUARDANDO_ALUNO
    t.responsavel_manual = cenario["dois"]
    t.data_planejada = date(2026, 12, 1)
    db.session.commit()

    novo = [item(2, "7001", "100", "500", FLIGHT, "30/10/2026", neg="17/09 - aguardando visto; 25/09 - visto saiu"),
            *CHECKLIST[1:]]
    importacao = importar(novo)
    assert importacao.resumo["tarefas_atualizadas"] == 1
    assert importacao.resumo["detalhes"]["campos_atualizados"] == {"prazo": 1, "NEG": 1}
    assert t.prazo_egali == date(2026, 10, 30)
    assert t.obs_egali.endswith("visto saiu")
    assert t.status == StatusTarefa.AGUARDANDO_ALUNO
    assert t.responsavel_manual is cenario["dois"]
    assert t.data_planejada == date(2026, 12, 1)  # a importação atualiza a data da Egali, nunca a planejada
    campos = {h.campo for h in db.session.execute(db.select(HistoricoTarefa).filter_by(tarefa_id=t.id)).scalars()}
    assert campos == {"prazo_egali", "obs_egali"}


# ---------------------------------------------------------------- itens que somem e voltam


def test_item_que_sumiu_e_finalizado(db, cenario):
    importar(CHECKLIST)
    importacao = importar(CHECKLIST[1:], periodo_completo=True)
    assert importacao.resumo["tarefas_finalizadas"] == 1
    t = tarefa(db, "7001")
    assert t.status == StatusTarefa.CONCLUIDA
    assert t.motivo_encerramento == MotivoEncerramento.FINALIZADO
    assert t.encerrada_egali_em is not None
    assert not t.na_fila


def test_item_que_sumiu_de_programa_cancelado_e_cancelado(db, cenario):
    importar(CHECKLIST)
    base([linha_base(3, "2000", "600", "200", consultor="Consultor Dois", nome="Bruno Teste")])  # programa 1000 sumiu
    importacao = importar([CHECKLIST[2]], periodo_completo=True)
    assert importacao.resumo["tarefas_canceladas"] == 2
    assert tarefa(db, "7001").motivo_encerramento == MotivoEncerramento.CANCELADO


def test_item_de_compra_desligada_e_cancelado(db, cenario):
    importar(CHECKLIST)
    base([linha_base(2, "1000", "500", "100", nome="Ana Teste"),  # compra 101 saiu da célula
          linha_base(3, "2000", "600", "200", consultor="Consultor Dois", nome="Bruno Teste", pt_prog=90.0)])
    importar([CHECKLIST[0], CHECKLIST[2]], periodo_completo=True)
    assert tarefa(db, "7002").motivo_encerramento == MotivoEncerramento.CANCELADO


def test_so_encerra_dentro_do_periodo(db, cenario):
    importar(CHECKLIST)
    # Exportação de 20/10 a 31/12: o item 7001 (prazo 15/10) está fora e não pode ser encerrado.
    importacao = importar([CHECKLIST[2]], periodo_inicio=date(2026, 10, 20), periodo_fim=date(2026, 12, 31))
    assert importacao.resumo["tarefas_fora_do_periodo"] == 1
    assert importacao.resumo["tarefas_finalizadas"] == 1
    assert tarefa(db, "7001").encerrada_egali_em is None
    assert tarefa(db, "7002").encerrada_egali_em is not None


def test_encerrar_a_mao_as_tarefas_fora_do_periodo(db, cenario):
    importar(CHECKLIST)
    importacao = importar([CHECKLIST[2]], periodo_inicio=date(2026, 10, 20), periodo_fim=date(2026, 12, 31))
    assert [t.item_checklist_egali for t in checklist.tarefas_fora_do_periodo(importacao)] == ["7001"]

    encerradas = checklist.encerrar_a_mao(importacao, {tarefa(db, "7001").id}, cenario["um"])
    assert encerradas == 1
    t = tarefa(db, "7001")
    assert t.status == StatusTarefa.CONCLUIDA
    assert t.motivo_encerramento == MotivoEncerramento.FINALIZADO
    assert checklist.tarefas_fora_do_periodo(importacao) == []
    quem = {(h.campo, h.usuario_id) for h in db.session.execute(db.select(HistoricoTarefa).filter_by(tarefa_id=t.id)).scalars()}
    assert quem == {("encerramento", cenario["um"].id), ("status", cenario["um"].id)}

    # Se o item voltar ao checklist, a tarefa é reaberta como qualquer outra.
    importar(CHECKLIST)
    assert t.status == StatusTarefa.A_FAZER and t.encerrada_egali_em is None


def test_encerrar_a_mao_so_as_marcadas(db, cenario):
    importar(CHECKLIST)
    importacao = importar([CHECKLIST[2]], periodo_inicio=date(2026, 10, 25), periodo_fim=date(2026, 12, 31))
    fora = checklist.tarefas_fora_do_periodo(importacao)
    assert {t.item_checklist_egali for t in fora} == {"7001", "7002"}
    checklist.encerrar_a_mao(importacao, {tarefa(db, "7002").id}, cenario["um"])
    assert tarefa(db, "7001").encerrada_egali_em is None
    assert tarefa(db, "7002").encerrada_egali_em is not None


def test_encerrar_a_mao_so_na_importacao_mais_recente(db, cenario):
    importar(CHECKLIST)
    antiga = importar([CHECKLIST[2]], periodo_inicio=date(2026, 10, 20), periodo_fim=date(2026, 12, 31))
    importar([CHECKLIST[2]], periodo_inicio=date(2026, 10, 20), periodo_fim=date(2026, 12, 31))
    with pytest.raises(ErroImportacao, match="mais recente"):
        checklist.encerrar_a_mao(antiga, {tarefa(db, "7001").id}, cenario["um"])


def test_item_no_arquivo_mas_nao_importado_nao_fica_fora_do_periodo(db, cenario):
    importar(CHECKLIST)
    # 7001 continua no arquivo, com divergência de aluno: não é importado, mas também não está "fora do período".
    importacao = importar([item(2, "7001", "100", "999"), *CHECKLIST[1:]],
                          periodo_inicio=date(2026, 10, 20), periodo_fim=date(2026, 12, 31))
    assert checklist.tarefas_fora_do_periodo(importacao) == []


def test_periodo_padrao_e_o_do_arquivo(db, cenario):
    importacao = checklist.criar_previa(CHECKLIST)
    assert (importacao.periodo_inicio, importacao.periodo_fim) == (date(2026, 10, 15), date(2026, 11, 1))
    completo = checklist.criar_previa(CHECKLIST, periodo_completo=True)
    assert completo.periodo_inicio is None and completo.periodo_fim is None


def test_periodo_invertido(db, cenario):
    with pytest.raises(ErroImportacao):
        checklist.criar_previa(CHECKLIST, periodo_inicio=date(2026, 12, 1), periodo_fim=date(2026, 1, 1))


def test_item_que_volta_e_reaberto(db, cenario):
    importar(CHECKLIST)
    importar(CHECKLIST[1:], periodo_completo=True)
    importacao = importar(CHECKLIST)
    assert importacao.resumo["tarefas_reabertas"] == 1
    t = tarefa(db, "7001")
    assert t.status == StatusTarefa.A_FAZER
    assert t.encerrada_egali_em is None and t.motivo_encerramento is None


def test_item_nao_importado_nao_e_encerrado(db, cenario):
    importar(CHECKLIST)
    # O item 7001 continua no arquivo, mas agora com ID Aluno divergente: não é importado e não pode ser encerrado.
    importacao = importar([item(2, "7001", "100", "999"), *CHECKLIST[1:]], periodo_completo=True)
    assert ocorrencias(importacao, TipoOcorrencia.DIVERGENCIA_ALUNO)
    assert tarefa(db, "7001").encerrada_egali_em is None


def test_aviso_quando_quase_tudo_seria_encerrado(db, cenario):
    importar([item(i, str(8000 + i), "100", "500", data="15/10/2026") for i in range(2, 32)])
    importacao = checklist.criar_previa([item(2, "8002", "100", "500")], periodo_completo=True)
    assert importacao.resumo["tarefas_finalizadas"] == 29
    assert ocorrencias(importacao, TipoOcorrencia.CANCELAMENTO_EM_MASSA)


# ---------------------------------------------------------------- compras fora da planilha


def test_visto_avulso_e_juntado_ao_programa_do_aluno(db, cenario):
    importacao = importar([item(2, "7010", "300", "500", COPIA_VISTO, servico="Visto - Estados Unidos")])
    assert importacao.resumo["compras_juntadas"] == 1
    compra = db.session.execute(db.select(Compra).filter_by(compra_id_egali="300")).scalar_one()
    assert compra.origem == OrigemCompra.CHECKLIST
    assert compra.programa.programa_id_egali == "1000"
    assert tarefa(db, "7010").programa.programa_id_egali == "1000"
    # A próxima importação da planilha não desliga essa compra.
    assert base([linha_base(2, "1000", "500", "100, 101", nome="Ana Teste"),
                 linha_base(3, "2000", "600", "200", consultor="Consultor Dois", nome="Bruno Teste", pt_prog=90.0)]
                ).resumo["compras_desligadas"] == 0


def test_aluno_so_de_visto_ganha_programa_proprio(db, cenario):
    linhas = [
        item(2, "7020", "400", "900", COPIA_VISTO, servico="Visto - Canadá", nome="Carla Só Visto", consultor="Consultor Dois"),
        item(3, "7021", "401", "900", "SA - EUA - Agendamento do aluno", servico="Visto - Estados Unidos", nome="Carla Só Visto",
             consultor="Consultor Dois"),
    ]
    importacao = importar(linhas)
    assert importacao.resumo["programas_so_visto_criados"] == 1
    assert importacao.resumo["alunos_criados"] == 1
    assert importacao.resumo["erros"] == 0
    programa = tarefa(db, "7020").programa
    assert programa.tipo == TipoPrograma.SO_VISTO
    assert programa.programa_id_egali is None
    assert programa.aluno.nome == "Carla Só Visto"
    assert programa.consultor is cenario["dois"]  # vem do CSV: não está na planilha
    assert programa.pais == "Canadá"
    assert tarefa(db, "7021").programa is programa
    assert importar(linhas).resumo["programas_so_visto_criados"] == 0

    # Quando o aluno aparece na planilha com um curso, o programa só de visto é juntado a ele.
    r = base([linha_base(2, "1000", "500", "100, 101", nome="Ana Teste"),
              linha_base(3, "2000", "600", "200", consultor="Consultor Dois", nome="Bruno Teste", pt_prog=90.0),
              linha_base(4, "3000", "900", "450", nome="Carla Só Visto")]).resumo
    assert r["programas_so_visto_incorporados"] == 1
    assert tarefa(db, "7020").programa.programa_id_egali == "3000"
    assert programa.situacao == SituacaoPrograma.INCORPORADO


def test_curso_fora_da_planilha_e_erro_agrupado_por_compra(db, cenario):
    importacao = importar([
        item(2, "7030", "555", "901", FLIGHT, servico="Summer Schools", nome="Davi Summer"),
        item(3, "7031", "555", "901", "SA - GERAL - Cadastrar flight details", servico="Summer Schools", nome="Davi Summer",
             **{"#": "7031"}),
    ])
    erros = ocorrencias(importacao, TipoOcorrencia.PROGRAMA_FALTANDO_NA_PLANILHA)
    assert len(erros) == 1 and "2 item(ns)" in erros[0].mensagem
    assert erros[0].gravidade == Gravidade.ERRO
    assert importacao.resumo["itens_sem_programa"] == 2
    assert db.session.query(Tarefa).count() == 0


def test_curso_de_aluno_que_esta_na_planilha_explica_o_caso(db, cenario):
    importacao = importar([item(2, "7032", "556", "500", FLIGHT, servico="Curso Premium", nome="Ana Teste")])
    erro = ocorrencias(importacao, TipoOcorrencia.PROGRAMA_FALTANDO_NA_PLANILHA)[0]
    assert "o aluno está na planilha (programa 1000)" in erro.mensagem
    assert "segundo programa" in erro.mensagem
    outro = importar([item(2, "7033", "557", "999", FLIGHT, servico="Curso Premium", nome="Fora Da Planilha")])
    assert "o aluno não está na planilha" in ocorrencias(outro, TipoOcorrencia.PROGRAMA_FALTANDO_NA_PLANILHA)[0].mensagem


def test_transfer_sem_programa_e_erro(db, cenario):
    importacao = importar([item(2, "7040", "666", "902", FLIGHT, servico="Transfer (chegada e saída)")])
    assert ocorrencias(importacao, TipoOcorrencia.PROGRAMA_FALTANDO_NA_PLANILHA)


def test_transfer_de_aluno_com_programa_e_juntado(db, cenario):
    importar([item(2, "7041", "667", "600", FLIGHT, servico="Transfer (chegada e saída)", consultor="Consultor Dois")])
    assert tarefa(db, "7041").programa.programa_id_egali == "2000"


def test_servico_ignorado_e_pulado_sem_aviso(db, cenario):
    importacao = importar([item(2, "7050", "777", "903", FLIGHT, servico="Valores Extras")])
    assert importacao.resumo["itens_ignorados"] == 1
    assert importacao.resumo["erros"] == 0 and importacao.resumo["avisos"] == 0


def test_servico_desconhecido_entra_como_nao_classificado(db, cenario):
    importacao = importar([item(2, "7060", "888", "904", FLIGHT, servico="Serviço Inventado")])
    assert ocorrencias(importacao, TipoOcorrencia.SERVICO_NAO_CLASSIFICADO)
    servico = db.session.execute(db.select(ServicoEgali).filter_by(nome="Serviço Inventado")).scalar_one()
    assert servico.categoria == CategoriaServico.NAO_CLASSIFICADO


def test_compra_ja_na_planilha_nao_depende_do_servico(db, cenario):
    # A compra 100 está na planilha: mesmo com serviço "ignorado" no CSV, o item entra.
    importar([item(2, "7070", "100", "500", FLIGHT, servico="Valores Extras")])
    assert tarefa(db, "7070").programa.programa_id_egali == "1000"


def test_aluno_com_dois_programas_pede_decisao(db, cenario):
    base([linha_base(2, "1000", "500", "100, 101", nome="Ana Teste"),
          linha_base(3, "2000", "600", "200", consultor="Consultor Dois", nome="Bruno Teste", pt_prog=90.0),
          linha_base(4, "1001", "500", "102", nome="Ana Teste")])
    importacao = importar([item(2, "7080", "999", "500", COPIA_VISTO, servico="Visto - Canadá")])
    assert ocorrencias(importacao, TipoOcorrencia.ALUNO_COM_VARIOS_PROGRAMAS)
    assert db.session.query(Tarefa).count() == 0


# ---------------------------------------------------------------- conferências


def test_divergencia_de_aluno_nao_importa(db, cenario):
    importacao = importar([item(2, "7090", "100", "123456")])
    assert ocorrencias(importacao, TipoOcorrencia.DIVERGENCIA_ALUNO)[0].gravidade == Gravidade.ERRO
    assert db.session.query(Tarefa).count() == 0


def test_consultor_diferente_da_planilha_gera_um_aviso_agrupado(db, cenario):
    importacao = importar([
        item(2, "7101", "100", "500", consultor="Consultor Dois"),
        item(3, "7102", "101", "500", COPIA_VISTO, consultor="Consultor Dois"),
    ])
    avisos = ocorrencias(importacao, TipoOcorrencia.CONSULTOR_DIVERGENTE)
    assert len(avisos) == 1 and "2 item(ns)" in avisos[0].mensagem
    assert tarefa(db, "7101").responsavel is cenario["dois"]  # prevalece o do checklist


def test_consultor_do_checklist_e_preservado_contra_nova_base(db, cenario):
    importar([item(2, "7103", "100", "500", consultor="Consultor Dois")])
    programa = db.session.execute(db.select(Programa).filter_by(programa_id_egali="1000")).scalar_one()
    assert programa.consultor is cenario["dois"]

    base([linha_base(2, "1000", "500", "100, 101", consultor="Consultora Um")])
    db.session.refresh(programa)
    assert programa.consultor is cenario["dois"]


def test_vip_abaixo_de_85_e_sinalizado(db, cenario):
    importacao = importar([item(2, "7110", "100", "500", VIP), item(3, "7111", "200", "600", VIP, consultor="Consultor Dois")])
    avisos = ocorrencias(importacao, TipoOcorrencia.VIP_ABAIXO_DA_PONTUACAO)
    assert len(avisos) == 1  # só o programa 1000 (71 pontos); o 2000 tem 90
    assert "1000" in avisos[0].mensagem


def test_procedimento_novo_entra_no_catalogo(db, cenario):
    novo = "SA - GERAL - Procedimento que ainda não existia"
    importacao = importar([item(2, "7120", "100", "500", novo)])
    assert importacao.resumo["etapas_criadas"] == 1
    assert ocorrencias(importacao, TipoOcorrencia.PROCEDIMENTO_NOVO)
    etapa = tarefa(db, "7120").etapa
    assert etapa.criada_automaticamente and etapa.trilha.codigo == "GERAL"
    assert etapa.nome == "Procedimento que ainda não existia"
    assert importar([item(2, "7120", "100", "500", novo)]).resumo["etapas_criadas"] == 0
    assert db.session.query(EtapaModelo).filter_by(criada_automaticamente=True).count() == 1


def test_procedimento_novo_do_canada_entra_em_vistos(db, cenario):
    importar([item(2, "7121", "101", "500", "SA - CAN - Procedimento novo do Canadá", servico="Visto - Canadá")])
    assert tarefa(db, "7121").etapa.trilha.codigo == "VISTOS"
    assert db.session.execute(db.select(Trilha).filter_by(codigo="CAN")).scalar_one_or_none() is None


def test_onboarding_ct_e_longa_conta_como_vip(db, cenario):
    # Quem tem esse procedimento é VIP: com menos de 85 pontos, a importação avisa para corrigir.
    importacao = importar([item(2, "7122", "100", "500", "SA - GERAL - Realização de Onboarding com novos alunos (CT e Longa)")])
    assert tarefa(db, "7122").etapa.trilha.codigo == "VIP"
    assert ocorrencias(importacao, TipoOcorrencia.VIP_ABAIXO_DA_PONTUACAO)


def test_procedimento_fora_do_formato_e_erro(db, cenario):
    importacao = importar([item(2, "7130", "100", "500", "Procedimento sem prefixo")])
    assert ocorrencias(importacao, TipoOcorrencia.LINHA_INVALIDA)
    assert db.session.query(Tarefa).count() == 0


def test_procedimento_antigo_do_ppt_encontra_a_etapa(db, cenario):
    importar([item(2, "7140", "100", "500", "SA - CAN – Verificar status da aplicação do visto")])
    assert tarefa(db, "7140").etapa.texto_egali == "SA - CAN - Verificar status da aplicação do visto"


# ---------------------------------------------------------------- linhas com problema


def test_linhas_com_problema(db, cenario):
    importacao = importar([
        item(2, "", "100", "500"),
        item(3, "7150", "", "500"),
        item(4, "7151", "100", ""),
        item(5, "7001", "100", "500"),
        item(6, "7001", "100", "500"),
        item(7, "7152", "100", "500", data="amanhã"),
        {"linha": 8, "valores": {"#": "", "id da compra": "", "id aluno": "", "procedimento": "", "data": "", "status": ""}},
    ])
    tipos = sorted((o.linha, o.gravidade.value) for o in importacao.ocorrencias)
    assert tipos == [(2, "erro"), (3, "erro"), (4, "erro"), (6, "erro"), (7, "aviso")]
    assert importacao.resumo["linhas_sem_dados_ignoradas"] == 1
    assert tarefa(db, "7152").prazo_egali is None


def test_checklist_antes_da_planilha_e_recusado(db):
    carregar_catalogo()
    with pytest.raises(ErroImportacao, match="Importe primeiro a planilha"):
        checklist.criar_previa(CHECKLIST)
    assert db.session.query(Programa).count() == 0


def test_aviso_quando_a_planilha_e_antiga(db, cenario):
    from datetime import datetime, timedelta, timezone

    from app.models import Importacao, TipoImportacao

    ultima_base = db.session.execute(db.select(Importacao).filter_by(tipo=TipoImportacao.BASE_ALUNOS)).scalars().first()
    ultima_base.concluida_em = datetime.now(timezone.utc) - timedelta(days=12)
    db.session.commit()
    importacao = checklist.criar_previa(CHECKLIST)
    avisos = [o for o in importacao.ocorrencias if "há 12 dias" in o.mensagem]
    assert len(avisos) == 1 and importacao.resumo["avisos"] >= 1

    ultima_base.concluida_em = datetime.now(timezone.utc) - timedelta(days=2)
    db.session.commit()
    assert not [o for o in checklist.criar_previa(CHECKLIST).ocorrencias if "dias" in o.mensagem and "planilha" in o.mensagem]


def test_arquivo_sem_coluna_obrigatoria(db, cenario):
    linha = item(2, "1", "100", "500")
    del linha["valores"]["id da compra"]
    with pytest.raises(ErroImportacao, match="id da compra"):
        checklist.criar_previa([linha])


# ---------------------------------------------------------------- leitura do CSV


def test_leitor_csv_cp1252_e_cabecalho_com_espacos():
    texto = "#;Id da Compra;NEG;ID Aluno;Aluno ;Procedimento ;Data ;Serviço\r\n" \
            "7298439;6763545;17/09 - sem cognito;2178959;Aluno Fictício ;SA - VISTOS - Documentação OK ? Envio;01/10/2026;Visto - Canadá\r\n" \
            ";;;;;;;\r\n"
    linhas = ler_texto_csv(decodificar(texto.encode("cp1252")))
    assert len(linhas) == 1
    v = linhas[0]["valores"]
    assert linhas[0]["linha"] == 2
    assert v["aluno"] == "Aluno Fictício "
    assert v["procedimento"] == "SA - VISTOS - Documentação OK ? Envio"
    assert v["serviço"] == "Visto - Canadá"


def test_leitor_csv_aceita_utf8():
    assert decodificar("Serviço".encode("utf-8-sig")) == "Serviço"
    assert decodificar("Serviço".encode("cp1252")) == "Serviço"
