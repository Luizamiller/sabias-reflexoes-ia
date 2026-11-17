"""Pipeline de um episódio: transcrição → indexação → geração de conteúdo → validação → revisão.

Roda em segundo plano (BackgroundTasks) e registra cada etapa em `etapas`, para a interface
mostrar o andamento. Nada é publicado automaticamente: o episódio termina em "revisao".
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from .. import segredos
from ..config import get_settings
from ..db import SessionLocal
from ..models import Configuracao, Episodio, Etapa, Pacote, Peca, Segmento, agora
from ..search.engine import Fala
from . import conteudo as C
from . import midia as M

log = logging.getLogger("acervo.pipeline")
ETAPAS = ["transcricao", "indexacao", "conteudo", "validacao"]
VOZ_PADRAO = (Path(__file__).resolve().parents[3] / "config" / "voz-da-marca.md")


def voz_da_marca(db: Session) -> str:
    c = db.get(Configuracao, "voz_da_marca")
    return c.valor if c else VOZ_PADRAO.read_text(encoding="utf-8")


def _etapa(db: Session, ep: Episodio, nome: str, status: str, detalhe: str | None = None) -> None:
    e = next((x for x in ep.etapas if x.nome == nome), None)
    if e is None:
        e = Etapa(episodio_id=ep.id, nome=nome)
        ep.etapas.append(e)
    e.status, e.detalhe = status, detalhe
    if status == "rodando":
        e.iniciado_em = agora()
    elif status in ("ok", "erro", "pulada"):
        e.terminado_em = agora()
    db.commit()


def criar_pacote(db: Session, ep: Episodio, dados: dict, motor: str, prompt_versao: str, metricas: dict | None = None) -> Pacote:
    falas = [Fala(s.inicio_s, s.texto) for s in ep.segmentos]
    alertas = C.validar(dados, " ".join(f.texto for f in falas), ep.duracao_s)
    p = Pacote(episodio_id=ep.id, motor=motor, prompt_versao=prompt_versao, alertas=alertas, **(metricas or {}))
    p.pecas = [Peca(tipo=t, ordem=i, conteudo=dados[t], conteudo_original=dados[t]) for i, t in enumerate(C.PECAS)]
    db.add(p)
    return p


def processar(episodio_id: int, cliente_claude=None, transcritor=None) -> None:
    from ..search.service import reindexar  # import tardio evita ciclo

    cfg = get_settings()
    db = SessionLocal()
    try:
        ep = db.get(Episodio, episodio_id)
        for nome in ETAPAS:
            if not any(e.nome == nome for e in ep.etapas):
                ep.etapas.append(Etapa(nome=nome))
        db.commit()

        # 1. transcrição (áudio ou vídeo; vídeo passa pela extração do áudio)
        if ep.origem in ("audio", "video") and not ep.segmentos:
            ep.status = "transcrevendo"
            chave_openai = segredos.chave("openai", db)
            if not chave_openai and transcritor is None:
                raise RuntimeError("Sem chave da OpenAI para transcrever. Cadastre em Configurações › Chaves de API e reprocesse.")
            _etapa(db, ep, "transcricao", "rodando", "Preparando a mídia")
            dica = f"Podcast Às Sábias Reflexões, episódio {ep.numero}: {ep.titulo}. Convidados: {ep.convidados}."
            falas, total = M.transcrever(cfg.storage_dir / ep.audio_arquivo, chave_openai or "", dica,
                                         progresso=lambda d: _etapa(db, ep, "transcricao", "rodando", d), transcritor=transcritor)
            if not falas:
                raise RuntimeError("A transcrição voltou vazia: o arquivo tem fala audível?")
            ep.segmentos = [Segmento(inicio_s=f.inicio, texto=f.texto) for f in falas]
            ep.duracao_s = int(total) or falas[-1].inicio + 10
            _etapa(db, ep, "transcricao", "ok", f"{len(falas)} segmentos · {ep.duracao_s // 60} min")
        else:
            _etapa(db, ep, "transcricao", "pulada", "Transcrição recebida pronta")

        # 2. indexação para a busca
        ep.status = "indexando"
        _etapa(db, ep, "indexacao", "rodando")
        n = reindexar(db)
        _etapa(db, ep, "indexacao", "ok", f"{n} trechos no acervo")

        # 3. conteúdo
        ep.status = "gerando"
        falas = [Fala(s.inicio_s, s.texto) for s in ep.segmentos]
        _etapa(db, ep, "conteudo", "rodando")
        if segredos.chave("anthropic", db) or cliente_claude is not None:
            dados, metricas = C.gerar_com_claude(ep.titulo, ep.numero, ep.convidados, falas, voz_da_marca(db), "v1", cliente_claude)
            motor, versao = "claude", "v1"
        else:
            dados, metricas = C.rascunho_deterministico(ep.titulo, falas, ep.duracao_s), {}
            motor, versao = "rascunho_deterministico", "extrativo-v1"
        _etapa(db, ep, "conteudo", "ok", motor)

        # 4. validação
        _etapa(db, ep, "validacao", "rodando")
        p = criar_pacote(db, ep, dados, motor, versao, metricas)
        ep.status = "revisao"
        _etapa(db, ep, "validacao", "ok", f"{len(p.alertas)} alerta(s) para o revisor")
        db.commit()
    except Exception as exc:
        log.exception("falha ao processar episódio %s", episodio_id)
        db.rollback()
        ep = db.get(Episodio, episodio_id)
        if ep:
            ep.status, ep.erro = "erro", str(exc)[:500]
            rodando = next((e for e in ep.etapas if e.status == "rodando"), None)
            if rodando:
                rodando.status, rodando.detalhe, rodando.terminado_em = "erro", str(exc)[:300], agora()
            db.commit()
    finally:
        db.close()
