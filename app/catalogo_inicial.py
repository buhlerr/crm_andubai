"""Carga inicial do catálogo: trilhas, etapas e classificação de serviços.

Fontes: os textos de procedimento do checklistServicoNew.csv (texto principal
de cada etapa, porque é por ele que a importação liga a tarefa à etapa) e o
PPT "Checklist S.A. - AN e Dubai" (orientações e nomes antigos, guardados
como apelidos).

Rodar mais de uma vez não duplica nada e não sobrescreve o que já foi
editado pela interface.
"""

from app.extensions import db
from app.models import ApelidoEtapa, CategoriaServico, EtapaModelo, ServicoEgali, Trilha
from app.texto import normalizar_texto

TRILHAS = [
    # (código, nome na interface)
    ("GERAL", "Geral"),
    ("VISTOS", "Vistos / Canadá"),
    ("EUA", "Estados Unidos"),
    ("EAU", "Dubai (EAU)"),
    ("VIP", "VIP"),
    ("ON", "Primeiro contato"),  # primeiro contato com o aluno, parecido com o onboarding
]

# ---------------------------------------------------------------- reorganização (decisão da equipe, 29/09/2026)
# O código no texto da Egali ("SA - CAN - ...") não precisa ser a trilha do catálogo:
# a tarefa acha a etapa pelo texto, e a etapa diz a trilha.

# Trilhas da Egali que no catálogo viraram parte de outra.
TRILHAS_MESCLADAS = {"CAN": "VISTOS"}

# Etapas que mudaram de trilha: texto do procedimento -> (trilha de antes, trilha nova).
MUDANCAS_DE_TRILHA = {
    "SA - GERAL - Realização de Onboarding com novos alunos (CT e Longa)": ("GERAL", "VIP"),
    "SA - CAN - Agendar consultoria com a Base - Canadá Leap": ("CAN", "VIP"),
    "SA - GERAL - Realização de Onboarding com novos alunos (pacotes)": ("GERAL", "ON"),
    "SA - GERAL - Organizar documentos para orçamento de tradução": ("GERAL", "VISTOS"),
}

# Ordem das trilhas que mudaram (as outras seguem a ordem da lista ETAPAS abaixo).
ORDEM_REORGANIZADA = {
    "VISTOS": [
        "SA - CAN - Realizar a aplicação do CAQ (conferir se DLI e carga horária (20h) estão de acordo)",
        "SA - VISTOS - Ter a primeira versão da carta de intenções/GS form e formulário de visto preenchido",
        "SA - VISTOS - Entrega da 1a documentação e envio de chamado com pendências de documentação/Solicitar LOA (CAD)",
        "SA - GERAL - Organizar documentos para orçamento de tradução",
        "SA - VISTOS - Preencher os formulários de imigração (Immi / GCKey) e verificar envio das traduções (Canadá).",
        "SA - VISTOS - Documentação OK ? Envio para embaixada/consulado",
        "SA - CAN - Ter custodianship assinado",
        "SA - CAN - Garantir biometria agendada do aluno",
        "SA - CAN - Conferir additional documents e enviar para o consulado",
        "SA - CAN - Verificar status da aplicação do visto",
        "SA - CAN - Confirmar envio do passaporte após aprovação",
        "SA - VISTOS - Ter uma cópia do visto/negativa",
    ],
    "VIP": [
        "SA - VIP - Primeiro contato de relacionamento com aluno",
        "SA - GERAL - Realização de Onboarding com novos alunos (CT e Longa)",
        "SA - CAN - Agendar consultoria com a Base - Canadá Leap",
    ],
    "ON": [
        "SA - GERAL - Realização de Onboarding com novos alunos (pacotes)",
        "SA - ON - Contact student who didn`t login after enrolment",
    ],
}
NOMES_ANTIGOS_DAS_TRILHAS = {"VISTOS": "Vistos"}  # renomeia só se ninguém mudou o nome pela tela


