"""Fluxo comum às importações: prévia -> confirmação ou descarte.

A prévia roda o processamento inteiro e desfaz tudo no final (rollback).
A confirmação roda o mesmo processamento e grava. Assim o resumo mostrado
é exatamente o que vai acontecer. Se o banco mudou entre a prévia e a
confirmação (outra importação no meio), a confirmação é recusada.
"""

import hashlib
from typing import Callable

from app.extensions import db
from app.importacao import ErroImportacao
from app.models import (
    Gravidade,
    Importacao,
    OcorrenciaImportacao,
    SituacaoImportacao,
    TipoImportacao,
    TipoOcorrencia,
)
from app.models.base import agora, hora_local

# processar(linhas_brutas, coletor, importacao_id, parametros) -> resumo
Processar = Callable[[list[dict], "Coletor", int | None, dict], dict]


class Coletor:
    """Junta os erros e avisos da importação."""

    def __init__(self):
        self.itens: list[dict] = []
        self.linhas_ignoradas = 0  # linhas sem nenhum dado (sobras de colunas auxiliares)

    def erro(self, tipo, mensagem, linha=None, chave=None):
        self.itens.append(dict(gravidade=Gravidade.ERRO, tipo=tipo, mensagem=mensagem, linha=linha, chave=chave))

    def aviso(self, tipo, mensagem, linha=None, chave=None):
        self.itens.append(dict(gravidade=Gravidade.AVISO, tipo=tipo, mensagem=mensagem, linha=linha, chave=chave))

    def conta(self, gravidade) -> int:
        return sum(1 for i in self.itens if i["gravidade"] == gravidade)


def hash_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def so_colunas(linhas_brutas: list[dict], colunas: frozenset[str]) -> list[dict]:
    # Os arquivos têm CPF, passaporte, e-mail, telefone... Na prévia só fica o que a importação usa.
    return [
        {"linha": b["linha"], "valores": {k: v for k, v in b["valores"].items() if k in colunas}}
        for b in linhas_brutas
    ]


def criar_previa(
    tipo: TipoImportacao,
    linhas_brutas: list[dict],
    processar: Processar,
    parametros: dict | None = None,
    arquivo_nome: str | None = None,
    arquivo_hash: str | None = None,
    usuario_id: int | None = None,
) -> Importacao:
    """parametros vira colunas da importação (ex.: periodo_inicio, periodo_fim)
    e é repassado ao processamento na prévia e na confirmação."""
    parametros = parametros or {}
    coletor = Coletor()
    try:
        resumo = processar(linhas_brutas, coletor, None, parametros)
    finally:
        db.session.rollback()

    if arquivo_hash:
        anterior = db.session.execute(
            db.select(Importacao)
            .filter_by(tipo=tipo, situacao=SituacaoImportacao.CONFIRMADA, arquivo_hash=arquivo_hash)
            .order_by(Importacao.concluida_em.desc())
        ).scalars().first()
        if anterior:
            coletor.aviso(
                TipoOcorrencia.ARQUIVO_JA_IMPORTADO,
                f"Este mesmo arquivo já foi importado em {hora_local(anterior.concluida_em):%d/%m/%Y %H:%M}. "
                "Importar de novo não duplica nada.",
            )

    resumo["linhas_sem_dados_ignoradas"] = coletor.linhas_ignoradas
    resumo["erros"] = coletor.conta(Gravidade.ERRO)
    resumo["avisos"] = coletor.conta(Gravidade.AVISO)
    importacao = Importacao(
        tipo=tipo,
        situacao=SituacaoImportacao.PREVIA,
        arquivo_nome=arquivo_nome,
        arquivo_hash=arquivo_hash,
        iniciada_por_id=usuario_id,
        resumo=resumo,
        dados_lidos=linhas_brutas,
        ocorrencias=[OcorrenciaImportacao(**item) for item in coletor.itens],
        **parametros,
    )
    db.session.add(importacao)
    db.session.commit()
    return importacao


def confirmar(importacao: Importacao, tipo: TipoImportacao, processar: Processar, contagens: tuple[str, ...],
              parametros: dict | None = None) -> Importacao:
    if importacao.tipo != tipo or importacao.situacao != SituacaoImportacao.PREVIA:
        raise ErroImportacao("Esta importação não está esperando confirmação.")
    esperado = {c: importacao.resumo[c] for c in contagens}
    try:
        resumo = processar(importacao.dados_lidos, Coletor(), importacao.id, parametros or {})
        if {c: resumo[c] for c in contagens} != esperado:
            raise ErroImportacao(
                "Os dados do sistema mudaram desde que esta prévia foi gerada. Gere a prévia de novo antes de confirmar."
            )
    except Exception:
        db.session.rollback()
        raise
    importacao.situacao = SituacaoImportacao.CONFIRMADA
    importacao.concluida_em = agora()
    importacao.dados_lidos = None
    db.session.commit()
    return importacao


def descartar(importacao: Importacao) -> Importacao:
    if importacao.situacao != SituacaoImportacao.PREVIA:
        raise ErroImportacao("Esta importação não está esperando confirmação.")
    importacao.situacao = SituacaoImportacao.DESCARTADA
    importacao.concluida_em = agora()
    importacao.dados_lidos = None
    db.session.commit()
    return importacao
