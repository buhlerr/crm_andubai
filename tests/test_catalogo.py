import pytest

from app.catalogo_inicial import ETAPAS, buscar_etapa_por_texto, carregar_catalogo, nome_da_etapa
from app.models import CategoriaServico, EtapaModelo, ServicoEgali, Trilha

# Todos os procedimentos distintos da exportação checklistServicoNew.csv de set/2026.
PROCEDIMENTOS_CSV = [
    "SA - GERAL - Realizar contato de relacionamento pré - embarque",
    "SA - GERAL - Cadastrar flight details",
    "SA - EUA - Solicitar cognito, analisar perfil e enviar rascunho do DS-160",
    "SA - GERAL - Ter a cópia do passaporte do aluno",
    "SA - VISTOS - Ter uma cópia do visto/negativa",
    "SA - VISTOS - Documentação OK ? Envio para embaixada/consulado",
    "SA - VISTOS - Entrega da 1a documentação e envio de chamado com pendências de documentação/Solicitar LOA (CAD)",
    "SA - EUA - Ter uma cópia do visto/negativa",
    "SA - EUA - Ligação de instrução pré entrevista EUA",
    "SA - EUA - Documentação OK - Confirmar envio de I-20, Sevis, documentos para entrevista, conferir endereço e número do DS-160",
    "SA - GERAL - Realização de Onboarding com novos alunos (pacotes)",
    "SA - GERAL - Ter cópia da autorização de viagem de menor de idade (nacional e internacional)",
    "SA - EUA - Solicitar LOA para visto",
    "SA - EUA - Finalizar DS-160 e criar conta de agendamento",
    "SA - VISTOS - Preencher os formulários de imigração (Immi / GCKey) e verificar envio das traduções (Canadá).",
    "SA - VISTOS - Ter a primeira versão da carta de intenções/GS form e formulário de visto preenchido",
    "SA - GERAL - Realizar contato de relacionamento pós embarque (pré NPS)",
    "SA - CAN - Verificar status da aplicação do visto",
    "SA - EUA - Agendamento do aluno",
    "SA - VIP - Primeiro contato de relacionamento com aluno",
    "SA - EAU - Ter confirmação de realização de teste de nivelamento",
    "SA - CAN - Garantir biometria agendada do aluno",
    "SA - GERAL - Ter a confirmação de vacina internacional de febre amarela",
    "SA - GERAL - Organizar documentos para orçamento de tradução",
    "SA - EUA - Agendar retirada de passaporte no CASV",
    "SA - EAU - Ter foto 3x4, foto da assinatura e declaração de visto assinada",
    "SA - CAN - Agendar consultoria com a Base - Canadá Leap",
    "SA - GERAL - Realização de Onboarding com novos alunos (CT e Longa)",
    "SA - EUA - Ter docs para emissão do I-20",
    "SA - EUA - Pagar a SEVIS e anexar na AA",
    "SA - CAN - Ter custodianship assinado",
    "SA - CAN - Confirmar envio do passaporte após aprovação",
    # Exportação de 29/09/2026.
    "SA - CAN - Conferir additional documents e enviar para o consulado",
    "SA - GERAL - Ter confirmação de realização do teste de nivelamento (requisito para embarque)",
    "SA - GERAL - Ter confirmação de realização do teste de nivelamento (requisito para invoice)",
    "SA - ON - Contact student who didn`t login after enrolment",
]


def test_carrega_trilhas_e_etapas(db):
    carregar_catalogo()
    assert [t.codigo for t in db.session.execute(db.select(Trilha).order_by(Trilha.ordem)).scalars()] == [
        "GERAL", "VISTOS", "EUA", "EAU", "VIP", "ON",
    ]
    assert db.session.query(EtapaModelo).count() == sum(len(v) for v in ETAPAS.values()) == 37


def nomes_da_trilha(db, codigo):
    trilha = db.session.execute(db.select(Trilha).filter_by(codigo=codigo)).scalar_one()
    return [e.nome for e in sorted(trilha.etapas, key=lambda e: e.ordem)]