def trilha_do_codigo(codigo: str) -> str:
    """Código da Egali ("CAN") -> código da trilha no catálogo ("VISTOS")."""
    return TRILHAS_MESCLADAS.get(codigo, codigo)


def _etapa(texto, regra_prazo=None, o_que_e=None, importancia=None, neg=None, link=None, apelidos=()):
    return {
        "texto_egali": texto,
        "regra_prazo": regra_prazo,
        "o_que_e": o_que_e,
        "importancia": importancia,
        "quando_cabe_neg": neg,
        "link_gravacao": link,
        "apelidos": list(apelidos),
    }


_SP = "https://egali.sharepoint.com/:v:/s/Egali-AC/"

# Etapas agrupadas pelo código que aparece no texto da Egali. A organização final do
# catálogo (ETAPAS, mais abaixo) aplica a reorganização acima sobre esta lista.
_ETAPAS_POR_CODIGO_EGALI = {
    "GERAL": [
        _etapa("SA - GERAL - Realização de Onboarding com novos alunos (pacotes)"),
        _etapa("SA - GERAL - Realização de Onboarding com novos alunos (CT e Longa)"),
        _etapa(
            "SA - GERAL - Ter a cópia do passaporte do aluno",
            regra_prazo="Não definido no PPT (\"??\").",
            o_que_e="Ter a cópia das páginas 2 e 3 do passaporte.",
            importancia="Emissão dos documentos corretos.\nVerificar validade.",
            neg="Agendado na Polícia Federal.\nSe sem visto, 90 dias antes do embarque.",
            link=_SP + "EUNFOy9GOOZHluVZQSQ3f2sB_KNDm8d17l0IxjQ9HTDmKg?e=g0hL3y",
        ),
        _etapa("SA - GERAL - Organizar documentos para orçamento de tradução"),
        _etapa(
            "SA - GERAL - Cadastrar flight details",
            regra_prazo="30 ou 60 dias antes do embarque.",
            o_que_e="Cadastrar a passagem aérea completa do aluno.",
            importancia="Conferir se está de acordo com as datas de acomodação e cidades corretas.\n"
            "Informar ao transfer.\nConfirmação de que vai embarcar.",
            neg="Aguardando retorno do visto.\nMais de 30 dias do embarque.",
            link=_SP + "EaXDFZMw5QNFrTMa6jELJa0BJ6Dmh6MHS5_xS-Ukmt3bfQ?e=ooBjvS",
        ),
        _etapa(
            "SA - GERAL - Ter cópia da autorização de viagem de menor de idade (nacional e internacional)",
            regra_prazo="45 dias antes do embarque.",
            o_que_e="Necessário para o embarque do aluno caso não tenha no passaporte.\n"
            "Sempre conferir a idade, para saber se precisa da nacional.",
            importancia="Muita atenção sempre.",
            neg="Não tem NEG.",
            link=_SP + "EUfD54pbQY5NpSGicwBg5nkB3a1edfyIXalMa42F_1azAA?e=UJRP3y",
        ),
        _etapa("SA - GERAL - Ter a confirmação de vacina internacional de febre amarela"),
        # Apareceram na exportação de 29/09/2026; não estão no PPT.
        _etapa("SA - GERAL - Ter confirmação de realização do teste de nivelamento (requisito para embarque)"),
        _etapa("SA - GERAL - Ter confirmação de realização do teste de nivelamento (requisito para invoice)"),
        _etapa(
            "SA - GERAL - Realizar contato de relacionamento pré - embarque",
            regra_prazo="10 dias antes do embarque.",
            o_que_e="Verificar se o aluno está preparado para a viagem.\nSe assistiu à OPE.",
            importancia="Reforçar a lista de documentos.\nEsclarecer as últimas dúvidas do intercambista.",
            neg="Sem NEG.",
            link=_SP + "EfBEEIVH2hFFljGmsXp6TXsBkAJ7fZmLVnQWhkeLNJeZoQ?e=x2RVSo",
            apelidos=["SA - GERAL - Realizar contato de relacionamento pré-embarque"],
        ),
        _etapa(
            "SA - GERAL - Realizar contato de relacionamento pós embarque (pré NPS)",
            regra_prazo="3 dias depois do embarque (só destinos sem base).",
            o_que_e="Garantir que foi tudo certo na chegada do aluno.",
            importancia="Contato ativo com o aluno.\nResolver se teve algum problema.",
            neg="Sem NEG.",
            link=_SP + "EY5T365o5jtDpd1XCp1KtWQBrdkg01qwHDwVZg99eECFFg?e=dkKmhi",
        ),
    ],
    "VISTOS": [
        _etapa(
            "SA - VISTOS - Ter a primeira versão da carta de intenções/GS form e formulário de visto preenchido",
            regra_prazo="148 dias antes do embarque.",
            o_que_e="Conferir carta de intenções e formulários.",
            importancia="Fazer com antecedência e garantir que terá tudo certo para a aplicação.\n"
            "Informações necessárias e corretas para a aplicação.",
            neg="Sem NEG.",
            link=_SP + "Efrq23oURPJHjbA3wQ-log8BC3nWJa5p_K2_VvDimq5qMQ?e=142EwD",
        ),
        _etapa(
            "SA - VISTOS - Entrega da 1a documentação e envio de chamado com pendências de documentação/Solicitar LOA (CAD)",
            regra_prazo="eTA: 60 dias do embarque.\nCAD: 141 dias do embarque.",
            o_que_e="Garantir que os documentos sejam enviados dentro do prazo.\n"
            "Lembrete dos documentos pendentes.\nLOA CAD.",
            importancia="Ter, dentro do prazo de aplicação, os documentos certos.",
            neg="Se eTA, passaporte do visto EUA ainda não chegou.\n"
            "Já verificar aqui os documentos que precisam ser traduzidos.",
            link=_SP + "EY4lfMw9LkZMgqLBjruikW0BQ72H5V-K2ZtxQjxAKLIJAg?e=EXDSiN",
        ),
        _etapa(
            "SA - VISTOS - Preencher os formulários de imigração (Immi / GCKey) e verificar envio das traduções (Canadá).",
            regra_prazo="113 dias da data de embarque.",
            o_que_e="Rascunhar a aplicação.\nConferir documentos da aplicação e preencher formulários.\n"
            "Criar a conta no consulado.",
            importancia="Garantir que no prazo da aplicação conseguiremos realizar.",
            neg="Documentos ainda com traduções.",
            link=_SP + "Efrq23oURPJHjbA3wQ-log8BC3nWJa5p_K2_VvDimq5qMQ?e=142EwD",
        ),
        _etapa(
            "SA - VISTOS - Documentação OK ? Envio para embaixada/consulado",
            regra_prazo="eTA: 30 dias do embarque.\nCAD: 120 dias do embarque.",
            o_que_e="Finalizar o procedimento de visto.",
            importancia="Aplicar com atenção e no prazo para o aluno embarcar a tempo.",
            neg="Se eTA, passaporte do visto EUA ainda não chegou.\nDocumentos com tradução.\n"
            "Se tiver ok do aluno de que pode atrasar.\nSe falta PAL.",
            link=_SP + "Efrq23oURPJHjbA3wQ-log8BC3nWJa5p_K2_VvDimq5qMQ?e=142EwD",
            apelidos=["SA - VISTOS - Documentação OK - Envio para a embaixada/consulado"],
        ),
        _etapa(
            "SA - VISTOS - Ter uma cópia do visto/negativa",
            regra_prazo="15 dias antes do embarque.",
            o_que_e="Anexar a cópia do visto.",
            importancia="Métricas internas.\nAcompanhamento de cada aluno.",
            neg="Se o visto não saiu.",
            link=_SP + "EceF_IRYbKRFmWZ54rBbXuEB_N5R4ysUeux_BmD6lrbgig?e=trP0wD",
        ),
    ],
    "CAN": [
        _etapa(
            "SA - CAN - Realizar a aplicação do CAQ (conferir se DLI e carga horária (20h) estão de acordo)",
            regra_prazo="165 dias da data de embarque.",
            o_que_e="Realizar a aplicação do CAQ com os devidos cuidados.",
            importancia="Realizar dentro do prazo para garantir que consiga embarcar.",
            neg="Falta LOA.",
            link=_SP + "Ec4LV8CA33ZAgL34h4K0qcUBtJOoj9bjmIIQzT9jfqZUZg?e=SCcMn2",
        ),
        _etapa("SA - CAN - Agendar consultoria com a Base - Canadá Leap"),
        _etapa(
            "SA - CAN - Ter custodianship assinado",
            regra_prazo="7 dias depois de finalizar a doc ok.",
            o_que_e="Garantir que o documento seja enviado no prazo.",
            importancia="Se não realizar, o visto pode ser negado.",
            neg="Apenas se estiver aguardando assinatura da escola.\nAguardando aluno preencher.",
            link=_SP + "EdgWnzFuP4VHmE2Sv1dzzAABn8GVinBk0bNpGCZ5KnY1aA?e=F8kyLd",
            apelidos=["SA - CAN - Enviar Custodianship para o consulado via Web Form"],
        ),
        _etapa(
            "SA - CAN - Garantir biometria agendada do aluno",
            regra_prazo="7 dias depois da doc ok finalizada.",
            o_que_e="Garantir que o aluno faça a biometria.",
            importancia="Se não realizar em 30 dias, o visto pode ser negado.\n"
            "O processo de visto fica parado até ser feito.",
            neg="Informar a data que o aluno agendou.\nSó finalizar quando o aluno fizer de fato a biometria.",
            link=_SP + "Ebqdl0XbMblNu74jyfnMxPoB-nPGetFnnCeRbV1lOr6mTg?e=byLojz",
        ),
        _etapa(
            "SA - CAN - Conferir additional documents e enviar para o consulado",
            regra_prazo="5 dias da compra de additional documents.",
            o_que_e="Conferir os documentos extras solicitados pelo consulado.",
            importancia="Se não realizar, o visto pode ser negado.\nO processo de visto fica parado até ser feito.",
            neg="Se o aluno estiver pendente do documento.",
            link=_SP + "EdgWnzFuP4VHmE2Sv1dzzAABn8GVinBk0bNpGCZ5KnY1aA?e=F8kyLd",
        ),
        _etapa(
            "SA - CAN - Verificar status da aplicação do visto",
            regra_prazo="50 dias depois de finalizar a doc ok.",
            o_que_e="Verificar se teve alguma atualização do visto CAD.\nConferir direto no GCKey, no site.",
            importancia="O passaporte tem 30 dias para chegar no VFS, caso contrário o visto é negado.\n"
            "Informar o aluno do resultado.",
            neg="Aplicado em XXXX, conferido em XXXX, OBS (em análise / solicitado exames em XXXX – "
            "informado à aluna / solicitado exames em XXXX – aluno fez em XXXX – em análise).",
            link=_SP + "ESSI72X_VdVFlP9cDS20BoUB1K89lROrt5Jtii10Y7imSw?e=Vc71tT",
        ),
        _etapa("SA - CAN - Confirmar envio do passaporte após aprovação"),
    ],
    "EUA": [
        # Sequência: cognito -> finalizar DS-160 -> agendamento. Cada uma abre quando a anterior é finalizada.
        _etapa(
            "SA - EUA - Solicitar cognito, analisar perfil e enviar rascunho do DS-160",
            regra_prazo="10 meses antes do embarque.",
            o_que_e="Conhecer o perfil do aluno.\nCriar a conta de agendamento.",
            importancia="Saber desde o início o perfil do aluno e entender melhorias no processo de visto dele, "
            "se necessário.",
            neg="Sem passaporte.\nPerfil delicado.\nAguardando retorno do ok do aluno no DS.",
            link=_SP + "ERc4CNN5w1lHtR6xXw5YakkB0gcgmB-rdXAolm-WtmmqBQ?e=aaNuZp",
            apelidos=["SA - EUA - Solicitar Cognito, analisar perfil e Criar conta de agendamento - Visto EUA"],
        ),
        _etapa(
            "SA - EUA - Ter docs para emissão do I-20",
            regra_prazo="150 dias antes da data de embarque.",
            o_que_e="Garantir o envio dos documentos para emissão do I-20.",
            importancia="Garantir que tenha o I-20 a tempo da entrevista e do embarque.",
            neg="Sem retorno, mas com prazo até 130 dias antes do embarque.",
            link=_SP + "EfHEskjtIs5NoWAwJdM3bSEBzHX4F3Bu2sbdhAL4AuEvjg?e=Rgz3Yh",
        ),
        _etapa(
            "SA - EUA - Pagar a SEVIS e anexar na AA",
            regra_prazo="90 dias antes da data de embarque.",
            o_que_e="Pagar a taxa SEVIS.",
            importancia="Obrigatória para visto EUA de estudante.",
            neg="Atraso da escola.",
            link=_SP + "EXW1kTocDmJIg6yTKg5UmF0BJewbsKUh1zVxNdHJEWGq9Q?e=CEPHsY",
        ),
        _etapa(
            "SA - EUA - Solicitar LOA para visto",
            regra_prazo="15 dias antes do embarque.",
            o_que_e="Ter a LOA para quem vai fazer a entrevista e viajar para os EUA.",
            importancia="Levar a LOA na entrevista e mostrar mais confiança.",
            neg="Sem NEG.",
            apelidos=["SA - VISTOS - Solicitar LOA (EUA)"],
        ),
        _etapa(
            "SA - EUA - Finalizar DS-160 e criar conta de agendamento",
            regra_prazo="20 dias antes da entrevista.",
            o_que_e="Finalizar o formulário DS-160 para o aluno levar na entrevista.",
            importancia="Garantir que o aluno tenha esse documento correto para a entrevista.",
            neg="Trocou a data da entrevista.\nSe pediu alteração no DS.\nColocar a data da entrevista.",
            link=_SP + "EVxepU_xTiZChztFoY31SbUBoDIV0y5TGh9VUKIIaczegw?e=a2mh0Z",
            apelidos=["SA - EUA - Finalizar DS 160 (Enviar Declaração EUA/Cronograma CAD)"],
        ),
        _etapa(
            "SA - EUA - Agendamento do aluno",
            regra_prazo="2 dias depois de finalizar o procedimento anterior.",
            o_que_e="Realizar o agendamento do visto EUA do aluno.",
            importancia="Garantir uma data para o agendamento.",
            neg="Se a entrevista for a mais de 10 dias do procedimento.\nColocar a data das entrevistas.",
            link=_SP + "EUNYhkj01HpAiDVtGUZ4GosBlOrqVMQTpCUT8lRw6ddOwA?e=DjR6IB",
            apelidos=["SA - EUA - Agendamento do aluno - Visto EUA"],
        ),
        _etapa(
            "SA - EUA - Documentação OK - Confirmar envio de I-20, Sevis, documentos para entrevista, "
            "conferir endereço e número do DS-160",
            regra_prazo="15 dias antes da entrevista.",
            o_que_e="Conferir se toda a documentação está disponível e correta na AA para o aluno levar na entrevista.",
            importancia="Ter certeza de que não haverá nenhum documento incorreto para levar na entrevista.",
            neg="Trocou a data da entrevista.\nSe a entrevista for a mais de 10 dias do procedimento.\n"
            "Colocar a data das entrevistas.",
            link=_SP + "Ee7HLlzv-rZMmwkJsILiopwBk2M1yB9sE3Pz0woiNrgw7g?e=v3v7if",
        ),
        _etapa(
            "SA - EUA - Ligação de instrução pré entrevista EUA",
            regra_prazo="14 dias antes da entrevista.",
            o_que_e="Treinar e preparar o aluno para a entrevista.",
            importancia="Tirar todas as dúvidas e deixar o aluno tranquilo para o momento da entrevista.\n"
            "Se o aluno não atender: mandar recado e áudio no WhatsApp, descrever na NEG e CANCELAR o procedimento.",
            neg="Entrevista a mais de 7 dias.\nTrocou a data da entrevista.\nColocar a data da entrevista.",
            link=_SP + "EdF1rdfBeNxOlRqD5awoI6gBDvpAqdGH3i1-DU7AW5sd_A?e=iCbMEz",
        ),
        _etapa(
            "SA - EUA - Ter uma cópia do visto/negativa",
            regra_prazo="7 dias depois da entrevista.",
            o_que_e="Anexar uma cópia do visto aprovado/negado na AA.",
            importancia="Métricas internas.\nAcompanhamento de cada aluno.",
            neg="Trocou a data da entrevista.",
            link=_SP + "EXT8ne3mjfFEsqG3K_PyDOIBNQifPEGdX_ZfFSB0wbLC_w?e=9Olfao",
        ),
        _etapa(
            "SA - EUA - Agendar retirada de passaporte no CASV",
            regra_prazo="7 dias depois de finalizar a cópia do visto.",
            o_que_e="Garantir que o aluno vá retirar o passaporte com o visto EUA.",
            importancia="Não perder o prazo para pegar o passaporte.",
            neg="Sem NEG.",
        ),
    ],
    "EAU": [
        _etapa(
            "SA - EAU - Ter foto 3x4, foto da assinatura e declaração de visto assinada",
            regra_prazo="70 dias antes da data de embarque.\n"
            "CT: 84 dias antes (aumentar para 100 dias; tem recado automático).",
            o_que_e="A escola ter os documentos necessários para a aplicação do visto.",
            importancia="Chegar na escola sem pendências.",
            neg="Sem NEG.\nFoto indecente.",
            link=_SP + "EaToz5aEHjJBjuCLET1SAD0BC61T16juSCnekEUIn5cdSg?e=p0E6uz",
        ),
        _etapa(
            "SA - EAU - Ter confirmação de realização de teste de nivelamento",
            regra_prazo="30 dias antes da data de embarque.",
            o_que_e="Confirmar que o aluno faça o teste de nivelamento antes do primeiro dia de aula.",
            importancia="Chegar na escola sem pendências.",
            neg="Pode ser feito até 15 dias antes do embarque.",
            link=_SP + "Ebw7QgfPykdHnBqva69edvgBdbMhbxbJ_50dJEMlxcX4qw?e=TwrDH9",
        ),
    ],
    "VIP": [
        _etapa("SA - VIP - Primeiro contato de relacionamento com aluno"),
    ],
    "ON": [
        _etapa(
            "SA - ON - Contact student who didn`t login after enrolment",
            regra_prazo="7 dias da matrícula.",
            o_que_e="Informar ao aluno sobre a área do aluno.",
            importancia="Deixar o aluno ciente da AA, da necessidade e da importância dela.",
            neg="Não tem NEG.",
        ),
    ],
}

