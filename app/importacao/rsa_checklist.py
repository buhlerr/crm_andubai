"""Relatório de checklist (TM) -> base do painel RSA - Checklist do Suporte.

A importação de checklist (app/importacao/checklist.py), a única do sistema, chama
montar_base() com as mesmas linhas que usa para as tarefas e, ao confirmar, guarda a
base. Ela é a que o HTML do RSA mostra (DADOS_CHECKLIST), no formato que o app espera
(dicionário de rótulos + colunas codificadas em base36).

A base fica em <dados>/rsa/base.json, fora do Git, porque traz nomes de alunos e
colaboradores. O HTML guardado não é alterado: a base é trocada na hora de mostrar.

Regras (as mesmas do painel VEG, Grupo 1 · Checklist do Suporte):
- Público teen fora: sai o aluno inteiro que tiver um serviço teen (Cadastros → Público teen),
  a tag "summer" ou um consultor da equipe teen como consultor ou como quem finalizou, e o aluno
  que já está marcado como teen no CRM.
- Finalizado: Status "Finalizado" ou Data da Finalização preenchida. Cancelado: fica fora.
  O resto é "Em aberto".
- Atraso por dia, ignorando a hora: finalizado = finalização - prazo (coluna Data);
  em aberto = data da importação - prazo (o que já venceu e não foi feito: backlog).
- Tipo de programa do aluno, pelos serviços dele no relatório: Grupo > CT > Curso >
  "Sem curso no período".
- Procedimento de visto: todo código de trilha que não seja GERAL, ON, VIP, GRUPOS ou AFR.
"""

import json
import os
import re
from datetime import date

from app.extensions import db
from app.importacao import ErroImportacao
from app.importacao.comum import Coletor
from app.importacao.valores import IdInvalido, normalizar_id_egali
from app.models import Aluno, ConsultorTeen, ServicoEgali, TipoOcorrencia
from app.models.base import agora, hora_local
from app.publico_teen import TAG_TEEN
from app.texto import normalizar_texto

COL_ITEM = "#"
COL_ALUNO = "id aluno"
COL_PROCEDIMENTO = "procedimento"
COL_DATA = "data"
COL_STATUS = "status"
COL_FINALIZACAO = "data da finalização"
COL_EXECUTOR = "atualizado por:"
COL_CONSULTOR = "consultor"
COL_PAIS = "país"
COL_VISTO = "tipo de visto"
COL_EMPRESA = "empresa"
COL_SERVICO = "serviço"
COL_TAGS = "tags"
COLUNAS_OBRIGATORIAS = (COL_ITEM, COL_ALUNO, COL_PROCEDIMENTO, COL_DATA, COL_STATUS, COL_FINALIZACAO)
COLUNAS_USADAS = frozenset(COLUNAS_OBRIGATORIAS) | {
    COL_EXECUTOR, COL_CONSULTOR, COL_PAIS, COL_VISTO, COL_EMPRESA, COL_SERVICO, COL_TAGS,
}

FINALIZADO = "Finalizado"
EM_ABERTO = "Em aberto"
EXECUTOR_EM_ABERTO = "Em aberto (ainda não finalizado)"
SEM_VISTO = "Sem visto vinculado"
PROGRAMAS = ("Grupo", "CT (Curso + Trabalho)", "Curso (Premium/Smart/Budget)", "Sem curso no período (só visto/serviços)")
NAO_SAO_DE_VISTO = {"GERAL", "ON", "VIP", "GRUPOS", "AFR"}

