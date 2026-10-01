"""senha individual (usuario.senha_hash) e pautas (pauta, pauta_anotacao, colaborador_setor)

Antes desta migração, a coluna senha_hash era criada por um ALTER TABLE no evento de conexão e as
tabelas de pautas não eram criadas por nenhuma migração. Bancos que já estão em uso podem ter
tudo isso (ou parte): por isso cada passo confere antes de criar, e a migração serve tanto para
banco novo quanto para o de produção.

Revision ID: 11a6fad7f26a
Revises: a750f5567f2c
Create Date: 2026-10-01 15:42:07.986553

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '11a6fad7f26a'
down_revision = 'a750f5567f2c'
branch_labels = None
depends_on = None


def _tabelas():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _colunas(tabela):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabela)}


def _indices(tabela):
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(tabela)}


def _criar_indices(tabela, indices):
    existentes = _indices(tabela)
    with op.batch_alter_table(tabela, schema=None) as batch_op:
        for nome, colunas, unico in indices:
            if nome not in existentes:
                batch_op.create_index(nome, colunas, unique=unico)


def upgrade():
    tabelas = _tabelas()

    if 'colaborador_setor' not in tabelas:
        op.create_table('colaborador_setor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=200), nullable=False),
        sa.Column('nome_normalizado', sa.String(length=200), nullable=False),
        sa.Column('setor', sa.String(length=150), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_colaborador_setor'))
        )
    _criar_indices('colaborador_setor', [
        (op.f('ix_colaborador_setor_nome'), ['nome'], True),
        (op.f('ix_colaborador_setor_nome_normalizado'), ['nome_normalizado'], True),
    ])

    if 'pauta' not in tabelas:
        op.create_table('pauta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('categoria', sa.String(length=250), nullable=False),
        sa.Column('categoria_limpa', sa.String(length=250), nullable=True),
        sa.Column('pauta_titulo', sa.String(length=500), nullable=False),
        sa.Column('aluno', sa.String(length=200), nullable=True),
        sa.Column('status_tm', sa.String(length=100), nullable=False),
        sa.Column('responsavel_tm', sa.String(length=200), nullable=True),
        sa.Column('criado_em_tm', sa.DateTime(timezone=True), nullable=True),
        sa.Column('criado_por_tm', sa.String(length=200), nullable=True),
        sa.Column('atualizado_em_tm', sa.DateTime(timezone=True), nullable=True),
        sa.Column('atualizado_por_tm', sa.String(length=200), nullable=True),
        sa.Column('tag', sa.String(length=100), nullable=True),
        sa.Column('tempo_inativo_texto', sa.String(length=50), nullable=True),
        sa.Column('tempo_inativo_horas', sa.Integer(), server_default='0', nullable=False),
        sa.Column('prazo_sla_horas', sa.Integer(), nullable=True),
        sa.Column('un_atualizou', sa.String(length=100), nullable=True),
        sa.Column('un_responsavel', sa.String(length=100), nullable=True),
        sa.Column('un_criou', sa.String(length=100), nullable=True),
        sa.Column('un_final', sa.String(length=200), nullable=True),
        sa.Column('atualizada_un', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('quebra_72h_unidade', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('quebra_72h_outro', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('ativa', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('encerrada_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consultor_id', sa.Integer(), nullable=True),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('observacao_atualizada_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('importacao_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['consultor_id'], ['usuario.id'], name=op.f('fk_pauta_consultor_id_usuario')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pauta'))
        )
    _criar_indices('pauta', [
        (op.f('ix_pauta_aluno'), ['aluno'], False),
        (op.f('ix_pauta_ativa'), ['ativa'], False),
        (op.f('ix_pauta_atualizado_em_tm'), ['atualizado_em_tm'], False),
        (op.f('ix_pauta_categoria_limpa'), ['categoria_limpa'], False),
        (op.f('ix_pauta_consultor_id'), ['consultor_id'], False),
        (op.f('ix_pauta_quebra_72h_unidade'), ['quebra_72h_unidade'], False),
        (op.f('ix_pauta_responsavel_tm'), ['responsavel_tm'], False),
        (op.f('ix_pauta_status_tm'), ['status_tm'], False),
    ])

    if 'pauta_anotacao' not in tabelas:
        op.create_table('pauta_anotacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pauta_id', sa.Integer(), nullable=False),
        sa.Column('autor_id', sa.Integer(), nullable=True),
        sa.Column('texto', sa.Text(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['autor_id'], ['usuario.id'], name=op.f('fk_pauta_anotacao_autor_id_usuario')),
        sa.ForeignKeyConstraint(['pauta_id'], ['pauta.id'], name=op.f('fk_pauta_anotacao_pauta_id_pauta'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pauta_anotacao'))
        )
    _criar_indices('pauta_anotacao', [(op.f('ix_pauta_anotacao_pauta_id'), ['pauta_id'], False)])

    if 'senha_hash' not in _colunas('usuario'):
        with op.batch_alter_table('usuario', schema=None) as batch_op:
            batch_op.add_column(sa.Column('senha_hash', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('usuario', schema=None) as batch_op:
        batch_op.drop_column('senha_hash')
    op.drop_table('pauta_anotacao')
    op.drop_table('pauta')
    op.drop_table('colaborador_setor')