def _organizar_etapas() -> dict[str, list[dict]]:
    """Aplica mesclas, mudanças de trilha e a nova ordem sobre a lista agrupada pela Egali."""
    por_trilha: dict[str, list[dict]] = {codigo: [] for codigo, _ in TRILHAS}
    for codigo, etapas in _ETAPAS_POR_CODIGO_EGALI.items():
        for dados in etapas:
            destino = MUDANCAS_DE_TRILHA.get(dados["texto_egali"], (None, trilha_do_codigo(codigo)))[1]
            por_trilha[destino].append(dados)
    for codigo, ordem in ORDEM_REORGANIZADA.items():
        posicao = {texto: i for i, texto in enumerate(ordem)}
        por_trilha[codigo].sort(key=lambda d: posicao.get(d["texto_egali"], len(ordem)))
    return por_trilha


# Em cada trilha, a ordem da lista é a ordem de exibição (aproximadamente a do processo).
ETAPAS = _organizar_etapas()


# Página de ajuda sobre NEG (slides 2, 31 e 32 do PPT).
ORIENTACOES_NEG = {
    "geral": [
        "Alinhamento sobre as possíveis NEGs.",
        "Fazer anotações no bloco de notas ajuda a lembrar do caso depois; usar o campo da NEG apenas para a NEG.",
        "Mesmo que não seja mais um indicador, precisamos ter atenção, pois faz parte da experiência do aluno.",
    ],
    "dicas": [
        "Puxar cada um dos procedimentos separados.",
        "Alguns procedimentos, principalmente os ligados ao visto, puxar com bastante antecedência e ir cobrando os documentos.",
        "Passaporte e flight details (se visto aprovado): já cobrar com 90, 100, 120 dias antes do procedimento.",
    ],
    "nao_e_neg": [
        "Em qualquer procedimento: sem retorno do aluno e tentativas de contato.",
    ],
    "excecoes": [
        "Exceções de matrícula.",
        "Alteração de data: precisa ter pauta ou confirmação por escrito do aluno de que vai alterar.",
        "Deadline (cuidar sempre, pois pode gerar cancelamento).",
        "Se o aluno tem eTA, o passaporte está no consulado americano e ainda temos prazo: ok.",
        "Se já sabe que não vai ter NEG, não coloca nada.",
    ],
}