def test_organizacao_decidida_pela_equipe(db):
    carregar_catalogo()
    assert nomes_da_trilha(db, "VIP") == [
        "Primeiro contato de relacionamento com aluno",
        "Realização de Onboarding com novos alunos (CT e Longa)",
        "Agendar consultoria com a Base - Canadá Leap",
    ]
    assert nomes_da_trilha(db, "ON") == [
        "Realização de Onboarding com novos alunos (pacotes)",
        "Contact student who didn`t login after enrolment",
    ]
    vistos = nomes_da_trilha(db, "VISTOS")
    assert len(vistos) == 12
    assert vistos[0].startswith("Realizar a aplicação do CAQ") and vistos[-1] == "Ter uma cópia do visto/negativa"
    assert "Garantir biometria agendada do aluno" in vistos
    assert db.session.execute(db.select(Trilha).filter_by(codigo="VISTOS")).scalar_one().nome == "Vistos / Canadá"
    assert not any("Onboarding" in n for n in nomes_da_trilha(db, "GERAL"))


def _voltar_para_a_organizacao_antiga(db):
    """Monta um catálogo como o de antes de 29/09/2026: trilha CAN separada, onboardings em GERAL."""
    trilhas = {t.codigo: t for t in db.session.execute(db.select(Trilha)).scalars()}
    can = Trilha(codigo="CAN", nome="Canadá", ordem=3)
    db.session.add(can)
    trilhas["VISTOS"].nome = "Vistos"
    for etapa in list(trilhas["VISTOS"].etapas) + list(trilhas["VIP"].etapas):
        if etapa.texto_egali.startswith("SA - CAN - "):
            etapa.trilha = can
    for texto in ("SA - GERAL - Realização de Onboarding com novos alunos (CT e Longa)",
                  "SA - GERAL - Realização de Onboarding com novos alunos (pacotes)",
                  "SA - GERAL - Organizar documentos para orçamento de tradução"):
        buscar_etapa_por_texto(texto).trilha = trilhas["GERAL"]
    # Como era: numeradas a partir de 1 dentro de cada trilha antiga.
    buscar_etapa_por_texto("SA - ON - Contact student who didn`t login after enrolment").ordem = 1
    buscar_etapa_por_texto("SA - VIP - Primeiro contato de relacionamento com aluno").ordem = 1
    db.session.commit()


def test_banco_antigo_e_reorganizado_uma_vez(db):
    carregar_catalogo()
    _voltar_para_a_organizacao_antiga(db)
    assert len(nomes_da_trilha(db, "CAN")) == 7

    contagem = carregar_catalogo()
    assert contagem["trilhas_mescladas"] == 1 and contagem["reorganizadas"] >= 3
    assert db.session.execute(db.select(Trilha).filter_by(codigo="CAN")).scalar_one_or_none() is None
    assert len(nomes_da_trilha(db, "VISTOS")) == 12
    assert "Realização de Onboarding com novos alunos (CT e Longa)" in nomes_da_trilha(db, "VIP")
    assert "Agendar consultoria com a Base - Canadá Leap" in nomes_da_trilha(db, "VIP")
    assert "Realização de Onboarding com novos alunos (pacotes)" in nomes_da_trilha(db, "ON")
    assert db.session.execute(db.select(Trilha).filter_by(codigo="VISTOS")).scalar_one().nome == "Vistos / Canadá"
    # Cada trilha reorganizada fica com a ordem definida, sem posições repetidas.
    for codigo in ("VISTOS", "VIP", "ON"):
        trilha = db.session.execute(db.select(Trilha).filter_by(codigo=codigo)).scalar_one()
        ordens = [e.ordem for e in trilha.etapas]
        assert len(ordens) == len(set(ordens)), codigo
    assert nomes_da_trilha(db, "ON") == [
        "Realização de Onboarding com novos alunos (pacotes)",
        "Contact student who didn`t login after enrolment",
    ]
    segunda = carregar_catalogo()
    assert segunda["reorganizadas"] == 0 and segunda["trilhas_mescladas"] == 0


def test_orcamento_de_traducao_fica_em_vistos_depois_da_primeira_documentacao(db):
    carregar_catalogo()
    vistos = nomes_da_trilha(db, "VISTOS")
    i = vistos.index("Organizar documentos para orçamento de tradução")
    assert vistos[i - 1].startswith("Entrega da 1a documentação")
    assert vistos[i + 1].startswith("Preencher os formulários de imigração")
    assert "Organizar documentos para orçamento de tradução" not in nomes_da_trilha(db, "GERAL")


