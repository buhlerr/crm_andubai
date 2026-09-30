"""categoria de serviço "ignorado"

Revision ID: a1c3e5f70201
Revises: 7ff23d970b05
Create Date: 2026-09-29

"""
from alembic import op

revision = "a1c3e5f70201"
down_revision = "7ff23d970b05"
branch_labels = None
depends_on = None

_NOME = "ck_servico_egali_categoriaservico"
_ANTES = "categoria IN ('curso', 'visto', 'avulso', 'nao_classificado')"
_DEPOIS = "categoria IN ('curso', 'visto', 'avulso', 'ignorado', 'nao_classificado')"


def upgrade():
    with op.batch_alter_table("servico_egali") as batch_op:
        batch_op.drop_constraint(op.f(_NOME), type_="check")
        batch_op.create_check_constraint(op.f(_NOME), _DEPOIS)


def downgrade():
    op.execute("UPDATE servico_egali SET categoria = 'nao_classificado' WHERE categoria = 'ignorado'")
    with op.batch_alter_table("servico_egali") as batch_op:
        batch_op.drop_constraint(op.f(_NOME), type_="check")
        batch_op.create_check_constraint(op.f(_NOME), _ANTES)
