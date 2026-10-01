import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import ComDatas, agora, coluna_enum

PONTUACAO_VIP = Decimal("85")


class Papel(enum.StrEnum):
    CONSULTOR = "consultor"
    ESTAGIARIO = "estagiario"
    ADMIN = "admin"


from werkzeug.security import check_password_hash, generate_password_hash

SENHA_MINIMA = 10


class VisaoFila(enum.StrEnum):
    LISTA = "lista"
    KANBAN = "kanban"  # colunas por status
    QUADRO = "quadro"  # um cartão por aluno
    CALENDARIO = "calendario"


class Usuario(ComDatas, db.Model):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    papel: Mapped[Papel] = mapped_column(coluna_enum(Papel), default=Papel.CONSULTOR)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Última visualização das filas escolhida pela pessoa.
    visao_fila: Mapped[VisaoFila] = mapped_column(coluna_enum(VisaoFila), default=VisaoFila.LISTA, server_default="lista")
    # Identificador da conta no Microsoft 365 (Entra ID), gravado no primeiro login.
    microsoft_oid: Mapped[str | None] = mapped_column(String(64), unique=True)
    # "Organizar por" escolhido na lista e no quadro (valores de consultas.Organizar; texto, validado no código).
    organizar_lista: Mapped[str] = mapped_column(String(20), default="data", server_default="data")
    organizar_quadro: Mapped[str] = mapped_column(String(20), default="embarque", server_default="embarque")
    # Hash da senha para autenticação local por e-mail e senha.
    senha_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def definir_senha(self, senha: str) -> None:
        if not senha or not senha.strip():
            raise ValueError("A senha não pode ser vazia.")
        if len(senha.strip()) < SENHA_MINIMA:
            raise ValueError(f"A senha deve ter pelo menos {SENHA_MINIMA} caracteres.")
        self.senha_hash = generate_password_hash(senha.strip())

    def verificar_senha(self, senha: str) -> bool:
        if not self.senha_hash or not senha:
            return False
        return check_password_hash(self.senha_hash, senha.strip())


class ApelidoConsultor(db.Model):
    """Exceção manual: nome do consultor como aparece na planilha -> usuário.
    Editável pela interface. Sem usuário = "sem consultor" de propósito."""

    __tablename__ = "apelido_consultor"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto_planilha: Mapped[str] = mapped_column(String(200))
    texto_normalizado: Mapped[str] = mapped_column(String(200), unique=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    usuario: Mapped["Usuario | None"] = relationship(foreign_keys=[usuario_id])


class Aluno(ComDatas, db.Model):
    __tablename__ = "aluno"

    id: Mapped[int] = mapped_column(primary_key=True)
    aluno_id_egali: Mapped[str] = mapped_column(String(20), unique=True)
    nome: Mapped[str] = mapped_column(String(300))

    # Público teen: a equipe de Teens é separada do Suporte ao Aluno, mas usa as mesmas
    # estruturas no TM. O aluno é marcado (não excluído) pela regra de app/publico_teen.py.
    teen: Mapped[bool] = mapped_column(Boolean, default=False, server_default=db.false(), index=True)
    teen_motivo: Mapped[str | None] = mapped_column(String(300))
    tags_egali: Mapped[str | None] = mapped_column(String(500))  # coluna Tags do checklist

    programas: Mapped[list["Programa"]] = relationship(back_populates="aluno", foreign_keys="Programa.aluno_id")


class TipoPrograma(enum.StrEnum):
    NORMAL = "normal"  # veio da planilha semanal
    SO_VISTO = "so_visto"  # criado a partir do checklist: aluno que só comprou visto


class SituacaoPrograma(enum.StrEnum):
    ATIVO = "ativo"
    CANCELADO = "cancelado"  # sumiu da planilha
    INCORPORADO = "incorporado"  # programa só de visto que foi juntado a um programa com curso


class Programa(ComDatas, db.Model):
    __tablename__ = "programa"
    __table_args__ = (
        # No máximo um programa "só de visto" ativo por aluno.
        Index(
            "uq_programa_so_visto_ativo_por_aluno",
            "aluno_id",
            unique=True,
            sqlite_where=db.text("tipo = 'so_visto' AND situacao = 'ativo'"),
            postgresql_where=db.text("tipo = 'so_visto' AND situacao = 'ativo'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Vazio só nos programas "só de visto", que não existem na planilha.
    programa_id_egali: Mapped[str | None] = mapped_column(String(20), unique=True)
    aluno_id: Mapped[int] = mapped_column(ForeignKey("aluno.id"), index=True)
    tipo: Mapped[TipoPrograma] = mapped_column(coluna_enum(TipoPrograma), default=TipoPrograma.NORMAL)

    # Consultor como veio da planilha (ou do CSV, nos programas só de visto) e o usuário resolvido.
    consultor_texto: Mapped[str | None] = mapped_column(String(200))
    consultor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), index=True)

    mes_embarque: Mapped[date | None] = mapped_column(Date)
    data_embarque: Mapped[date | None] = mapped_column(Date)
    visto_normalizado: Mapped[str | None] = mapped_column(String(200))
    pais: Mapped[str | None] = mapped_column(String(100))
    cidade: Mapped[str | None] = mapped_column(String(100))
    escola: Mapped[str | None] = mapped_column(String(300))
    acomodacao: Mapped[str | None] = mapped_column(String(300))
    grupo: Mapped[str | None] = mapped_column(String(300))
    pontuacao: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))  # coluna pt_prog
    servicos_egali: Mapped[str | None] = mapped_column(Text)  # coluna servico_name (lista separada por vírgula)
    tags_egali: Mapped[str | None] = mapped_column(String(500))  # coluna tags

    situacao: Mapped[SituacaoPrograma] = mapped_column(
        coluna_enum(SituacaoPrograma), default=SituacaoPrograma.ATIVO, index=True
    )
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reativado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    incorporado_ao_programa_id: Mapped[int | None] = mapped_column(ForeignKey("programa.id"))
    ultima_importacao_id: Mapped[int | None] = mapped_column(ForeignKey("importacao.id"))

    aluno: Mapped["Aluno"] = relationship(back_populates="programas", foreign_keys=[aluno_id])
    consultor: Mapped["Usuario | None"] = relationship(foreign_keys=[consultor_id])
    compras: Mapped[list["Compra"]] = relationship(back_populates="programa")
    tarefas: Mapped[list["Tarefa"]] = relationship(back_populates="programa")  # noqa: F821

    @property
    def vip(self) -> bool:
        return self.pontuacao is not None and self.pontuacao >= PONTUACAO_VIP

    @property
    def ativo(self) -> bool:
        return self.situacao == SituacaoPrograma.ATIVO


