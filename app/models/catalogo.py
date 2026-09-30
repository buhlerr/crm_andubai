from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import ComDatas


class Trilha(db.Model):
    __tablename__ = "trilha"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)  # como aparece no CSV: GERAL, VISTOS...
    nome: Mapped[str] = mapped_column(String(100))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)

    etapas: Mapped[list["EtapaModelo"]] = relationship(back_populates="trilha", order_by="EtapaModelo.ordem")


class EtapaModelo(ComDatas, db.Model):
    """Procedimento do catálogo. Não gera tarefas (quem cria é o CSV): serve
    para agrupar, ordenar e mostrar as orientações do PPT junto da tarefa."""

    __tablename__ = "etapa_modelo"
    __table_args__ = (UniqueConstraint("trilha_id", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trilha_id: Mapped[int] = mapped_column(ForeignKey("trilha.id"), index=True)
    nome: Mapped[str] = mapped_column(String(300))
    # Texto completo como vem na coluna "Procedimento" do CSV (SA - <trilha> - <etapa>).
    texto_egali: Mapped[str] = mapped_column(String(400))
    ordem: Mapped[int] = mapped_column(Integer, default=0)

    # Orientações (PPT "Checklist S.A."). O prazo é calculado pela Egali; aqui é só referência.
    regra_prazo: Mapped[str | None] = mapped_column(Text)
    o_que_e: Mapped[str | None] = mapped_column(Text)
    importancia: Mapped[str | None] = mapped_column(Text)
    quando_cabe_neg: Mapped[str | None] = mapped_column(Text)
    link_gravacao: Mapped[str | None] = mapped_column(String(500))

    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    # Procedimento que apareceu no CSV sem estar no catálogo: entra sozinho e fica marcado para revisão.
    criada_automaticamente: Mapped[bool] = mapped_column(Boolean, default=False)

    trilha: Mapped["Trilha"] = relationship(back_populates="etapas")
    apelidos: Mapped[list["ApelidoEtapa"]] = relationship(back_populates="etapa", cascade="all, delete-orphan")


class ApelidoEtapa(db.Model):
    """Todo texto conhecido que aponta para uma etapa, incluindo o texto
    principal. É por aqui que uma linha do CSV encontra sua etapa."""

    __tablename__ = "apelido_etapa"

    id: Mapped[int] = mapped_column(primary_key=True)
    etapa_id: Mapped[int] = mapped_column(ForeignKey("etapa_modelo.id"), index=True)
    texto: Mapped[str] = mapped_column(String(400))
    texto_normalizado: Mapped[str] = mapped_column(String(400), unique=True)

    etapa: Mapped["EtapaModelo"] = relationship(back_populates="apelidos")
