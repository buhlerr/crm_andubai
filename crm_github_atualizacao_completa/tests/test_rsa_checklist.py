"""Relatório de checklist do ano -> base do painel RSA. Só dados fictícios."""

import io
import json
from datetime import date

import pytest

from app import rsa
from app.importacao import rsa_checklist
from app.importacao.comum import Coletor
from app.importacao.leitor_csv import ler_texto_csv
from app.models import CategoriaServico, ConsultorTeen, Importacao, Papel, ServicoEgali, SituacaoImportacao, Tarefa, Usuario
from app.texto import normalizar_texto

HOJE = date(2026, 11, 10)
COLUNAS = ["#", "ID Aluno", "Aluno ", "Consultor ", "País ", "Tipo De Visto", "Empresa ", "Data ", "Status",
           "Atualizado por:", "Procedimento ", "Tags", "Data da Finalização", "Serviço"]

# Mesmo formato da exportação do TM: duas linhas antes do cabeçalho.
LINHAS = [
    # #, aluno, nome, consultor, país, visto, empresa, prazo, status, quem, procedimento, tags, finalização, serviço
    ("1", "10", "Aluno Um", "Consultora Ana", "Canadá", "Canadá (Estudante)", "Egali Intercâmbio - Brasil", "01/10/2026",
     "Finalizado", "Executora Bia", "SA - VISTOS - Ter uma cópia do visto/negativa", "", "05/10/2026 14:03:22", "Visto - Canadá"),
    ("2", "10", "Aluno Um", "Consultora Ana", "Canadá", "Canadá (Estudante)", "Egali Intercâmbio - Brasil", "01/11/2026",
     "Aguardando", "", "SA - GERAL - Cadastrar flight details", "", "", "Curso + Trabalho Canadá"),
    ("3", "20", "Aluna Dois", "Consultora Ana", "EUA", "EUA (Turista)", "Egali Intercâmbio - Brasil", "20/11/2026",
     "Aguardando", "", "SA - EUA - Agendamento do aluno", "", "", "Visto - Estados Unidos"),
    ("4", "20", "Aluna Dois", "Consultora Ana", "EUA", "EUA (Turista)", "Egali Intercâmbio - Brasil", "01/09/2026",
     "Cancelado", "", "SA - EUA - Pagar a SEVIS e anexar na AA", "", "", "Visto - Estados Unidos"),
    ("5", "30", "Aluno Teen", "Consultora Ana", "Canadá", "", "Egali Intercâmbio - Brasil", "01/08/2026",
     "Finalizado", "Executora Bia", "SA - GERAL - Cadastrar flight details", "", "01/08/2026 10:00:00", "Summer Schools"),
    ("6", "30", "Aluno Teen", "Consultora Ana", "Canadá", "", "Egali Intercâmbio - Brasil", "01/08/2026",
     "Finalizado", "Executora Bia", "SA - VISTOS - Ter uma cópia do visto/negativa", "", "02/08/2026 10:00:00", "Visto - Canadá"),
    ("7", "40", "Aluna Tag", "Consultora Ana", "Irlanda", "", "Egali Intercâmbio - Brasil", "01/08/2026",
     "Finalizado", "Executora Bia", "SA - GERAL - Cadastrar flight details", "summer,Grupo", "01/08/2026 10:00:00", "Curso Premium"),
    ("8", "50", "Aluno Cinco", "Pessoa da Equipe Teen", "Malta", "", "Egali Intercâmbio - Brasil", "01/08/2026",
     "Finalizado", "Executora Bia", "SA - MAL - Realizar agendamento VFS", "", "01/08/2026 10:00:00", "Curso Smart"),
]


