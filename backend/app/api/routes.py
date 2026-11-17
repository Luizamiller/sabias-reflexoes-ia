from __future__ import annotations

import hmac
import json
import time
import uuid
from datetime import UTC
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import segredos
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..eval import relatorio
from ..models import Configuracao, Episodio, Pacote, Peca, Pergunta, Segmento, agora
from ..pipeline import conteudo as C
from ..pipeline import midia as M
from ..pipeline.exportar import FORMATOS, exportar
from ..pipeline.processar import criar_pacote, processar, voz_da_marca
from ..search.engine import ler_transcricao, mmss, segundos
from ..search.service import buscar, fonte_api, indice, reindexar, responder_stream

router = APIRouter(prefix="/api")


def iso(dt):
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def _pacote(db: Session, eid: int) -> Pacote | None:
    return db.scalar(select(Pacote).where(Pacote.episodio_id == eid).order_by(Pacote.id.desc()).limit(1))


def resumo_ep(db: Session, e: Episodio) -> dict:
    p = _pacote(db, e.id)
    revisadas = sum(1 for x in p.pecas if x.status != "pendente") if p else 0
    return {"id": e.id, "numero": e.numero, "titulo": e.titulo, "convidados": e.convidados, "status": e.status,
            "origem": e.origem, "midia_tipo": e.midia_tipo, "duracao_s": e.duracao_s, "criado_em": iso(e.criado_em), "atualizado_em": iso(e.atualizado_em),
            "pecas_revisadas": revisadas, "pecas_total": len(p.pecas) if p else 0, "alertas": len(p.alertas) if p else 0,
            "exemplo": "[EXEMPLO FICTÍCIO]" in e.titulo}


def pacote_api(p: Pacote | None) -> dict | None:
    if not p:
        return None
    return {"id": p.id, "motor": p.motor, "prompt_versao": p.prompt_versao, "alertas": p.alertas,
            "tokens_entrada": p.tokens_entrada, "tokens_saida": p.tokens_saida, "tempo_s": p.tempo_s, "criado_em": iso(p.criado_em),
            "pecas": [{"id": x.id, "tipo": x.tipo, "rotulo": C.ROTULOS[x.tipo], "conteudo": x.conteudo, "status": x.status,
                       "editada": x.conteudo != x.conteudo_original, "revisado_em": iso(x.revisado_em)} for x in p.pecas]}


# ------------------------------------------------------------------ status e biblioteca
@router.get("/health")
def health(db: Session = Depends(get_db)):
    cfg = get_settings()
    claude, openai, voyage = (bool(segredos.chave(p, db)) for p in ("anthropic", "openai", "voyage"))
    emb = cfg.provedor_embeddings
    return {"status": "ok", "integracoes": {
        "claude": claude, "whisper": openai, "n8n": bool(cfg.n8n_token), "ffmpeg": bool(M.ffmpeg()),
        "embeddings": emb if emb == "local" or (emb == "voyage" and voyage) or (emb == "openai" and openai) else "local"}}


@router.get("/episodios")
def listar(db: Session = Depends(get_db)):
    eps = db.scalars(select(Episodio).order_by(Episodio.id.desc())).all()
    total_p = db.scalar(select(func.count()).select_from(Pergunta)) or 0
    return {"episodios": [resumo_ep(db, e) for e in eps],
            "totais": {"episodios": len(eps), "horas": round(sum(e.duracao_s for e in eps) / 3600, 2),
                       "trechos": len(indice(db).trechos), "perguntas": total_p,
                       "em_revisao": sum(1 for e in eps if e.status == "revisao")}}


@router.get("/episodios/{eid}")
def ver(eid: int, db: Session = Depends(get_db)):
    e = db.get(Episodio, eid)
    if not e:
        raise HTTPException(404, "Episódio não encontrado.")
    return resumo_ep(db, e) | {
        "erro": e.erro, "tem_audio": bool(e.audio_arquivo), "tem_midia": bool(e.audio_arquivo),
        "midia": {"tipo": e.midia_tipo or "audio", "nome": e.midia_nome, "bytes": e.midia_bytes} if e.audio_arquivo else None,
        "segmentos": [{"id": s.id, "inicio": mmss(s.inicio_s), "inicio_s": s.inicio_s, "texto": s.texto} for s in e.segmentos],
        "etapas": [{"nome": x.nome, "status": x.status, "detalhe": x.detalhe, "iniciado_em": iso(x.iniciado_em),
                    "terminado_em": iso(x.terminado_em)} for x in e.etapas],
        "pacote": pacote_api(_pacote(db, e.id)),
    }


