import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import ComDatas, agora, coluna_enum


class StatusTarefa(enum.StrEnum):
    A_FAZER = "a_fazer"
    EM_ANDAMENTO = "em_andamento"
    AGUARDANDO_ALUNO = "aguardando_aluno"
    CONCLUIDA = "concluida"
    NAO_SE_APLICA = "nao_se_aplica"


STATUS_ABERTOS = frozenset({StatusTarefa.A_FAZER, StatusTarefa.EM_ANDAMENTO, StatusTarefa.AGUARDANDO_ALUNO})

ROTULOS_STATUS = {
    StatusTarefa.A_FAZER: "A fazer",
    StatusTarefa.EM_ANDAMENTO: "Em andamento",
    StatusTarefa.AGUARDANDO_ALUNO: "Aguardando aluno",
    StatusTarefa.CONCLUIDA: "Concluída",
    StatusTarefa.NAO_SE_APLICA: "Não se aplica",
}


class MotivoEncerramento(enum.StrEnum):
    """Por que o item sumiu do checklist da Egali."""

    FINALIZADO = "finalizado"  # feito pelo consultor
    CANCELADO = "cancelado"  # serviço cancelado (a compra ou o programa saiu da planilha)
    DESCONHECIDO = "desconhecido"


class Tarefa(ComDatas, db.Model):
    """Um item do checklist da Egali (uma linha do CSV).

    Campos que vêm da Egali (prazo_egali, status_egali, obs_egali) são
    sempre atualizados pela importação. O que é trabalho da equipe
    (status, responsavel_manual, data_planejada, anotações) a importação nunca toca.
    """

    __tablename__ = "tarefa"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Coluna "#" do CSV: chave do item no sistema Egali.
    item_checklist_egali: Mapped[str] = mapped_column(String(20), unique=True)
    programa_id: Mapped[int] = mapped_column(ForeignKey("programa.id"), index=True)
    compra_id: Mapped[int | None] = mapped_column(ForeignKey("compra.id"), index=True)
    etapa_id: Mapped[int] = mapped_column(ForeignKey("etapa_modelo.id"), index=True)

    # Vazio = segue o consultor do programa (que acompanha a planilha).
    responsavel_manual_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), index=True)

    # Data do procedimento na Egali: fixa, vem do CSV. É ela que diz se a tarefa está atrasada.
    prazo_egali: Mapped[date | None] = mapped_column(Date, index=True)
    # Data em que o consultor planeja fazer. Vazio = a mesma do procedimento.
    # Ordena as filas e posiciona a tarefa no calendário; não muda o atraso.
    data_planejada: Mapped[date | None] = mapped_column(Date)

    status: Mapped[StatusTarefa] = mapped_column(
        coluna_enum(StatusTarefa), default=StatusTarefa.A_FAZER, index=True
    )
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status_egali: Mapped[str | None] = mapped_column(String(50))
    # Coluna NEG: "Observação do sistema Egali". Separada das anotações do sistema novo.
    obs_egali: Mapped[str | None] = mapped_column(Text)
    obs_egali_atualizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Preenchidos quando o item some do CSV.
    encerrada_egali_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_encerramento: Mapped[MotivoEncerramento | None] = mapped_column(coluna_enum(MotivoEncerramento))

    ultima_importacao_id: Mapped[int | None] = mapped_column(ForeignKey("importacao.id"))

    # Concluída (ou "não se aplica") neste sistema e já lançada pela pessoa no sistema da Egali.
    # A confirmação de verdade vem na importação seguinte, quando o item some do CSV.
    lancada_egali_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lancada_egali_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    programa: Mapped["Programa"] = relationship(back_populates="tarefas")  # noqa: F821
    ultima_importacao: Mapped["Importacao | None"] = relationship()  # noqa: F821
    lancada_egali_por: Mapped["Usuario | None"] = relationship(foreign_keys=[lancada_egali_por_id])  # noqa: F821
    compra: Mapped["Compra | None"] = relationship()  # noqa: F821
    etapa: Mapped["EtapaModelo"] = relationship()  # noqa: F821
    responsavel_manual: Mapped["Usuario | None"] = relationship(foreign_keys=[responsavel_manual_id])  # noqa: F821
    anotacoes: Mapped[list["Anotacao"]] = relationship(back_populates="tarefa", order_by="Anotacao.criado_em")

    @property
    def responsavel(self):
        return self.responsavel_manual or self.programa.consultor

    @property
    def data_prevista(self) -> date | None:
        """Quando a tarefa deve ser feita: a planejada pelo consultor, senão a do procedimento."""
        return self.data_planejada or self.prazo_egali

    @property
    def planejada_apos_prazo(self) -> bool:
        return bool(self.data_planejada and self.prazo_egali and self.data_planejada > self.prazo_egali)

    @property
    def aberta(self) -> bool:
        return self.status in STATUS_ABERTOS

    @property
    def na_fila(self) -> bool:
        return self.aberta and self.programa.ativo

    def atrasada(self, hoje: date | None = None) -> bool:
        """Pela data do procedimento na Egali (fixa), não pela planejada."""
        hoje = hoje or date.today()
        return self.aberta and self.prazo_egali is not None and self.prazo_egali < hoje

    def dias_de_atraso(self, hoje: date | None = None) -> int:
        hoje = hoje or date.today()
        return (hoje - self.prazo_egali).days if self.atrasada(hoje) else 0

    @property
    def tem_justificativa(self) -> bool:
        return bool(self.obs_egali and self.obs_egali.strip())


class Anotacao(db.Model):
    """Anotação feita no sistema novo. A importação nunca mexe aqui."""

    __tablename__ = "anotacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefa.id"), index=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    # Tela "Para lançar na Egali": a pessoa lançou como NEG no sistema da Egali, ou disse que não precisa.
    lancada_egali_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lancada_egali_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    nao_precisa_lancar: Mapped[bool] = mapped_column(Boolean, default=False, server_default=db.false())

    tarefa: Mapped["Tarefa"] = relationship(back_populates="anotacoes")
    autor: Mapped["Usuario"] = relationship(foreign_keys=[autor_id])  # noqa: F821
    lancada_egali_por: Mapped["Usuario | None"] = relationship(foreign_keys=[lancada_egali_por_id])  # noqa: F821


class HistoricoTarefa(db.Model):
    """Quem mudou o quê. Sem usuário = mudança feita por uma importação."""

    __tablename__ = "historico_tarefa"

    id: Mapped[int] = mapped_column(primary_key=True)
    tarefa_id: Mapped[int] = mapped_column(ForeignKey("tarefa.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    importacao_id: Mapped[int | None] = mapped_column(ForeignKey("importacao.id"))
    campo: Mapped[str] = mapped_column(String(50))
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_novo: Mapped[str | None] = mapped_column(Text)
    quando: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