SERVICOS = {
    CategoriaServico.CURSO: [
        "Curso Premium", "Curso Budget", "Curso Smart", "Summer Schools", "Vancouver Experience", "Grupo Premium",
        "Curso + Trabalho", "Curso + Trabalho Canadá", "Canada Leap",
        "Winter Schools", "Viagem Cultural",  # programas do público teen (ver app/publico_teen.py)
    ],
    CategoriaServico.VISTO: [
        "Visto - Estados Unidos", "Visto - Canadá - eTA", "Visto - Canadá", "SEVIS", "Additional documents - Canadá",
    ],
    CategoriaServico.AVULSO: ["Transfer (chegada e saída)", "Seguro Viagem"],
    CategoriaServico.IGNORADO: ["C. Curso", "Valores Extras", "Reserva técnica"],
}


def nome_da_etapa(texto_egali: str) -> str:
    """'SA - EUA - Agendamento do aluno' -> 'Agendamento do aluno'."""
    partes = texto_egali.split(" - ", 2)
    return partes[2].strip() if len(partes) == 3 else texto_egali.strip()


def buscar_etapa_por_texto(texto: str) -> EtapaModelo | None:
    apelido = db.session.execute(
        db.select(ApelidoEtapa).filter_by(texto_normalizado=normalizar_texto(texto))
    ).scalar_one_or_none()
    return apelido.etapa if apelido else None