@router.get("/episodios/{eid}/midia")
@router.get("/episodios/{eid}/audio")
def midia(eid: int, db: Session = Depends(get_db)):
    """Áudio ou vídeo original, com suporte a Range (o player pula para qualquer ponto sem baixar tudo)."""
    e = db.get(Episodio, eid)
    caminho = get_settings().storage_dir / e.audio_arquivo if e and e.audio_arquivo else None
    if not caminho or not caminho.exists():
        raise HTTPException(404, "Este episódio não tem mídia armazenada.")
    return FileResponse(caminho, filename=e.midia_nome or caminho.name, content_disposition_type="inline")


@router.get("/episodios/{eid}/exportar")
def exportar_ep(eid: int, formato: str = "txt", db: Session = Depends(get_db)):
    e = db.get(Episodio, eid)
    if not e:
        raise HTTPException(404, "Episódio não encontrado.")
    if formato not in FORMATOS:
        raise HTTPException(422, f"Formato inválido. Use: {', '.join(FORMATOS)}.")
    texto, tipo = exportar(e, _pacote(db, e.id), formato)
    nome = f"episodio-{e.numero}.{FORMATOS[formato]}".replace(" ", "-")
    return PlainTextResponse(texto, media_type=f"{tipo}; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/episodios", status_code=201)
async def novo(background: BackgroundTasks, titulo: str = Form(..., min_length=2, max_length=200),
               numero: str = Form(..., min_length=1, max_length=20), convidados: str = Form("Sem convidados", max_length=200),
               transcricao: str | None = Form(None), arquivo: UploadFile | None = File(None), db: Session = Depends(get_db)):
    """Aceita transcrição pronta (`[mm:ss] fala`, colada ou em .txt) ou áudio/vídeo (transcrito com Whisper)."""
    cfg = get_settings()
    ep = Episodio(titulo=titulo.strip(), numero=numero.strip(), convidados=convidados.strip() or "Sem convidados")
    texto = transcricao
    if arquivo is not None and arquivo.filename:
        nome = arquivo.filename
        if nome.lower().endswith(".txt"):
            texto = (await arquivo.read()).decode("utf-8", errors="replace")
        else:
            tipo = M.tipo_da_midia(nome, arquivo.content_type)
            if not tipo:
                raise HTTPException(415, "Formato não reconhecido. Envie áudio (MP3, M4A, WAV…), vídeo (MP4, MOV, MKV, WEBM…) ou .txt.")
            if not segredos.chave("openai", db):
                raise HTTPException(422, "Para transcrever, cadastre a chave da OpenAI em Configurações › Chaves de API. "
                                         "Ou envie a transcrição pronta.")
            if tipo == "video" and not M.ffmpeg():
                raise HTTPException(422, "Para vídeo é preciso o ffmpeg no servidor.")
            cfg.storage_dir.mkdir(parents=True, exist_ok=True)
            destino = cfg.storage_dir / f"{uuid.uuid4().hex}{Path(nome).suffix.lower()}"
            limite, total = cfg.limite_midia_mb * 1024 * 1024, 0
            try:
                with destino.open("wb") as f:  # direto para o disco, em blocos: vídeos longos não passam pela memória
                    while bloco := await arquivo.read(1024 * 1024):
                        total += len(bloco)
                        if total > limite:
                            raise HTTPException(413, f"Arquivo acima de {cfg.limite_midia_mb} MB.")
                        f.write(bloco)
            except BaseException:
                destino.unlink(missing_ok=True)
                raise
            if total == 0:
                destino.unlink(missing_ok=True)
                raise HTTPException(422, "O arquivo chegou vazio.")
            ep.audio_arquivo, ep.midia_tipo, ep.midia_nome, ep.midia_bytes = destino.name, tipo, nome[-260:], total
            ep.origem = tipo
    if ep.origem not in ("audio", "video"):
        if not texto:
            raise HTTPException(422, "Envie a transcrição (colada ou .txt) ou um arquivo de áudio ou vídeo.")
        _, falas = ler_transcricao(texto)
        if not falas:
            raise HTTPException(422, "Nenhuma linha no formato [mm:ss] texto foi encontrada na transcrição.")
        ep.segmentos = [Segmento(inicio_s=f.inicio, texto=f.texto) for f in falas]
        ep.duracao_s = falas[-1].inicio + 15
    db.add(ep)
    db.commit()
    background.add_task(processar, ep.id)
    return resumo_ep(db, ep)


@router.post("/episodios/{eid}/reprocessar")
def reprocessar(eid: int, background: BackgroundTasks, transcrever: bool = False, db: Session = Depends(get_db)):
    """Gera o pacote de novo (com o Claude, se houver chave). `transcrever=true` refaz também a transcrição da mídia."""
    e = db.get(Episodio, eid)
    if not e:
        raise HTTPException(404, "Episódio não encontrado.")
    if e.status in ("transcrevendo", "indexando", "gerando"):
        raise HTTPException(409, "O episódio já está sendo processado.")
    if transcrever:
        if not e.audio_arquivo:
            raise HTTPException(422, "Este episódio não tem mídia para transcrever.")
        e.segmentos.clear()
    e.status, e.erro = "recebido", None
    for x in e.etapas:
        x.status, x.detalhe = "pendente", None
    db.commit()
    background.add_task(processar, e.id)
    return resumo_ep(db, e)


