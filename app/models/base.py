import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column


def agora() -> datetime:
    return datetime.now(timezone.utc)


def hora_local(momento: datetime | None) -> datetime | None:
    """Datas são gravadas em UTC; o SQLite as devolve sem fuso. Para mostrar
    à equipe, converte para o fuso do servidor."""
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone()


def coluna_enum(classe: type[enum.Enum]) -> Enum:
    """Enum guardado como texto + CHECK. Funciona igual no SQLite e no
    Postgres, sem depender de tipos ENUM nativos."""
    return Enum(
        classe,
        name=classe.__name__.lower(),
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=30,
        values_callable=lambda e: [m.value for m in e],
    )


class ComDatas:
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)
