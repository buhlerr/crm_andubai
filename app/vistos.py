"""Tipo de visto do aluno, no formato que a equipe usa: "Visto - Canadá - Turista".

A fonte é a coluna "Visto normalizado" da planilha, que separa o tipo (turista, estudante, eTA...)
e pode ter mais de um visto separado por vírgula: "Turista - EUA,eTA - Canadá". Os serviços das
compras ("Visto - Canadá") não dizem o tipo, então só servem de reserva para os programas só de
visto, que não estão na planilha.
"""

import re

from app.extensions import db
from app.models import CategoriaServico, Programa, ServicoEgali
from app.texto import normalizar_texto

SEM_VISTO = "Sem visto informado"
PAISES = {"eua": "EUA", "estados unidos": "EUA", "canada": "Canadá", "canadá": "Canadá"}
TIPOS = {"esta u.s": "ESTA", "segundo visto": "Segundo visto", "canadá/quebec": "Quebec", "canada/quebec": "Quebec"}


def tokens(visto_normalizado: str | None) -> list[str]:
    """Cada visto da célula, como está na planilha ("Turista - EUA")."""
    if not visto_normalizado:
        return []
    partes = [p.strip() for p in visto_normalizado.split(",")]
    return [p for p in partes if p and normalizar_texto(p) != normalizar_texto(SEM_VISTO)]


def rotulo(token: str) -> str:
    """"Turista - EUA" -> "Visto - EUA - Turista"; "Canadá/Quebec - Canadá" -> "Visto - Canadá - Quebec"."""
    m = re.match(r"^(.*?)\s*-\s*([^-]+)$", token)
    if not m:
        return f"Visto - {token}"
    tipo, pais = m.group(1).strip(), m.group(2).strip()
    pais = PAISES.get(normalizar_texto(pais), pais)
    tipo = TIPOS.get(normalizar_texto(tipo), tipo)
    return f"Visto - {pais} - {tipo}"


def _nomes_de_servicos_de_visto() -> set[str]:
    """Uma consulta por requisição (as telas mostram dezenas de alunos)."""
    from flask import g, has_app_context

    if has_app_context() and hasattr(g, "_servicos_de_visto"):
        return g._servicos_de_visto
    nomes = set(db.session.execute(
        db.select(ServicoEgali.nome_normalizado).filter_by(categoria=CategoriaServico.VISTO)
    ).scalars())
    if has_app_context():
        g._servicos_de_visto = nomes
    return nomes


def _servicos_de_visto(programa: Programa) -> list[str]:
    nomes = _nomes_de_servicos_de_visto()
    vistos = []
    for compra in programa.compras:
        if compra.servico and normalizar_texto(compra.servico) in nomes and compra.servico.lower().startswith("visto"):
            nome = compra.servico.replace("Estados Unidos", "EUA")
            if nome not in vistos:
                vistos.append(nome)
    return vistos


def tipos_de_visto(programa: Programa) -> list[str]:
    """Rótulos dos vistos do programa (pode ser vazio)."""
    rotulos = [rotulo(t) for t in tokens(programa.visto_normalizado)]
    return rotulos or _servicos_de_visto(programa)


def texto_de_visto(programa: Programa) -> str:
    return " · ".join(tipos_de_visto(programa)) or SEM_VISTO
