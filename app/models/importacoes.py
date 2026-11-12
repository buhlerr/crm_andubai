import enum
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import agora, coluna_enum


class TipoImportacao(enum.StrEnum):
    BASE_ALUNOS = "base_alunos"  # planilha semanal (não é mais importada; fica para o histórico)
    CHECKLIST = "checklist"  # checklistServicoNew.csv (ou leitura direta, no futuro)


class SituacaoImportacao(enum.StrEnum):
    PREVIA = "previa"  # resumo calculado, esperando confirmação
    CONFIRMADA = "confirmada"
    DESCARTADA = "descartada"
    FALHOU = "falhou"


class Importacao(db.Model):
    __tablename__ = "importacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoImportacao] = mapped_column(coluna_enum(TipoImportacao))
    situacao: Mapped[SituacaoImportacao] = mapped_column(
        coluna_enum(SituacaoImportacao), default=SituacaoImportacao.PREVIA
    )
    arquivo_nome: Mapped[str | None] = mapped_column(String(300))
    arquivo_hash: Mapped[str | None] = mapped_column(String(64))  # sha256; conferido na confirmação

    # Período coberto pelo CSV. Item que some só é encerrado se o prazo estiver
    # dentro dele. Vazio = exportação completa.
    periodo_inicio: Mapped[date | None] = mapped_column(Date)
    periodo_fim: Mapped[date | None] = mapped_column(Date)

    iniciada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    iniciada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resumo: Mapped[dict | None] = mapped_column(JSON)  # contagens: novos, atualizados, cancelados...
    # Linhas lidas do arquivo (só as colunas usadas), guardadas entre a prévia e a
    # confirmação para não abrir o Excel de novo. Apagadas ao confirmar ou descartar.
    dados_lidos: Mapped[list | None] = mapped_column(JSON)

    ocorrencias: Mapped[list["OcorrenciaImportacao"]] = relationship(
        back_populates="importacao", cascade="all, delete-orphan"
    )


class Gravidade(enum.StrEnum):
    ERRO = "erro"  # linha não importada, precisa de correção
    AVISO = "aviso"  # importada, mas vale conferir


class TipoOcorrencia(enum.StrEnum):
    SEM_PROGRAMA_ID = "sem_programa_id"
    SEM_ALUNO_ID = "sem_aluno_id"
    PROGRAMA_FALTANDO_NA_PLANILHA = "programa_faltando_na_planilha"  # compra de curso que não está na planilha
    DIVERGENCIA_ALUNO = "divergencia_aluno"  # ID Aluno do CSV != aluno_id do programa
    ALUNO_COM_VARIOS_PROGRAMAS = "aluno_com_varios_programas"  # compra avulsa sem saber a qual juntar
    CONSULTOR_NAO_ENCONTRADO = "consultor_nao_encontrado"
    CONSULTOR_DIVERGENTE = "consultor_divergente"  # CSV mostra outro consultor; vale o da planilha
    PROCEDIMENTO_NOVO = "procedimento_novo"  # entrou no catálogo automaticamente
    SERVICO_NAO_CLASSIFICADO = "servico_nao_classificado"
    VIP_ABAIXO_DA_PONTUACAO = "vip_abaixo_da_pontuacao"  # etapa VIP em programa com menos de 85 pontos
    LINHA_INVALIDA = "linha_invalida"
    CANCELAMENTO_EM_MASSA = "cancelamento_em_massa"  # muitos programas sumiram: arquivo errado ou filtrado?
    ARQUIVO_JA_IMPORTADO = "arquivo_ja_importado"


class OcorrenciaImportacao(db.Model):
    __tablename__ = "ocorrencia_importacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    importacao_id: Mapped[int] = mapped_column(ForeignKey("importacao.id"), index=True)
    gravidade: Mapped[Gravidade] = mapped_column(coluna_enum(Gravidade))
    tipo: Mapped[TipoOcorrencia] = mapped_column(coluna_enum(TipoOcorrencia), index=True)
    linha: Mapped[int | None] = mapped_column(Integer)  # número da linha no arquivo
    chave: Mapped[str | None] = mapped_column(String(100))  # ID envolvido (programa, compra, #...)
    mensagem: Mapped[str] = mapped_column(Text)
    resolvida: Mapped[bool] = mapped_column(Boolean, default=False)
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolvida_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))

    importacao: Mapped["Importacao"] = relationship(back_populates="ocorrencias")