def _reorganizar_banco(trilhas: dict[str, Trilha], contagem: dict) -> None:
    """Leva um catálogo antigo para a organização atual. Cada passo só age se o
    banco ainda estiver como antes: etapa que alguém já moveu pela tela fica onde está."""

    def posicao(codigo: str, texto: str) -> int:
        ordem = ORDEM_REORGANIZADA.get(codigo, [])
        return ordem.index(texto) + 1 if texto in ordem else 1000

    def renumerar(codigo: str) -> None:
        # Só as etapas que estão na ordem definida; as outras mantêm a ordem que já tinham.
        db.session.flush()
        for etapa in trilhas[codigo].etapas:
            if etapa.texto_egali in ORDEM_REORGANIZADA.get(codigo, []):
                etapa.ordem = posicao(codigo, etapa.texto_egali)

    trilhas_que_receberam = set()
    for texto, (origem, destino) in MUDANCAS_DE_TRILHA.items():
        etapa = buscar_etapa_por_texto(texto)
        if etapa is not None and etapa.trilha.codigo == origem:
            etapa.trilha = trilhas[destino]
            trilhas_que_receberam.add(destino)
            contagem["reorganizadas"] += 1
    for codigo in trilhas_que_receberam:
        renumerar(codigo)

    for antigo, novo in TRILHAS_MESCLADAS.items():
        trilha_antiga = trilhas.get(antigo)
        if trilha_antiga is None:
            continue
        destino = trilhas[novo]
        for etapa in list(trilha_antiga.etapas):
            etapa.trilha = destino
            contagem["reorganizadas"] += 1
        renumerar(novo)
        if destino.nome == NOMES_ANTIGOS_DAS_TRILHAS.get(novo):
            destino.nome = dict(TRILHAS)[novo]
        db.session.delete(trilha_antiga)
        del trilhas[antigo]
        contagem["trilhas_mescladas"] += 1
    db.session.flush()