def csv_do_tm(linhas=LINHAS) -> str:
    def linha(valores):
        return ";".join(f'"{v}"' for v in valores)
    topo = ['<input id="oInpAllCheckId" name="oInpAllCheckId" type="hidden" value="1,2,3">""',
            '"Contagem de linhas: 8";"Atualizar as datas marcadas abaixo para (marcar/desmarcar tudo): "']
    # "Id da Compra" logo depois do "#": uma compra por item, como nas compras avulsas do TM.
    cabecalho = [COLUNAS[0], "Id da Compra", *COLUNAS[1:]]
    corpo = [linha([l[0], str(int(l[0]) * 100), *l[1:]]) for l in linhas]
    return "\n".join(topo + [linha(cabecalho)] + corpo) + "\n"


@pytest.fixture
def teen(db):
    db.session.add(ServicoEgali(nome="Summer Schools", nome_normalizado=normalizar_texto("Summer Schools"),
                                categoria=CategoriaServico.CURSO, teen=True))
    db.session.add(ConsultorTeen(nome="Pessoa da Equipe Teen", nome_normalizado=normalizar_texto("Pessoa da Equipe Teen")))
    db.session.commit()


def decodificar(base):
    """Base no formato do app -> lista de linhas com os rótulos."""
    n = base["meta"]["n"]
    col = {k: [int(x, 36) for x in v.split(",")] if n else [] for k, v in base["col"].items()}
    linhas = []
    for i in range(n):
        linha = {k: base["dic"][k][col[k][i]] for k in base["dic"]}
        linha.update(dias=col["di"][i] - 1000, visto_proc=col["pv"][i], aluno=col["al"][i])
        linhas.append(linha)
    return linhas


def test_leitor_acha_o_cabecalho_depois_das_linhas_do_tm():
    linhas = ler_texto_csv(csv_do_tm())
    assert len(linhas) == len(LINHAS) and linhas[0]["linha"] == 4
    assert linhas[0]["valores"]["#"] == "1" and linhas[0]["valores"]["atualizado por:"] == "Executora Bia"
    # CSV sem as linhas extras continua igual.
    assert ler_texto_csv('"#";"Aluno"\n"1";"X"\n') == [{"linha": 2, "valores": {"#": "1", "aluno": "X"}}]


def test_base_com_finalizados_em_aberto_e_teen_fora(db, teen):
    base, resumo = rsa_checklist.montar_base(ler_texto_csv(csv_do_tm()), Coletor(), HOJE)
    linhas = decodificar(base)
    procs = [l["proc"] for l in linhas]
    assert len(linhas) == 3  # 1, 2 e 3; o 4 foi cancelado; 5 a 8 são do público teen
    assert resumo["finalizados"] == 1 and resumo["em_aberto"] == 2 and resumo["cancelados_ignorados"] == 1
    assert resumo["alunos_teen_excluidos"] == 3 and resumo["linhas_teen_excluidas"] == 4
    assert base["meta"]["excl_alunos"] == 3 and base["meta"]["atraso_ate"] == "10/11/2026"

    fin, aberto_vencido, aberto_no_prazo = linhas
    assert fin["per"] == "Finalizado" and fin["exec"] == "Executora Bia" and fin["dias"] == 4 and fin["mes"] == "2026-10"
    assert aberto_vencido["per"] == "Em aberto" and aberto_vencido["exec"] == rsa_checklist.EXECUTOR_EM_ABERTO
    assert aberto_vencido["dias"] == 9 and aberto_vencido["mes"] == "2026-11"  # venceu em 01/11, conta até a importação
    assert aberto_no_prazo["dias"] < 0  # vence depois de hoje: não está atrasado
    assert fin["visto_proc"] == 1 and aberto_vencido["visto_proc"] == 0 and aberto_no_prazo["visto_proc"] == 1
    assert fin["prog"] == "CT (Curso + Trabalho)"  # o aluno 10 tem Curso + Trabalho
    assert aberto_no_prazo["prog"] == "Sem curso no período (só visto/serviços)"
    assert aberto_no_prazo["visto"] == "EUA (Turista)" and "SA - MAL - Realizar agendamento VFS" not in procs