def test_banco_ja_reorganizado_recebe_so_a_mudanca_nova(db):
    # Como o banco que já tinha passado pela primeira reorganização: só o orçamento de tradução ainda em GERAL.
    carregar_catalogo()
    trilhas = {t.codigo: t for t in db.session.execute(db.select(Trilha)).scalars()}
    traducao = buscar_etapa_por_texto("SA - GERAL - Organizar documentos para orçamento de tradução")
    traducao.trilha, traducao.ordem = trilhas["GERAL"], 4
    for i, etapa in enumerate(sorted(trilhas["VISTOS"].etapas, key=lambda e: e.ordem), start=1):
        if etapa is not traducao:
            etapa.ordem = i
    db.session.commit()

    contagem = carregar_catalogo()
    assert contagem["reorganizadas"] == 1 and contagem["trilhas_mescladas"] == 0
    assert traducao.trilha.codigo == "VISTOS"
    ordens = [e.ordem for e in trilhas["VISTOS"].etapas]
    assert len(ordens) == len(set(ordens)) == 12
    assert nomes_da_trilha(db, "VISTOS")[3] == "Organizar documentos para orçamento de tradução"


def test_reorganizacao_respeita_o_que_foi_mudado_pela_tela(db):
    carregar_catalogo()
    _voltar_para_a_organizacao_antiga(db)
    trilhas = {t.codigo: t for t in db.session.execute(db.select(Trilha)).scalars()}
    onboarding = buscar_etapa_por_texto("SA - GERAL - Realização de Onboarding com novos alunos (pacotes)")
    onboarding.trilha = trilhas["EAU"]  # alguém moveu pela tela
    trilhas["VISTOS"].nome = "Vistos Canadá e Austrália"  # e renomeou
    db.session.commit()
    carregar_catalogo()
    assert onboarding.trilha.codigo == "EAU"
    assert trilhas["VISTOS"].nome == "Vistos Canadá e Austrália"


def test_tarefas_acompanham_a_etapa_que_mudou_de_trilha(db):
    from app.models import Aluno, Programa, Tarefa

    carregar_catalogo()
    _voltar_para_a_organizacao_antiga(db)
    etapa = buscar_etapa_por_texto("SA - CAN - Garantir biometria agendada do aluno")
    aluno = Aluno(aluno_id_egali="1", nome="Aluno Fictício")
    db.session.add(Tarefa(item_checklist_egali="1", programa=Programa(programa_id_egali="1", aluno=aluno), etapa=etapa))
    db.session.commit()
    carregar_catalogo()
    tarefa = db.session.execute(db.select(Tarefa)).scalar_one()
    assert tarefa.etapa.trilha.codigo == "VISTOS"


def test_trilha_on_e_primeiro_contato(db):
    carregar_catalogo()
    assert db.session.execute(db.select(Trilha).filter_by(codigo="ON")).scalar_one().nome == "Primeiro contato"


def test_carga_da_nome_a_trilha_provisoria_mas_respeita_nome_editado(db):
    carregar_catalogo()
    trilhas = {t.codigo: t for t in db.session.execute(db.select(Trilha)).scalars()}
    trilhas["ON"].nome = "ON"  # banco antigo, nome provisório
    trilhas["EAU"].nome = "Dubai"  # editado pela interface
    db.session.commit()
    carregar_catalogo()
    assert trilhas["ON"].nome == "Primeiro contato"
    assert trilhas["EAU"].nome == "Dubai"


def test_segunda_carga_nao_duplica(db):
    carregar_catalogo()
    assert carregar_catalogo() == {"trilhas": 0, "etapas": 0, "apelidos": 0, "servicos": 0, "reorganizadas": 0, "trilhas_mescladas": 0}
    assert db.session.query(EtapaModelo).count() == 37


def test_segunda_carga_nao_sobrescreve_edicao(db):
    carregar_catalogo()
    etapa = buscar_etapa_por_texto("SA - GERAL - Cadastrar flight details")
    etapa.regra_prazo = "Editado pela equipe"
    db.session.commit()
    carregar_catalogo()
    assert buscar_etapa_por_texto("SA - GERAL - Cadastrar flight details").regra_prazo == "Editado pela equipe"


