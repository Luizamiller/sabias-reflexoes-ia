from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def agora() -> datetime:
    return datetime.now(UTC)


class Episodio(Base):
    __tablename__ = "episodios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(20), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    convidados: Mapped[str] = mapped_column(String(200), default="Sem convidados")
    # recebido | transcrevendo | indexando | gerando | revisao | publicado | erro
    status: Mapped[str] = mapped_column(String(20), default="recebido", index=True)
    origem: Mapped[str] = mapped_column(String(20), default="transcricao")  # transcricao | audio | video | n8n | exemplo
    audio_arquivo: Mapped[str | None] = mapped_column(String(260), nullable=True)  # arquivo de mídia guardado (áudio ou vídeo)
    midia_tipo: Mapped[str | None] = mapped_column(String(10), nullable=True)      # audio | video
    midia_nome: Mapped[str | None] = mapped_column(String(260), nullable=True)     # nome original enviado
    midia_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duracao_s: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)
    segmentos: Mapped[list[Segmento]] = relationship(cascade="all, delete-orphan", order_by="Segmento.inicio_s", lazy="selectin")
    etapas: Mapped[list[Etapa]] = relationship(cascade="all, delete-orphan", order_by="Etapa.id", lazy="selectin")


class Segmento(Base):
    """Uma fala com timestamp — saída do Whisper ou linha `[mm:ss] texto` da transcrição."""
    __tablename__ = "segmentos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episodio_id: Mapped[int] = mapped_column(ForeignKey("episodios.id", ondelete="CASCADE"), index=True)
    inicio_s: Mapped[int] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(Text)


class Etapa(Base):
    """Andamento do pipeline, para a interface mostrar o que está acontecendo."""
    __tablename__ = "etapas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episodio_id: Mapped[int] = mapped_column(ForeignKey("episodios.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente | rodando | ok | erro | pulada
    detalhe: Mapped[str | None] = mapped_column(Text, nullable=True)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Pacote(Base):
    """As 8 peças geradas a partir de um episódio, com a versão do prompt e os alertas de validação."""
    __tablename__ = "pacotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episodio_id: Mapped[int] = mapped_column(ForeignKey("episodios.id", ondelete="CASCADE"), index=True)
    motor: Mapped[str] = mapped_column(String(30))  # claude | n8n | rascunho_deterministico
    prompt_versao: Mapped[str] = mapped_column(String(20))
    alertas: Mapped[list] = mapped_column(JSON, default=list)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0)
    tempo_s: Mapped[float] = mapped_column(Float, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    pecas: Mapped[list[Peca]] = relationship(cascade="all, delete-orphan", order_by="Peca.ordem", lazy="selectin")


class Peca(Base):
    __tablename__ = "pecas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pacote_id: Mapped[int] = mapped_column(ForeignKey("pacotes.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))
    ordem: Mapped[int] = mapped_column(Integer)
    conteudo: Mapped[dict | list | str] = mapped_column(JSON)
    conteudo_original: Mapped[dict | list | str] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente | aprovada | editada | rejeitada
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Pergunta(Base):
    __tablename__ = "perguntas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pergunta: Mapped[str] = mapped_column(Text)
    resposta: Mapped[str] = mapped_column(Text, default="")
    fontes: Mapped[list] = mapped_column(JSON, default=list)
    citacoes_invalidas: Mapped[list] = mapped_column(JSON, default=list)
    motor: Mapped[str] = mapped_column(String(30))
    chamou_modelo: Mapped[bool] = mapped_column(default=False)
    util: Mapped[bool | None] = mapped_column(nullable=True)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class Configuracao(Base):
    __tablename__ = "configuracoes"
    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