@pytest.mark.parametrize("procedimento,visto", [
    ("SA - EUA - Agendamento do aluno", True), ("SA-ON - Send welcome e-mail and message in AA", False),
    ("SA ? AUS - Garantizar presentación de exámenes", True), ("SA - MH - AUS - Agendar biométricos", True),
    ("SA - GRUPOS - Enviar Kit para unidade/parceiro", False), ("SA - Realizar reboarding com aluno revertido CRC", False),
])
def test_procedimento_de_visto(procedimento, visto):
    assert rsa_checklist.procedimento_de_visto(procedimento) is visto


def test_arquivo_sem_as_colunas_do_relatorio(db):
    with pytest.raises(rsa_checklist.ErroImportacao, match="Data da Finalização|data da finalização"):
        rsa_checklist.montar_base(ler_texto_csv('"#";"ID Aluno";"Procedimento";"Data";"Status"\n"1";"2";"SA - GERAL - X";"01/01/2026";"Aguardando"\n'), Coletor())


@pytest.fixture
def cliente(app, db, tmp_path, monkeypatch, teen):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    admin = Usuario(nome="Admin Teste", email="admin@exemplo.com", papel=Papel.ADMIN)
    db.session.add(admin)
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sessao:
        sessao["usuario_id"], sessao["csrf"] = admin.id, "t"
    return c


def test_importacao_de_checklist_pela_tela_atualiza_tarefas_e_rsa(app, db, cliente, tmp_path):
    from app.catalogo_inicial import carregar_catalogo

    carregar_catalogo()
    resposta = cliente.post("/importacoes/nova", data={
        "csrf": "t", "tipo": "checklist",
        "arquivo": (io.BytesIO(csv_do_tm().encode("cp1252")), "checklistServicoNew.csv"),
    }, content_type="multipart/form-data", follow_redirects=True)
    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 200 and "Painel RSA" in html
    importacao = db.session.execute(db.select(Importacao)).scalar_one()
    assert importacao.situacao == SituacaoImportacao.PREVIA
    assert not (tmp_path / "rsa" / "base.json").exists()  # a prévia não grava nada

    cliente.post(f"/importacoes/{importacao.id}/confirmar", data={"csrf": "t"})
    db.session.refresh(importacao)
    assert importacao.situacao == SituacaoImportacao.CONFIRMADA
    base = json.loads((tmp_path / "rsa" / "base.json").read_text(encoding="utf-8"))
    assert base["meta"]["n"] == 3 and base["meta"]["arquivo"] == "checklistServicoNew.csv"
    tarefas = {t.item_checklist_egali: t for t in db.session.execute(db.select(Tarefa)).scalars()}
    assert "4" not in tarefas  # cancelado: não vira tarefa
    assert tarefas["1"].status.value == "concluida" and tarefas["2"].aberta  # finalizado e em aberto


HTML_COM_BASE = """<!doctype html><html><body><div id="login"></div><div id="app"></div>
<script>
const DADOS_CHECKLIST = {"meta":{"n":1},"dic":{"proc":["Antigo"]},"col":{"proc":"0"}};
const DIMS_CH = [['mes','Mês de finalização'], ['per','Período do relatório']];
function agregaCH(dim, rows){ return []; }
function revealApp(u){} function go(p){} function saveDB(){}
</script></body></html>"""


def test_encaixe_troca_a_base_do_html(db, teen):
    base, _ = rsa_checklist.montar_base(ler_texto_csv(csv_do_tm()), Coletor(), HOJE)
    saida = rsa.encaixar(HTML_COM_BASE, "visao", "Pessoa Teste", admin=True, base=base)
    assert '"Antigo"' not in saida and '"Executora Bia"' in saida
    assert "['per','Situação (finalizado ou em aberto)']" in saida and "Mês (finalização ou prazo)" in saida
    assert "agregaCH = function" in saida
    # Sem relatório importado, fica a base do próprio HTML.
    assert '"Antigo"' in rsa.encaixar(HTML_COM_BASE, "visao", "Pessoa Teste", admin=True)
