"""Exportação: transcrição em TXT, legendas SRT/VTT e o pacote de conteúdo em Markdown."""
from __future__ import annotations

from ..models import Episodio, Pacote
from ..search.engine import mmss
from .conteudo import ROTULOS

FORMATOS = {"txt": "txt", "srt": "srt", "vtt": "vtt", "md": "md"}
TIPOS = {"txt": "text/plain", "srt": "application/x-subrip", "vtt": "text/vtt", "md": "text/markdown"}


def _ts(seg: float, sep: str) -> str:
    ms = int(round(seg * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _blocos(ep: Episodio):
    """Cada fala vira uma legenda: do início dela até o início da seguinte (no máximo 8 s, para não ficar parada)."""
    segs = ep.segmentos
    for i, s in enumerate(segs):
        prox = segs[i + 1].inicio_s if i + 1 < len(segs) else max(ep.duracao_s, s.inicio_s + 4)
        yield i + 1, s.inicio_s, max(s.inicio_s + 1, min(prox, s.inicio_s + 8)), s.texto


def _peca_md(tipo: str, c) -> str:
    if isinstance(c, str):
        return c
    if tipo == "newsletter" and isinstance(c, dict):
        return f"**Assunto:** {c.get('assunto', '')}\n\n{c.get('corpo', '')}"
    if isinstance(c, list):
        linhas = []
        for x in c:
            if isinstance(x, str):
                linhas.append(f"> {x}" if tipo == "citacoes" else f"- {x}")
            elif isinstance(x, dict):
                tempo = " – ".join(str(x[k]) for k in ("inicio", "fim") if x.get(k))
                resto = " · ".join(str(v) for k, v in x.items() if k not in ("inicio", "fim") and v)
                linhas.append(f"- **{tempo}** {resto}".strip())
        return "\n".join(linhas)
    return str(c)


def exportar(ep: Episodio, pacote: Pacote | None, formato: str) -> tuple[str, str]:
    if formato == "txt":
        cab = f"titulo: {ep.titulo}\nepisodio: {ep.numero}\nconvidados: {ep.convidados}\n---\n"
        return cab + "\n".join(f"[{mmss(s.inicio_s)}] {s.texto}" for s in ep.segmentos) + "\n", TIPOS[formato]
    if formato == "srt":
        return "\n".join(f"{n}\n{_ts(a, ',')} --> {_ts(b, ',')}\n{t}\n" for n, a, b, t in _blocos(ep)), TIPOS[formato]
    if formato == "vtt":
        return "WEBVTT\n\n" + "\n".join(f"{_ts(a, '.')} --> {_ts(b, '.')}\n{t}\n" for _, a, b, t in _blocos(ep)), TIPOS[formato]
    partes = [f"# Episódio {ep.numero} — {ep.titulo}", f"Convidados: {ep.convidados}"]
    if pacote:
        partes.append(f"_Gerado por: {pacote.motor} · prompt {pacote.prompt_versao}. Peças rejeitadas não entram._")
        for p in pacote.pecas:
            if p.status == "rejeitada":
                continue
            selo = {"aprovada": "aprovada", "editada": "editada e aprovada"}.get(p.status, "aguardando revisão")
            partes.append(f"## {ROTULOS.get(p.tipo, p.tipo)}  \n_{selo}_\n\n{_peca_md(p.tipo, p.conteudo)}")
    else:
        partes.append("_Ainda sem pacote de conteúdo._")
    return "\n\n".join(partes) + "\n", TIPOS[formato]
