"""estado interno e histórico das pautas

Revision ID: 2d9c4a7e1b30
Revises: ec1a54ac4fe8
"""
from alembic import op
import sqlalchemy as sa

revision = "2d9c4a7e1b30"
down_revision = "f4b7c9d2e1a0"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tabelas = set(insp.get_table_names())
    if "pauta" in tabelas:
        colunas = {c["name"] for c in insp.get_columns("pauta")}
        faltantes = [
            ("estado_interno", sa.String(length=30), "acao"),
            ("estado_interno_em", sa.DateTime(timezone=True), "CURRENT_TIMESTAMP"),
            ("estado_interno_por_id", sa.Integer(), None),
        ]
        with op.batch_alter_table("pauta") as batch:
            for nome, tipo, padrao in faltantes:
                if nome not in colunas:
                    kwargs = {"nullable": nome != "estado_interno"}
                    if padrao is not None:
                        kwargs["server_default"] = sa.text(
                            "CURRENT_TIMESTAMP" if padrao == "CURRENT_TIMESTAMP" else f"'{padrao}'"
                        )
                    batch.add_column(sa.Column(nome, tipo, **kwargs))
            if "estado_interno" not in colunas or "ix_pauta_estado_interno" not in {
                i["name"] for i in insp.get_indexes("pauta")
            }:
                batch.create_index("ix_pauta_estado_interno", ["estado_interno"])
            if "estado_interno_por_id" not in colunas:
                batch.create_foreign_key(
                    "fk_pauta_estado_interno_por_id_usuario", "usuario", ["estado_interno_por_id"], ["id"]
                )
    if "pauta_historico" not in tabelas:
        op.create_table(
            "pauta_historico",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("pauta_id", sa.Integer(), nullable=False),
            sa.Column("estado_anterior", sa.String(length=30), nullable=True),
            sa.Column("estado_novo", sa.String(length=30), nullable=False),
            sa.Column("usuario_id", sa.Integer(), nullable=True),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["pauta_id"], ["pauta.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("pauta_historico") as batch:
            batch.create_index("ix_pauta_historico_pauta_id", ["pauta_id"])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "pauta_historico" in insp.get_table_names():
        op.drop_table("pauta_historico")
    if "pauta" in insp.get_table_names():
        with op.batch_alter_table("pauta") as batch:
            if "ix_pauta_estado_interno" in {i["name"] for i in insp.get_indexes("pauta")}:
                batch.drop_index("ix_pauta_estado_interno")
            for nome in ("estado_interno_por_id", "estado_interno_em", "estado_interno"):
                if nome in {c["name"] for c in insp.get_columns("pauta")}:
                    batch.drop_column(nome)
