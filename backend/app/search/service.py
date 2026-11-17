"""Índice em memória do acervo + assistente com RAG e citações verificadas.

O índice é reconstruído a partir dos segmentos no banco quando um episódio entra ou sai.
Para um acervo de podcast (centenas de episódios) isso cabe com folga em memória; acima disso,
o passo seguinte é guardar os vetores numa coluna pgvector (docs/ARQUITETURA.md).
"""
from __future__ import annotations

import logging
import re
import threading
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Episodio
from ..segredos import chave
from .embeddings import escolher
from .engine import PADRAO, Fala, Indice, Resultado

log = logging.getLogger("acervo.busca")
_lock = threading.Lock()
_indice: Indice | None = None

SYSTEM = """Você é o assistente do acervo do podcast "Às Sábias Reflexões".
Responda à pergunta usando SOMENTE os trechos de transcrição fornecidos.

Regras:
- Toda afirmação deve terminar com a fonte entre parênteses, exatamente como aparece no trecho, ex.: (Ep. 3 – 12:40).
- Se os trechos não respondem à pergunta, diga claramente que o acervo não trata desse assunto. Não complete com conhecimento próprio.
- Não atribua a uma pessoa algo que ela não disse nos trechos.
- Responda em português do Brasil, em no máximo 3 parágrafos curtos.
- Ao final, sugira o episódio mais relevante para ouvir completo."""

PROMPT_REESCRITA = """Você ajuda a buscar trechos em transcrições de um podcast de conversa.
Reescreva a pergunta abaixo como 1 ou 2 frases curtas, em português informal, com as palavras e
situações concretas que alguém provavelmente usaria AO FALAR desse assunto em voz alta.
Não responda à pergunta. Devolva só as frases.

Exemplo:
Pergunta: como lidar com elogio sem se justificar
Frases: alguém falou que minha roupa é linda e eu já disse que comprei na promoção, com desconto

Pergunta: {pergunta}
Frases:"""

RESPOSTA_SEM_FONTE = "Não encontrei esse assunto nas transcrições do acervo. Tente reformular a pergunta ou usar outras palavras."
CITACAO = re.compile(r"\(Ep\.\s*([\w-]+)\s*[–-]\s*(\d{1,2}:\d{2})\)")


def reindexar(db: Session) -> int:
    global _indice
    cfg = get_settings()
    eps = db.scalars(select(Episodio).where(Episodio.status != "erro").order_by(Episodio.id)).all()
    dados = [(e.id, e.numero, e.titulo, [Fala(s.inicio_s, s.texto) for s in e.segmentos]) for e in eps if e.segmentos]
    novo = Indice(dados, PADRAO, escolher(cfg.provedor_embeddings, chave("voyage", db), chave("openai", db)))
    with _lock:
        _indice = novo
    log.info("índice reconstruído: %d episódios, %d trechos", len(dados), len(novo.trechos))
    return len(novo.trechos)


def indice(db: Session) -> Indice:
    if _indice is None:
        reindexar(db)
    return _indice


def _cliente():
    k = chave("anthropic")
    if not k:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=k)


def buscar(db: Session, pergunta: str, k: int = 5, cliente=None, reescrever: bool | None = None) -> tuple[list[Resultado], str | None]:
    """Busca híbrida; com reescrita opcional da pergunta pelo Claude (recurso do projeto original)."""
    ind = indice(db)
    reescrever = get_settings().reescrever_pergunta if reescrever is None else reescrever
    cli = cliente or (_cliente() if reescrever else None)
    if not reescrever or cli is None:
        return ind.buscar(pergunta, k), None
    msg = cli.messages.create(model=get_settings().modelo_claude, max_tokens=120,
                              messages=[{"role": "user", "content": PROMPT_REESCRITA.format(pergunta=pergunta)}])
    extra = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    melhores: dict[int, Resultado] = {}
    for consulta in (pergunta, f"{pergunta} {extra}"):
        for r in ind.buscar(consulta, k):
            if id(r.trecho) not in melhores or r.nota > melhores[id(r.trecho)].nota:
                melhores[id(r.trecho)] = r
    return sorted(melhores.values(), key=lambda r: -r.nota)[:k], extra


def verificar_citacoes(texto: str, fontes: list[Resultado]) -> list[str]:
    """Citações na resposta que não correspondem a nenhuma fala dos trechos enviados ao modelo."""
    validas = {(r.trecho.episodio, m) for r in fontes for m in r.trecho.minutos}
    return [f"Ep. {ep} – {ts}" for ep, ts in CITACAO.findall(texto) if (ep, ts) not in validas]


def fonte_api(r: Resultado) -> dict:
    t = r.trecho
    return {"episodio_id": t.episodio_id, "episodio": t.episodio, "titulo": t.titulo, "inicio": t.inicio, "minutos": t.minutos,
            "texto": t.texto, "citacao": t.citacao, "lexical": round(r.lexical, 3),
            "semantica": None if r.semantica is None else round(r.semantica, 3)}


def responder_stream(db: Session, pergunta: str, cliente=None) -> Iterator[dict]:
    """Gera eventos: `fontes` → `texto` (vários) → `fim`. Sem trecho relevante, não chama o modelo."""
    fontes, reescrita = buscar(db, pergunta, cliente=cliente)
    yield {"tipo": "fontes", "fontes": [fonte_api(r) for r in fontes], "reescrita": reescrita}
    if not fontes:
        yield {"tipo": "texto", "texto": RESPOSTA_SEM_FONTE}
        yield {"tipo": "fim", "motor": "nenhum", "chamou_modelo": False, "citacoes_invalidas": [], "resposta": RESPOSTA_SEM_FONTE}
        return

    cli = cliente or _cliente()
    if cli is None:  # sem modelo: resposta extrativa, honesta sobre isso
        partes = ["Sem modelo de linguagem configurado, estes são os trechos do acervo mais próximos da pergunta:\n"]
        partes += [f"— “{r.trecho.texto}” ({r.trecho.citacao})" for r in fontes[:3]]
        partes.append(f"\nPara ouvir completo: Ep. {fontes[0].trecho.episodio}, {fontes[0].trecho.titulo.replace('[EXEMPLO FICTÍCIO] ', '')}.")
        texto = "\n".join(partes)
        yield {"tipo": "texto", "texto": texto}
        yield {"tipo": "fim", "motor": "extrativo", "chamou_modelo": False, "citacoes_invalidas": [], "resposta": texto}
        return

    contexto = "\n\n".join(f'<trecho fonte="{r.trecho.citacao}" titulo="{r.trecho.titulo}">\n{r.trecho.texto}\n</trecho>' for r in fontes)
    kwargs = dict(model=get_settings().modelo_claude, max_tokens=1000, system=SYSTEM,
                  messages=[{"role": "user", "content": f"<trechos>\n{contexto}\n</trechos>\n\nPergunta: {pergunta}"}])
    texto = ""
    if hasattr(cli.messages, "stream"):
        with cli.messages.stream(**kwargs) as s:
            for pedaco in s.text_stream:
                texto += pedaco
                yield {"tipo": "texto", "texto": pedaco}
    else:  # clientes simulados nos testes
        msg = cli.messages.create(**kwargs)
        texto = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        yield {"tipo": "texto", "texto": texto}
    invalidas = verificar_citacoes(texto, fontes)
    yield {"tipo": "fim", "motor": "claude", "chamou_modelo": True, "citacoes_invalidas": invalidas, "resposta": texto}
