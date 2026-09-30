"""visualização da fila escolhida por cada usuário

Revision ID: af5ef57dd310
Revises: c182388d0923
Create Date: 2026-09-29 14:05:30.165399

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'af5ef57dd310'
down_revision = 'c182388d0923'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'visao_fila',
            sa.Enum('lista', 'kanban', 'quadro', 'calendario', name='visaofila', native_enum=False, create_constraint=False, length=30),
            server_default='lista', nullable=False,
        ))
        batch_op.create_check_constraint(
            op.f('ck_usuario_visaofila'), "visao_fila IN ('lista', 'kanban', 'quadro', 'calendario')"
        )


def downgrade():
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_usuario_visaofila'), type_='check')
        batch_op.drop_column('visao_fila')