@router.delete("/episodios/{eid}", status_code=204)
def apagar(eid: int, db: Session = Depends(get_db)):
    e = db.get(Episodio, eid)
    if not e:
        raise HTTPException(404, "Episódio não encontrado.")
    for p in db.scalars(select(Pacote).where(Pacote.episodio_id == eid)):
        db.delete(p)
    db.flush()  # pacotes antes do episódio (sem relação ORM entre eles, a ordem não é garantida)
    arquivo = e.audio_arquivo
    db.delete(e)
    db.commit()
    if arquivo:
        (get_settings().storage_dir / arquivo).unlink(missing_ok=True)
    reindexar(db)


class SegmentoIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


@router.patch("/segmentos/{sid}")
def editar_segmento(sid: int, body: SegmentoIn, db: Session = Depends(get_db)):
    """Correção manual da transcrição (nome próprio, palavra mal ouvida). A busca é reindexada na hora."""
    s = db.get(Segmento, sid)
    if not s:
        raise HTTPException(404, "Trecho não encontrado.")
    s.texto = body.texto.strip()
    db.commit()
    reindexar(db)
    return {"id": s.id, "inicio": mmss(s.inicio_s), "inicio_s": s.inicio_s, "texto": s.texto}


# ------------------------------------------------------------------ revisão humana
class RevisaoIn(BaseModel):
    acao: Literal["aprovar", "rejeitar", "editar", "reabrir"]
    conteudo: dict | list | str | None = None


@router.post("/pecas/{pid}")
def revisar(pid: int, body: RevisaoIn, db: Session = Depends(get_db)):
    p = db.get(Peca, pid)
    if not p:
        raise HTTPException(404, "Peça não encontrada.")
    if body.acao == "editar":
        if body.conteudo is None:
            raise HTTPException(422, "Envie o conteúdo editado.")
        p.conteudo, p.status = body.conteudo, "editada"
    elif body.acao == "reabrir":
        p.status = "pendente"
    else:
        p.status = "aprovada" if body.acao == "aprovar" else "rejeitada"
    p.revisado_em = agora() if p.status != "pendente" else None
    pacote = db.get(Pacote, p.pacote_id)
    ep = db.get(Episodio, pacote.episodio_id)
    todas = all(x.status != "pendente" for x in pacote.pecas)
    ep.status = "publicado" if todas and any(x.status in ("aprovada", "editada") for x in pacote.pecas) else "revisao"
    db.commit()
    return ver(ep.id, db)


# ------------------------------------------------------------------ busca e assistente
@router.get("/busca")
def busca(q: str, db: Session = Depends(get_db)):
    if len(q.strip()) < 2:
        return {"resultados": []}
    t0 = time.perf_counter()
    res, _ = buscar(db, q.strip(), k=10, reescrever=False)
    return {"resultados": [fonte_api(r) for r in res], "ms": round((time.perf_counter() - t0) * 1000, 1),
            "versao": indice(db).versao}


class PerguntaIn(BaseModel):
    pergunta: str = Field(min_length=3, max_length=500)


