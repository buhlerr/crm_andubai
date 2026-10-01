"""senha_hash em usuario e tabelas de pautas (pauta, pauta_anotacao, colaborador_setor)

Revision ID: ec1a54ac4fe8
Revises: a750f5567f2c
Create Date: 2026-10-01 15:31:22.747533

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ec1a54ac4fe8'
down_revision = 'a750f5567f2c'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tabelas_existentes = set(insp.get_table_names())

    # 1. Coluna senha_hash em usuario
    if "usuario" in tabelas_existentes:
        colunas_usuario = {c["name"] for c in insp.get_columns("usuario")}
        if "senha_hash" not in colunas_usuario:
            with op.batch_alter_table("usuario", schema=None) as batch_op:
                batch_op.add_column(sa.Column("senha_hash", sa.String(length=255), nullable=True))

    # 2. Tabela colaborador_setor
    if "colaborador_setor" not in tabelas_existentes:
        op.create_table(
            "colaborador_setor",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("nome", sa.String(length=200), nullable=False),
            sa.Column("nome_normalizado", sa.String(length=200), nullable=False),
            sa.Column("setor", sa.String(length=150), nullable=False),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_colaborador_setor")),
            sa.UniqueConstraint("nome", name=op.f("uq_colaborador_setor_nome")),
            sa.UniqueConstraint("nome_normalizado", name=op.f("uq_colaborador_setor_nome_normalizado")),
        )
        with op.batch_alter_table("colaborador_setor", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_colaborador_setor_nome"), ["nome"], unique=True)
            batch_op.create_index(batch_op.f("ix_colaborador_setor_nome_normalizado"), ["nome_normalizado"], unique=True)

    # 3. Tabela pauta
    if "pauta" not in tabelas_existentes:
        op.create_table(
            "pauta",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("categoria", sa.String(length=250), nullable=False),
            sa.Column("categoria_limpa", sa.String(length=250), nullable=True),
            sa.Column("pauta_titulo", sa.String(length=500), nullable=False),
            sa.Column("aluno", sa.String(length=200), nullable=True),
            sa.Column("status_tm", sa.String(length=100), nullable=False),
            sa.Column("responsavel_tm", sa.String(length=200), nullable=True),
            sa.Column("criado_em_tm", sa.DateTime(timezone=True), nullable=True),
            sa.Column("criado_por_tm", sa.String(length=200), nullable=True),
            sa.Column("atualizado_em_tm", sa.DateTime(timezone=True), nullable=True),
            sa.Column("atualizado_por_tm", sa.String(length=200), nullable=True),
            sa.Column("tag", sa.String(length=100), nullable=True),
            sa.Column("tempo_inativo_texto", sa.String(length=50), nullable=True),
            sa.Column("tempo_inativo_horas", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("prazo_sla_horas", sa.Integer(), nullable=True),
            sa.Column("un_atualizou", sa.String(length=100), nullable=True),
            sa.Column("un_responsavel", sa.String(length=100), nullable=True),
            sa.Column("un_criou", sa.String(length=100), nullable=True),
            sa.Column("un_final", sa.String(length=200), nullable=True),
            sa.Column("atualizada_un", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("quebra_72h_unidade", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("quebra_72h_outro", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consultor_id", sa.Integer(), nullable=True),
            sa.Column("observacao", sa.Text(), nullable=True),
            sa.Column("observacao_atualizada_em", sa.DateTime(timezone=True), nullable=True),
            sa.Column("importacao_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
            sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["consultor_id"], ["usuario.id"], name=op.f("fk_pauta_consultor_id_usuario")),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_pauta")),
        )
        with op.batch_alter_table("pauta", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_pauta_aluno"), ["aluno"], unique=False)
            batch_op.create_index(batch_op.f("ix_pauta_ativa"), ["ativa"], unique=False)
            batch_op.create_index(batch_op.f("ix_pauta_atualizado_em_tm"), ["atualizado_em_tm"], unique=False)
            batch_op.create_index(batch_op.f("ix_pauta_categoria_limpa"), ["categoria_limpa"], unique=False)
            batch_op.create_index(batch_op.f("ix_pauta_consultor_id"), ["consultor_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_pauta_quebra_72h_unidade"), ["quebra_72h_unidade"], unique=False)
            batch_op.create_index(batch_op.f("ix_pauta_responsavel_tm"), ["responsavel_tm"], unique=False)
            batch_op.create_index(batch_op.f("ix_pauta_status_tm"), ["status_tm"], unique=False)

    # 4. Tabela pauta_anotacao
    if "pauta_anotacao" not in tabelas_existentes:
        op.create_table(
            "pauta_anotacao",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("pauta_id", sa.Integer(), nullable=False),
            sa.Column("autor_id", sa.Integer(), nullable=True),
            sa.Column("texto", sa.Text(), nullable=False),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["autor_id"], ["usuario.id"], name=op.f("fk_pauta_anotacao_autor_id_usuario")),
            sa.ForeignKeyConstraint(["pauta_id"], ["pauta.id"], name=op.f("fk_pauta_anotacao_pauta_id_pauta"), ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_pauta_anotacao")),
        )
        with op.batch_alter_table("pauta_anotacao", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_pauta_anotacao_pauta_id"), ["pauta_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tabelas_existentes = set(insp.get_table_names())

    if "pauta_anotacao" in tabelas_existentes:
        with op.batch_alter_table("pauta_anotacao", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_pauta_anotacao_pauta_id"))
        op.drop_table("pauta_anotacao")

    if "pauta" in tabelas_existentes:
        with op.batch_alter_table("pauta", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_pauta_status_tm"))
            batch_op.drop_index(batch_op.f("ix_pauta_responsavel_tm"))
            batch_op.drop_index(batch_op.f("ix_pauta_quebra_72h_unidade"))
            batch_op.drop_index(batch_op.f("ix_pauta_consultor_id"))
            batch_op.drop_index(batch_op.f("ix_pauta_categoria_limpa"))
            batch_op.drop_index(batch_op.f("ix_pauta_atualizado_em_tm"))
            batch_op.drop_index(batch_op.f("ix_pauta_ativa"))
            batch_op.drop_index(batch_op.f("ix_pauta_aluno"))
        op.drop_table("pauta")

    if "colaborador_setor" in tabelas_existentes:
        with op.batch_alter_table("colaborador_setor", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_colaborador_setor_nome_normalizado"))
            batch_op.drop_index(batch_op.f("ix_colaborador_setor_nome"))
        op.drop_table("colaborador_setor")

    if "usuario" in tabelas_existentes:
        colunas_usuario = {c["name"] for c in insp.get_columns("usuario")}
        if "senha_hash" in colunas_usuario:
            with op.batch_alter_table("usuario", schema=None) as batch_op:
                batch_op.drop_column("senha_hash")