class OrigemCompra(enum.StrEnum):
    PLANILHA = "planilha"  # está na célula compra_id do programa
    CHECKLIST = "checklist"  # compra avulsa (visto, transfer...) juntada pelo CSV


class Compra(db.Model):
    __tablename__ = "compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id_egali: Mapped[str] = mapped_column(String(20), unique=True)
    # Vazio quando a compra foi desligada do programa (saiu da célula compra_id).
    programa_id: Mapped[int | None] = mapped_column(ForeignKey("programa.id"), index=True)
    origem: Mapped[OrigemCompra] = mapped_column(coluna_enum(OrigemCompra), default=OrigemCompra.PLANILHA)
    servico: Mapped[str | None] = mapped_column(String(200))  # coluna "Serviço" do CSV
    ligada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=agora)
    desligada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    programa: Mapped["Programa | None"] = relationship(back_populates="compras")


class CategoriaServico(enum.StrEnum):
    CURSO = "curso"  # é um programa e precisa estar na planilha
    VISTO = "visto"  # pode vir sozinho (programa só de visto)
    AVULSO = "avulso"  # serviço extra, sempre junto de um programa (transfer, seguro...)
    IGNORADO = "ignorado"  # compra sem acompanhamento (C. Curso, valores extras...): a importação pula
    NAO_CLASSIFICADO = "nao_classificado"


class ServicoEgali(db.Model):
    """Classificação dos serviços do sistema Egali, editável pela interface.
    Decide o que fazer com uma compra do checklist que não está na planilha."""

    __tablename__ = "servico_egali"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    nome_normalizado: Mapped[str] = mapped_column(String(200), unique=True)
    categoria: Mapped[CategoriaServico] = mapped_column(
        coluna_enum(CategoriaServico), default=CategoriaServico.NAO_CLASSIFICADO
    )
    # Aluno com este serviço é do público teen (ex.: Summer Schools).
    teen: Mapped[bool] = mapped_column(Boolean, default=False, server_default=db.false())
    observacao: Mapped[str | None] = mapped_column(Text)


class ConsultorTeen(db.Model):
    """Consultor da equipe de Teens: aluno com ele como consultor é do público teen. Editável na tela."""

    __tablename__ = "consultor_teen"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    nome_normalizado: Mapped[str] = mapped_column(String(200), unique=True)