@router.post("/assistente")
def perguntar(body: PerguntaIn):
    """Server-Sent Events: fontes primeiro, depois o texto em pedaços, depois o fechamento com a verificação de citações."""
    def eventos():
        db = SessionLocal()
        t0 = time.perf_counter()
        try:
            for ev in responder_stream(db, body.pergunta.strip()):
                if ev["tipo"] == "fontes":
                    fontes = ev["fontes"]
                if ev["tipo"] == "fim":
                    reg = Pergunta(pergunta=body.pergunta.strip(), resposta=ev["resposta"], fontes=[f["citacao"] for f in fontes],
                                   citacoes_invalidas=ev["citacoes_invalidas"], motor=ev["motor"], chamou_modelo=ev["chamou_modelo"],
                                   ms=round((time.perf_counter() - t0) * 1000))
                    db.add(reg)
                    db.commit()
                    ev = ev | {"pergunta_id": reg.id}
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'tipo': 'erro', 'mensagem': 'Não foi possível responder agora. Tente de novo.'})}\n\n"
        finally:
            db.close()
    return StreamingResponse(eventos(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class AvaliarIn(BaseModel):
    util: bool


@router.post("/perguntas/{pid}/avaliacao")
def avaliar_resposta(pid: int, body: AvaliarIn, db: Session = Depends(get_db)):
    p = db.get(Pergunta, pid)
    if not p:
        raise HTTPException(404, "Pergunta não encontrada.")
    p.util = body.util
    db.commit()
    return {"ok": True}


@router.get("/perguntas")
def historico(db: Session = Depends(get_db)):
    rows = db.scalars(select(Pergunta).order_by(Pergunta.id.desc()).limit(50)).all()
    return [{"id": p.id, "pergunta": p.pergunta, "motor": p.motor, "chamou_modelo": p.chamou_modelo, "fontes": p.fontes,
             "citacoes_invalidas": p.citacoes_invalidas, "util": p.util, "ms": p.ms, "criado_em": iso(p.criado_em)} for p in rows]


@router.get("/avaliacao")
def avaliacao():
    return relatorio()


# ------------------------------------------------------------------ configuração
@router.get("/config")
def config(db: Session = Depends(get_db)):
    system, user = C.carregar_prompt("v1")
    changelog = (C.PROMPTS_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    return {"voz_da_marca": voz_da_marca(db), "prompt": {"versao": "v1", "system": system, "user": user}, "changelog": changelog}


class VozIn(BaseModel):
    texto: str = Field(min_length=10, max_length=8000)


@router.put("/config/voz")
def salvar_voz(body: VozIn, db: Session = Depends(get_db)):
    c = db.get(Configuracao, "voz_da_marca") or Configuracao(chave="voz_da_marca", valor="")
    c.valor = body.texto
    db.merge(c)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ chaves de API
Provedor = Literal["anthropic", "openai", "voyage"]


class ChaveIn(BaseModel):
    valor: str = Field(min_length=1, max_length=400)


@router.get("/config/chaves")
def listar_chaves(db: Session = Depends(get_db)):
    """Só máscaras: a chave inteira nunca sai do servidor."""
    return segredos.status(db)


@router.put("/config/chaves/{provedor}")
def salvar_chave(provedor: Provedor, body: ChaveIn, testar: bool = True, db: Session = Depends(get_db)):
    valor = body.valor.strip()
    if erro := segredos.validar_formato(provedor, valor):
        raise HTTPException(422, erro)
    if testar:
        ok, msg = segredos.testar(provedor, valor)
        if not ok:
            raise HTTPException(422, msg)
    segredos.salvar(db, provedor, valor)
    return {"chaves": segredos.status(db), "mensagem": "Chave salva e cifrada."}


@router.delete("/config/chaves/{provedor}")
def remover_chave(provedor: Provedor, db: Session = Depends(get_db)):
    segredos.remover(db, provedor)
    return {"chaves": segredos.status(db)}


@router.post("/config/chaves/{provedor}/testar")
def testar_chave(provedor: Provedor, db: Session = Depends(get_db)):
    valor = segredos.chave(provedor, db)
    if not valor:
        raise HTTPException(404, "Nenhuma chave cadastrada para este provedor.")
    ok, msg = segredos.testar(provedor, valor)
    return {"ok": ok, "mensagem": msg}


# ------------------------------------------------------------------ n8n
class N8nIn(BaseModel):
    titulo: str
    numero: str = ""
    convidados: str = "Sem convidados"
    transcricao_com_timestamps: str
    conteudo: dict
    prompt_versao: str = "v1"
    tokens_entrada: int = 0
    tokens_saida: int = 0
    tempo_s: float = 0


@router.post("/integracoes/n8n/episodios", status_code=201)
def receber_n8n(body: N8nIn, x_webhook_token: str | None = Header(None), db: Session = Depends(get_db)):
    """Recebe o resultado do workflow n8n (Whisper + Claude) e coloca o episódio na fila de revisão do acervo."""
    token = get_settings().n8n_token
    if not token or not x_webhook_token or not hmac.compare_digest(token, x_webhook_token):
        raise HTTPException(401, "Token do webhook inválido.")
    _, falas = ler_transcricao(body.transcricao_com_timestamps)
    if not falas:
        raise HTTPException(422, "Transcrição sem linhas [mm:ss].")
    ep = Episodio(titulo=body.titulo, numero=body.numero or "?", convidados=body.convidados, origem="n8n", status="revisao",
                  duracao_s=falas[-1].inicio + 15)
    ep.segmentos = [Segmento(inicio_s=f.inicio, texto=f.texto) for f in falas]
    db.add(ep)
    db.flush()
    try:
        p = criar_pacote(db, ep, body.conteudo, "n8n", body.prompt_versao,
                         {"tokens_entrada": body.tokens_entrada, "tokens_saida": body.tokens_saida, "tempo_s": body.tempo_s})
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    db.commit()
    reindexar(db)
    return {"episodio_id": ep.id, "alertas": p.alertas}


__all__ = ["router", "segundos"]
