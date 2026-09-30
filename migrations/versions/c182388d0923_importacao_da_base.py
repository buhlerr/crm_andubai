"""importacao da base: dados lidos da prévia e novos tipos de ocorrência

Revision ID: c182388d0923
Revises: a1c3e5f70201
Create Date: 2026-09-29 10:43:28.156585

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c182388d0923'
down_revision = 'a1c3e5f70201'
branch_labels = None
depends_on = None

_CHECK = "ck_ocorrencia_importacao_tipoocorrencia"
_TIPOS_ANTES = (
    "'sem_programa_id', 'sem_aluno_id', 'programa_faltando_na_planilha', 'divergencia_aluno', "
    "'aluno_com_varios_programas', 'consultor_nao_encontrado', 'consultor_divergente', 'procedimento_novo', "
    "'servico_nao_classificado', 'vip_abaixo_da_pontuacao', 'linha_invalida'"
)
_TIPOS_DEPOIS = _TIPOS_ANTES + ", 'cancelamento_em_massa', 'arquivo_ja_importado'"


def upgrade():
    with op.batch_alter_table('importacao', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dados_lidos', sa.JSON(), nullable=True))

    with op.batch_alter_table('ocorrencia_importacao', schema=None) as batch_op:
        batch_op.drop_constraint(op.f(_CHECK), type_="check")
        batch_op.create_check_constraint(op.f(_CHECK), f"tipo IN ({_TIPOS_DEPOIS})")


def downgrade():
    op.execute(
        "DELETE FROM ocorrencia_importacao WHERE tipo IN ('cancelamento_em_massa', 'arquivo_ja_importado')"
    )
    with op.batch_alter_table('ocorrencia_importacao', schema=None) as batch_op:
        batch_op.drop_constraint(op.f(_CHECK), type_="check")
        batch_op.create_check_constraint(op.f(_CHECK), f"tipo IN ({_TIPOS_ANTES})")

    with op.batch_alter_table('importacao', schema=None) as batch_op:
        batch_op.drop_column('dados_lidos')
