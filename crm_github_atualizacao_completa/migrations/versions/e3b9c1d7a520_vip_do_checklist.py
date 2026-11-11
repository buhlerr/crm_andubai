"""programa.vip_egali: VIP pelo checklist (procedimento VIP ou tag VIP)

O checklist passou a ser a única importação; sem a planilha, não há mais a pontuação.

Revision ID: e3b9c1d7a520
Revises: 2d9c4a7e1b30
Create Date: 2026-11-10

"""
import sqlalchemy as sa
from alembic import op

revision = "e3b9c1d7a520"
down_revision = "2d9c4a7e1b30"
branch_labels = None
depends_on = None


def upgrade():
    colunas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("programa")}
    if "vip_egali" not in colunas:
        with op.batch_alter_table("programa") as batch_op:
            batch_op.add_column(sa.Column("vip_egali", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    colunas = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("programa")}
    if "vip_egali" in colunas:
        with op.batch_alter_table("programa") as batch_op:
            batch_op.drop_column("vip_egali")
