"""O que a equipe faz numa tarefa. Tudo fica no histórico, com quem fez."""

from datetime import date

from app.extensions import db
from app.models import Anotacao, HistoricoTarefa, ROTULOS_STATUS, StatusTarefa, Tarefa, Usuario
from app.models.base import agora


def _historico(tarefa: Tarefa, usuario: Usuario, campo: str, anterior, novo):
    db.session.add(HistoricoTarefa(
        tarefa_id=tarefa.id, usuario_id=usuario.id, campo=campo,
        valor_anterior=None if anterior is None else str(anterior),
        valor_novo=None if novo is None else str(novo),
    ))


def mudar_status(tarefa: Tarefa, status: StatusTarefa, usuario: Usuario) -> bool:
    if tarefa.status == status:
        return False
    _historico(tarefa, usuario, "status", tarefa.status.value, status.value)
    tarefa.status = status
    tarefa.concluida_em = agora() if status == StatusTarefa.CONCLUIDA else None
    if tarefa.aberta and tarefa.lancada_egali_em:
        # Voltou a ficar aberta: o "lancei na Egali" anterior não vale mais.
        tarefa.lancada_egali_em = tarefa.lancada_egali_por_id = None
    db.session.commit()
    return True


def marcar_lancada(tarefa: Tarefa, usuario: Usuario) -> bool:
    """A pessoa lançou na Egali o que concluiu aqui. A importação seguinte confirma (o item some do CSV)."""
    if tarefa.aberta:
        return False
    _historico(tarefa, usuario, "lancamento_egali", None, "lançada no sistema da Egali")
    tarefa.lancada_egali_em = agora()
    tarefa.lancada_egali_por_id = usuario.id
    db.session.commit()
    return True


def marcar_anotacao(anotacao: Anotacao, usuario: Usuario, nao_precisa: bool = False) -> None:
    """Observação lançada como NEG na Egali, ou que não precisa ser lançada."""
    anotacao.lancada_egali_em = agora()
    anotacao.lancada_egali_por_id = usuario.id
    anotacao.nao_precisa_lancar = nao_precisa
    db.session.commit()


def mudar_responsavel(tarefa: Tarefa, novo: Usuario | None, usuario: Usuario) -> bool:
    """novo=None: volta a seguir o consultor do programa."""
    if tarefa.responsavel_manual is novo:
        return False
    _historico(
        tarefa, usuario, "responsavel",
        tarefa.responsavel_manual.nome if tarefa.responsavel_manual else "(consultor do programa)",
        novo.nome if novo else "(consultor do programa)",
    )
    tarefa.responsavel_manual = novo
    db.session.commit()
    return True


def mudar_data_planejada(tarefa: Tarefa, data: date | None, usuario: Usuario) -> bool:
    """Data em que o consultor vai fazer. None, ou a própria data do procedimento,
    volta a seguir a data da Egali. A data do procedimento nunca muda aqui."""
    if data == tarefa.prazo_egali:
        data = None
    if tarefa.data_planejada == data:
        return False
    _historico(tarefa, usuario, "data_planejada", tarefa.data_planejada, data)
    tarefa.data_planejada = data
    db.session.commit()
    return True


def anotar(tarefa: Tarefa, texto: str, usuario: Usuario) -> Anotacao | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    anotacao = Anotacao(tarefa=tarefa, autor=usuario, texto=texto)
    db.session.add(anotacao)
    db.session.commit()
    return anotacao


ROTULOS_CAMPOS_HISTORICO = {
    "status": "Status",
    "responsavel": "Responsável",
    "data_planejada": "Data planejada",
    "prazo_egali": "Data do procedimento (Egali)",
    "obs_egali": "NEG",
    "programa": "Programa",
    "procedimento": "Procedimento",
    "encerramento": "Saiu do checklist",
    "lancamento_egali": "Lançada na Egali",
}


def descrever_valor(campo: str, valor: str | None) -> str:
    if valor is None or valor == "":
        return "—"
    if campo == "status":
        try:
            return ROTULOS_STATUS[StatusTarefa(valor)]
        except ValueError:
            return valor
    if campo in ("data_planejada", "prazo_egali") and len(valor) == 10 and valor[4] == "-":
        return f"{valor[8:10]}/{valor[5:7]}/{valor[0:4]}"
    return valor