def _data(texto: str | None) -> date | None:
    """"12/11/2026" ou "15/10/2026 14:03:22" -> date. Vazio ou inválido -> None."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", texto or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _texto(valor: str | None) -> str:
    return re.sub(r"\s+", " ", valor or "").strip()


def codigo_da_trilha(procedimento: str) -> str:
    """"SA - EUA - Agendamento" -> "EUA"; "SA-ON - ..." -> "ON"; "SA ? AUS - ..." -> "AUS"; sem código -> ""."""
    partes = re.split(r"\s*[-?–]\s*", _texto(procedimento))
    partes = [p for p in partes if p]
    if len(partes) >= 3 and partes[0].upper() == "SA" and re.fullmatch(r"[A-Z]{2,8}", partes[1]):
        return partes[1]
    return ""


def procedimento_de_visto(procedimento: str) -> bool:
    codigo = codigo_da_trilha(procedimento)
    return bool(codigo) and codigo not in NAO_SAO_DE_VISTO


def tipo_de_programa(servicos: set[str]) -> str:
    texto = " | ".join(normalizar_texto(s) for s in servicos)
    if "grupo" in texto:
        return PROGRAMAS[0]
    if "trabalho" in texto:
        return PROGRAMAS[1]
    if "curso" in texto or "canada leap" in texto:
        return PROGRAMAS[2]
    return PROGRAMAS[3]


def _b36(n: int) -> str:
    digitos = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n < 0:
        return "-" + _b36(-n)
    s = ""
    while True:
        n, r = divmod(n, 36)
        s = digitos[r] + s
        if not n:
            return s


class _Dicionario:
    """Rótulos na ordem em que aparecem; cada linha guarda só o índice."""

    def __init__(self):
        self.rotulos: list[str] = []
        self._indice: dict[str, int] = {}

    def __call__(self, rotulo: str) -> int:
        if rotulo not in self._indice:
            self._indice[rotulo] = len(self.rotulos)
            self.rotulos.append(rotulo)
        return self._indice[rotulo]


def _id_ou_nada(valor):
    try:
        return normalizar_id_egali(valor)
    except IdInvalido:
        return None


def montar_base(linhas_brutas: list[dict], coletor: Coletor, hoje: date | None = None) -> tuple[dict, dict]:
    """Devolve (base no formato DADOS_CHECKLIST, resumo com as contagens)."""
    hoje = hoje or date.today()
    if not linhas_brutas:
        raise ErroImportacao("O arquivo não tem nenhuma linha de dados.")
    colunas = set().union(*(b["valores"].keys() for b in linhas_brutas))
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in colunas]
    if faltando:
        raise ErroImportacao(
            f"O arquivo não tem a(s) coluna(s): {', '.join(faltando)}. "
            "Confira se é o relatório de checklist do TM com os procedimentos finalizados e em aberto."
        )

    servicos_teen = set(db.session.execute(db.select(ServicoEgali.nome_normalizado).filter_by(teen=True)).scalars())
    consultores_teen = set(db.session.execute(db.select(ConsultorTeen.nome_normalizado)).scalars())
    # Aluno já marcado teen no CRM continua fora, mesmo num arquivo sem a linha que o marcou (serviço, tag ou consultor).
    alunos_teen = set(db.session.execute(db.select(Aluno.aluno_id_egali).filter_by(teen=True)).scalars())

    # 1ª passada: lê, separa cancelados e marca o público teen (do aluno inteiro).
    linhas, vistos_itens, teen, cancelados = [], set(), set(), 0
    for bruta in linhas_brutas:
        n, v = bruta["linha"], {k: _texto(val) for k, val in bruta["valores"].items()}
        if not v.get(COL_ALUNO) or not v.get(COL_PROCEDIMENTO):
            coletor.linhas_ignoradas += 1
            continue
        item = v.get(COL_ITEM, "")
        if item and item in vistos_itens:
            coletor.aviso(TipoOcorrencia.LINHA_INVALIDA, f"O item {item} aparece mais de uma vez. Só a primeira linha entrou.", n, item)
            continue
        vistos_itens.add(item)
        status = normalizar_texto(v.get(COL_STATUS))
        if "cancel" in status:
            cancelados += 1
            continue
        prazo = _data(v.get(COL_DATA))
        finalizacao = _data(v.get(COL_FINALIZACAO))
        finalizado = status == "finalizado" or finalizacao is not None
        if finalizado and finalizacao is None:
            coletor.aviso(TipoOcorrencia.LINHA_INVALIDA, "Finalizado sem Data da Finalização: o atraso fica zerado.", n, item)
        if prazo is None:
            coletor.aviso(TipoOcorrencia.LINHA_INVALIDA, f"Sem prazo válido na coluna Data ({v.get(COL_DATA)!r}): o atraso fica zerado.", n, item)
        aluno = v[COL_ALUNO]
        executor = v.get(COL_EXECUTOR) if finalizado else ""
        if (_id_ou_nada(aluno) in alunos_teen
                or normalizar_texto(v.get(COL_SERVICO)) in servicos_teen
                or TAG_TEEN in [normalizar_texto(t) for t in (v.get(COL_TAGS) or "").split(",")]
                or normalizar_texto(v.get(COL_CONSULTOR)) in consultores_teen
                or (executor and normalizar_texto(executor) in consultores_teen)):
            teen.add(aluno)
        linhas.append(dict(v=v, aluno=aluno, prazo=prazo, finalizacao=finalizacao, finalizado=finalizado, executor=executor))

    linhas_teen = sum(1 for l in linhas if l["aluno"] in teen)
    linhas = [l for l in linhas if l["aluno"] not in teen]
    servicos_do_aluno: dict[str, set[str]] = {}
    for l in linhas:
        if l["v"].get(COL_SERVICO):
            servicos_do_aluno.setdefault(l["aluno"], set()).add(l["v"][COL_SERVICO])

    # 2ª passada: codifica no formato do app.
    dims = {k: _Dicionario() for k in ("proc", "exec", "cons", "pais", "visto", "prog", "emp", "mes", "per")}
    dims["per"](FINALIZADO)
    dims["per"](EM_ABERTO)
    alunos = _Dicionario()
    col = {k: [] for k in (*dims, "al", "di", "pv")}
    datas = []
    for l in linhas:
        v = l["v"]
        referencia = l["finalizacao"] if l["finalizado"] else l["prazo"]
        ate = l["finalizacao"] if l["finalizado"] else hoje
        dias = (ate - l["prazo"]).days if (ate and l["prazo"]) else 0
        if referencia:
            datas.append(referencia)
        procedimento = v[COL_PROCEDIMENTO]
        col["proc"].append(dims["proc"](procedimento))
        col["exec"].append(dims["exec"](l["executor"] or "Sem registro") if l["finalizado"] else dims["exec"](EXECUTOR_EM_ABERTO))
        col["cons"].append(dims["cons"](v.get(COL_CONSULTOR) or "Sem consultor"))
        col["pais"].append(dims["pais"](v.get(COL_PAIS) or "Sem país"))
        col["visto"].append(dims["visto"](v.get(COL_VISTO) or SEM_VISTO))
        col["prog"].append(dims["prog"](tipo_de_programa(servicos_do_aluno.get(l["aluno"], set()))))
        col["emp"].append(dims["emp"](v.get(COL_EMPRESA) or "Sem empresa"))
        col["mes"].append(dims["mes"]((referencia or hoje).strftime("%Y-%m")))
        col["per"].append(dims["per"](FINALIZADO if l["finalizado"] else EM_ABERTO))
        col["al"].append(alunos(l["aluno"]))
        col["di"].append(max(dias, -1000) + 1000)  # o app subtrai 1000; atraso = valor > 0
        col["pv"].append(1 if procedimento_de_visto(procedimento) else 0)

    finalizados = sum(1 for l in linhas if l["finalizado"])
    meta = {
        "n": len(linhas), "alunos": len(alunos.rotulos),
        "ini": min(datas).strftime("%d/%m/%Y") if datas else "", "fim": max(datas).strftime("%d/%m/%Y") if datas else "",
        "excl_alunos": len(teen), "excl_linhas": linhas_teen, "n_orig": len(linhas) + linhas_teen,
        "finalizados": finalizados, "em_aberto": len(linhas) - finalizados, "atraso_ate": hoje.strftime("%d/%m/%Y"),
    }
    base = {
        "meta": meta,
        "dic": {k: d.rotulos for k, d in dims.items()},
        "col": {k: ",".join(_b36(x) for x in valores) for k, valores in col.items()},
    }
    resumo = {
        "linhas_importadas": len(linhas) + linhas_teen + cancelados,
        "linhas_na_base": len(linhas), "finalizados": finalizados, "em_aberto": len(linhas) - finalizados,
        "alunos": len(alunos.rotulos), "alunos_teen_excluidos": len(teen), "linhas_teen_excluidas": linhas_teen,
        "cancelados_ignorados": cancelados,
    }
    return base, resumo


# ---------------------------------------------------------------- guardar e ler a base


def _caminho() -> str:
    from flask import current_app

    pasta = os.path.join(current_app.instance_path, "rsa")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, "base.json")


def guardar_base(base: dict, importacao_id: int | None, arquivo_nome: str | None) -> None:
    base = dict(base, meta=dict(base["meta"], importacao_id=importacao_id, arquivo=arquivo_nome,
                                importado_em=hora_local(agora()).strftime("%d/%m/%Y %H:%M")))
    temporario = _caminho() + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporario, _caminho())  # quem estiver abrindo o RSA nunca lê um arquivo pela metade


def base_guardada() -> dict | None:
    try:
        with open(_caminho(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