@pytest.mark.parametrize("texto", PROCEDIMENTOS_CSV)
def test_todo_procedimento_do_csv_tem_etapa(db, texto):
    carregar_catalogo()
    from app.catalogo_inicial import MUDANCAS_DE_TRILHA, trilha_do_codigo

    etapa = buscar_etapa_por_texto(texto)
    assert etapa is not None
    esperada = MUDANCAS_DE_TRILHA.get(texto, (None, trilha_do_codigo(texto.split(" - ")[1])))[1]
    assert etapa.trilha.codigo == esperada


@pytest.mark.parametrize(
    ("texto_ppt", "texto_csv"),
    [
        ("SA - VISTOS - Solicitar LOA (EUA)", "SA - EUA - Solicitar LOA para visto"),
        ("SA - CAN - Enviar Custodianship para o consulado via Web Form", "SA - CAN - Ter custodianship assinado"),
        ("SA - VISTOS - Documentação OK - Envio para a embaixada/consulado",
         "SA - VISTOS - Documentação OK ? Envio para embaixada/consulado"),
        ("SA - EUA - Finalizar DS 160 (Enviar Declaração EUA/Cronograma CAD)",
         "SA - EUA - Finalizar DS-160 e criar conta de agendamento"),
        ("SA - EUA - Agendamento do aluno - Visto EUA", "SA - EUA - Agendamento do aluno"),
        ("SA - CAN – Verificar status da aplicação do visto", "SA - CAN - Verificar status da aplicação do visto"),
        ("SA - ON - Contact student who didn't login after enrolment",
         "SA - ON - Contact student who didn`t login after enrolment"),
    ],
)
def test_nome_antigo_do_ppt_aponta_para_a_mesma_etapa(db, texto_ppt, texto_csv):
    carregar_catalogo()
    assert buscar_etapa_por_texto(texto_ppt).id == buscar_etapa_por_texto(texto_csv).id


def test_sequencia_ds160_sao_tres_etapas_distintas(db):
    carregar_catalogo()
    ids = {
        buscar_etapa_por_texto(t).id
        for t in [
            "SA - EUA - Solicitar cognito, analisar perfil e enviar rascunho do DS-160",
            "SA - EUA - Finalizar DS-160 e criar conta de agendamento",
            "SA - EUA - Agendamento do aluno",
        ]
    }
    assert len(ids) == 3


def test_servicos_classificados(db):
    carregar_catalogo()
    categorias = {s.nome: s.categoria for s in db.session.execute(db.select(ServicoEgali)).scalars()}
    assert categorias["Summer Schools"] == CategoriaServico.CURSO
    assert categorias["Grupo Premium"] == CategoriaServico.CURSO
    assert categorias["Visto - Canadá - eTA"] == CategoriaServico.VISTO
    assert categorias["Transfer (chegada e saída)"] == CategoriaServico.AVULSO
    assert categorias["Canada Leap"] == CategoriaServico.CURSO
    assert categorias["Curso + Trabalho Canadá"] == CategoriaServico.CURSO
    assert categorias["C. Curso"] == CategoriaServico.IGNORADO
    assert CategoriaServico.NAO_CLASSIFICADO not in categorias.values()


def test_carga_classifica_servico_pendente_mas_respeita_decisao_da_equipe(db):
    carregar_catalogo()
    servicos = {s.nome: s for s in db.session.execute(db.select(ServicoEgali)).scalars()}
    servicos["Canada Leap"].categoria = CategoriaServico.NAO_CLASSIFICADO  # banco antigo, ainda sem decisão
    servicos["Seguro Viagem"].categoria = CategoriaServico.IGNORADO  # decisão tomada pela interface
    db.session.commit()
    carregar_catalogo()
    assert servicos["Canada Leap"].categoria == CategoriaServico.CURSO
    assert servicos["Seguro Viagem"].categoria == CategoriaServico.IGNORADO


def test_nome_da_etapa():
    assert nome_da_etapa("SA - CAN - Agendar consultoria com a Base - Canadá Leap") == (
        "Agendar consultoria com a Base - Canadá Leap"
    )
