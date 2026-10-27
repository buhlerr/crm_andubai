"""Modelos para gestão de Pautas de Comunicação Interna (TM Egali).

Armazena as pautas sincronizadas a partir dos arquivos CSV/MHTML exportados do TM,
garantindo persistência de dados internos (observações, anotações de consultores,
atribuições manuais e histórico) entre sucessivas reimportações.
"""

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import ComDatas, agora


class Pauta(ComDatas, db.Model):
    """Uma pauta de comunicação interna do sistema TM Egali.

    Campos do sistema corporativo são atualizados a cada nova importação via Upsert.
    Campos internos da unidade (observacao, consultor_id, anotações) nunca são apagados
    nem sobrescritos pela importação.
    """

    __tablename__ = "pauta"

    # ID oficial do protocolo no TM (ex: 3104087)
    id: Mapped[int] = mapped_column(primary_key=True)

    # Identificação e classificação do TM
    categoria: Mapped[str] = mapped_column(String(250))
    categoria_limpa: Mapped[str | None] = mapped_column(String(250), index=True)
    pauta_titulo: Mapped[str] = mapped_column(String(500))
    aluno: Mapped[str | None] = mapped_column(String(200), index=True)
    status_tm: Mapped[str] = mapped_column(String(100), index=True)  # Em aberto, Aguardando retorno..., etc.
    responsavel_tm: Mapped[str | None] = mapped_column(String(200), index=True)

    # Rastreamento de autoria e datas no TM
    criado_em_tm: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_por_tm: Mapped[str | None] = mapped_column(String(200))
    atualizado_em_tm: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    atualizado_por_tm: Mapped[str | None] = mapped_column(String(200))

    # Tags e SLA corporativo
    tag: Mapped[str | None] = mapped_column(String(100))  # Atrasada, Atrasada 72h +
    tempo_inativo_texto: Mapped[str | None] = mapped_column(String(50))  # "01:16:36", "145:33:42"
    tempo_inativo_horas: Mapped[int] = mapped_column(Integer, default=0)
    prazo_sla_horas: Mapped[int | None] = mapped_column(Integer)  # SLA em horas da categoria

    # Inteligência de Unidade e Setores
    un_atualizou: Mapped[str | None] = mapped_column(String(100))
    un_responsavel: Mapped[str | None] = mapped_column(String(100))
    un_criou: Mapped[str | None] = mapped_column(String(100))
    un_final: Mapped[str | None] = mapped_column(String(200))
    atualizada_un: Mapped[bool] = mapped_column(Boolean, default=False)  # True se UN Atualizou == 'AN e Dubai'

    # Indicadores de quebra de 72h
    quebra_72h_unidade: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    quebra_72h_outro: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ciclo de vida e arquivamento
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- CAMPOS INTERNOS DO CRM (Preservados perpetuamente entre importações) ---
    ESTADOS_INTERNOS = {
        "acao": "Ação necessária",
        "aguardando": "Aguardando retorno",
        "acompanhamento": "Em acompanhamento",
        "finalizada": "Finalizada",
    }
    estado_interno: Mapped[str] = mapped_column(String(30), default="acao", index=True)
    estado_interno_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, nullable=False)
    estado_interno_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    consultor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    observacao: Mapped[str | None] = mapped_column(Text)
    observacao_atualizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Vínculo com a última importação
    importacao_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    # Relacionamentos
    consultor: Mapped["Usuario | None"] = relationship(foreign_keys=[consultor_id])  # noqa: F821
    estado_interno_por: Mapped["Usuario | None"] = relationship(foreign_keys=[estado_interno_por_id])  # noqa: F821
    anotacoes: Mapped[list["PautaAnotacao"]] = relationship(
        back_populates="pauta", cascade="all, delete-orphan", order_by="PautaAnotacao.criado_em.desc()"
    )

    @property
    def estado_interno_rotulo(self) -> str:
        return self.ESTADOS_INTERNOS.get(self.estado_interno, self.ESTADOS_INTERNOS["acao"])

    @property
    def eh_responsabilidade_nossa(self) -> bool:
        """Indica se a nossa unidade (AN e Dubai) é a responsável oficial no TM."""
        return self.un_responsavel == "AN e Dubai"

    @property
    def pendente_de_acao_nossa(self) -> bool:
        """Indica se há ação imediata requerida da nossa equipe."""
        # Se formos responsáveis e não atualizamos por último, ou pauta em aberto sem resposta nossa
        if self.eh_responsabilidade_nossa and not self.atualizada_un:
            return True
        return False

    @property
    def subestado_aguardando(self) -> str:
        """Determina a subdivisão para o status 'Aguardando retorno do aluno/fornecedor'.

        Retorna:
        - 'nossa_acao': Responsável é nossa UN e a última atualização veio de fora.
        - 'nosso_aluno': Responsável é nossa UN e nós fomos os últimos a atualizar (esperando aluno).
        - 'outro_setor': Responsável é outro setor (estamos apenas acompanhando/cobrando).
        """
        if "aguardando" not in (self.status_tm or "").lower():
            return "outro"
        if self.eh_responsabilidade_nossa:
            return "nosso_aluno" if self.atualizada_un else "nossa_acao"
        return "outro_setor"


class PautaAnotacao(db.Model):
    """Comentário ou histórico de anotação interna sobre uma pauta.

    Nunca tocado por importações. Permite múltiplos registros ao longo do tempo.
    """

    __tablename__ = "pauta_anotacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    pauta_id: Mapped[int] = mapped_column(ForeignKey("pauta.id", ondelete="CASCADE"), index=True)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    pauta: Mapped["Pauta"] = relationship(back_populates="anotacoes")
    autor: Mapped["Usuario | None"] = relationship()  # noqa: F821


class PautaHistorico(db.Model):
    """Histórico das movimentações internas do painel, independente do TM."""

    __tablename__ = "pauta_historico"

    id: Mapped[int] = mapped_column(primary_key=True)
    pauta_id: Mapped[int] = mapped_column(ForeignKey("pauta.id", ondelete="CASCADE"), index=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(30))
    estado_novo: Mapped[str] = mapped_column(String(30))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    pauta: Mapped["Pauta"] = relationship()
    usuario: Mapped["Usuario | None"] = relationship()


class ColaboradorSetor(db.Model):
    """Tabela auxiliar de mapeamento de colaboradores e seus respectivos setores.

    Substitui a antiga aba 'Auxiliar!A:B' do Excel, permitindo identificar a unidade
    de quem abriu, é responsável ou movimentou a pauta.
    """

    __tablename__ = "colaborador_setor"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    nome_normalizado: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    setor: Mapped[str] = mapped_column(String(150))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
