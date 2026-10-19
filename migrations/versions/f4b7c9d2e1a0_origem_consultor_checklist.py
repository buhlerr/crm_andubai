"""Marca consultores definidos pelo checklist.

Revision ID: f4b7c9d2e1a0
Revises: ec1a54ac4fe8
Create Date: 2026-10-13

"""
from alembic import op
import sqlalchemy as sa


revision = "f4b7c9d2e1a0"
down_revision = "ec1a54ac4fe8"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "programa" not in insp.get_table_names():
        return
    colunas = {coluna["name"] for coluna in insp.get_columns("programa")}
    if "consultor_do_checklist" not in colunas:
        with op.batch_alter_table("programa", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("consultor_do_checklist", sa.Boolean(), server_default=sa.false(), nullable=False)
            )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "programa" not in insp.get_table_names():
        return
    colunas = {coluna["name"] for coluna in insp.get_columns("programa")}
    if "consultor_do_checklist" in colunas:
        with op.batch_alter_table("programa", schema=None) as batch_op:
            batch_op.drop_column("consultor_do_checklist")
