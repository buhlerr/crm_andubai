"""prazo editado vira "data planejada" (não substitui mais a data da Egali)

Revision ID: b7d41e0c9a12
Revises: af5ef57dd310
Create Date: 2026-09-29

A data do procedimento (prazo_egali) é fixa e define o atraso. A data
planejada é quando o consultor vai fazer; só ordena e posiciona no calendário.
"""
from alembic import op


revision = 'b7d41e0c9a12'
down_revision = 'af5ef57dd310'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tarefa', schema=None) as batch_op:
        batch_op.alter_column('prazo_manual', new_column_name='data_planejada')
    op.execute("UPDATE historico_tarefa SET campo = 'data_planejada' WHERE campo = 'prazo_manual'")


def downgrade():
    op.execute("UPDATE historico_tarefa SET campo = 'prazo_manual' WHERE campo = 'data_planejada'")
    with op.batch_alter_table('tarefa', schema=None) as batch_op:
        batch_op.alter_column('data_planejada', new_column_name='prazo_manual')
