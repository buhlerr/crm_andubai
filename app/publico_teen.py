"""Público teen: marca o aluno, não exclui.

A equipe de Teens é independente do Suporte ao Aluno, mas usa as mesmas
estruturas no TM, então os arquivos vêm com as duas operações misturadas.
Mesma regra do painel VEG (Grupo 1 · Checklist do Suporte): é teen o aluno
com pelo menos um destes sinais, em qualquer programa ou compra dele:
- um serviço marcado como teen (Summer Schools, Winter Schools, Viagem
  Cultural, Vancouver Experience; editável em Cadastros → Público teen);
- a tag "summer";
- um consultor da equipe teen como consultor do programa.

A marca é do aluno inteiro, não da tarefa, porque a maior parte das tarefas
de um aluno teen fica em serviços neutros (eTA, visto, transfer), que
sozinhos não identificariam o perfil.
"""

from collections import defaultdict

from app.extensions import db
from app.models import Aluno, Compra, ConsultorTeen, Programa, ServicoEgali
from app.texto import normalizar_texto

SERVICOS_TEEN_PADRAO = ("Summer Schools", "Winter Schools", "Viagem Cultural", "Vancouver Experience")
TAG_TEEN = "summer"


def _itens(lista: str | None) -> list[str]:
    return [normalizar_texto(p) for p in (lista or "").split(",") if p.strip()]


def recalcular() -> int:
    """Refaz a marca de todos os alunos. Não faz commit. Devolve quantos são teen."""
    servicos_teen = {s.nome_normalizado: s.nome for s in db.session.execute(db.select(ServicoEgali).filter_by(teen=True)).scalars()}
    consultores_teen = {c.nome_normalizado: c.nome for c in db.session.execute(db.select(ConsultorTeen)).scalars()}
    motivos: dict[int, list[str]] = defaultdict(list)

    def marcar(aluno_id: int, motivo: str):
        if motivo not in motivos[aluno_id]:
            motivos[aluno_id].append(motivo)

    for programa in db.session.execute(db.select(Programa)).scalars():
        for servico in _itens(programa.servicos_egali):
            if servico in servicos_teen:
                marcar(programa.aluno_id, servicos_teen[servico])
        if TAG_TEEN in _itens(programa.tags_egali):
            marcar(programa.aluno_id, "tag summer")
        consultor = normalizar_texto(programa.consultor_texto)
        if consultor in consultores_teen:
            marcar(programa.aluno_id, f"consultor teen ({consultores_teen[consultor]})")

    compras = db.session.execute(
        db.select(Programa.aluno_id, Compra.servico).join(Compra.programa).where(Compra.servico.is_not(None))
    ).all()
    for aluno_id, servico in compras:
        if normalizar_texto(servico) in servicos_teen:
            marcar(aluno_id, servicos_teen[normalizar_texto(servico)])

    total = 0
    for aluno in db.session.execute(db.select(Aluno)).scalars():
        if TAG_TEEN in _itens(aluno.tags_egali):
            marcar(aluno.id, "tag summer")
        lista = motivos.get(aluno.id)
        aluno.teen = bool(lista)
        aluno.teen_motivo = ", ".join(lista)[:300] if lista else None
        total += aluno.teen
    db.session.flush()
    return total