def carregar_catalogo() -> dict:
    """Cria o que ainda não existe e aplica a reorganização das trilhas num banco
    antigo. Não altera outros registros existentes, exceto serviços ainda "não
    classificados" e trilhas com nome provisório (igual ao código)."""
    contagem = {"trilhas": 0, "etapas": 0, "apelidos": 0, "servicos": 0, "reorganizadas": 0, "trilhas_mescladas": 0}

    trilhas = {t.codigo: t for t in db.session.execute(db.select(Trilha)).scalars()}
    for ordem, (codigo, nome) in enumerate(TRILHAS, start=1):
        if codigo not in trilhas:
            trilhas[codigo] = Trilha(codigo=codigo, nome=nome, ordem=ordem)
            db.session.add(trilhas[codigo])
            contagem["trilhas"] += 1
        elif trilhas[codigo].nome == codigo and nome != codigo:
            # Nome igual ao código = provisório, ninguém deu nome ainda.
            trilhas[codigo].nome = nome
            contagem["trilhas"] += 1
    db.session.flush()
    _reorganizar_banco(trilhas, contagem)

    for codigo, etapas in ETAPAS.items():
        for ordem, dados in enumerate(etapas, start=1):
            textos = [dados["texto_egali"], *dados["apelidos"]]
            etapa = next((e for e in map(buscar_etapa_por_texto, textos) if e), None)
            if etapa is None:
                campos = {k: v for k, v in dados.items() if k != "apelidos"}
                etapa = EtapaModelo(
                    trilha=trilhas[codigo], nome=nome_da_etapa(dados["texto_egali"]), ordem=ordem, **campos
                )
                db.session.add(etapa)
                contagem["etapas"] += 1
            for texto in textos:
                if buscar_etapa_por_texto(texto) is None:
                    db.session.add(ApelidoEtapa(etapa=etapa, texto=texto, texto_normalizado=normalizar_texto(texto)))
                    db.session.flush()
                    contagem["apelidos"] += 1

    existentes = {s.nome_normalizado: s for s in db.session.execute(db.select(ServicoEgali)).scalars()}
    for categoria, nomes in SERVICOS.items():
        for nome in nomes:
            servico = existentes.get(normalizar_texto(nome))
            if servico is None:
                db.session.add(ServicoEgali(nome=nome, nome_normalizado=normalizar_texto(nome), categoria=categoria))
                contagem["servicos"] += 1
            elif servico.categoria == CategoriaServico.NAO_CLASSIFICADO and categoria != servico.categoria:
                # "Não classificado" quer dizer que ninguém decidiu ainda: pode receber a classificação nova.
                servico.categoria = categoria
                contagem["servicos"] += 1
    db.session.flush()

    # Público teen: na primeira vez (nenhum serviço marcado ainda), marca os do painel VEG.
    # Depois disso, quem decide é a tela Cadastros → Público teen.
    from app import publico_teen

    ja_configurado = db.session.execute(db.select(ServicoEgali.id).filter_by(teen=True).limit(1)).first()
    if ja_configurado is None:
        nomes_teen = {normalizar_texto(n) for n in publico_teen.SERVICOS_TEEN_PADRAO}
        for servico in db.session.execute(db.select(ServicoEgali)).scalars():
            if servico.nome_normalizado in nomes_teen:
                servico.teen = True
                contagem["servicos"] += 1
        publico_teen.recalcular()

    db.session.commit()
    return contagem
