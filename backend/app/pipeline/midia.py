"""Áudio e vídeo: tipo do arquivo, extração do áudio com ffmpeg, corte em partes e transcrição com Whisper.

O fluxo para um vídeo de 1h30:
  vídeo.mp4 → ffmpeg (só a trilha de áudio, mono, 16 kHz, MP3 48 kbps ≈ 32 MB)
            → partes de 20 min (~7 MB cada, abaixo do limite de 25 MB da API)
            → Whisper em cada parte → segmentos com o horário somado ao início da parte.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from ..config import get_settings
from ..search.engine import Fala

EXT_AUDIO = {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".flac", ".aac", ".wma"}
EXT_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg", ".wmv"}
LIMITE_API = 25 * 1024 * 1024


def tipo_da_midia(nome: str, content_type: str | None = None) -> str | None:
    ext = Path(nome.lower()).suffix
    if ext in EXT_VIDEO:
        return "video"
    if ext in EXT_AUDIO:
        return "audio"
    ct = (content_type or "").lower()
    return "video" if ct.startswith("video/") else "audio" if ct.startswith("audio/") else None


def ffmpeg() -> str | None:
    cfg = get_settings()
    if cfg.ffmpeg_bin:
        return cfg.ffmpeg_bin
    if achado := shutil.which("ffmpeg"):
        return achado
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pacote ausente ou binário indisponível para a plataforma
        return None


def _rodar(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def duracao(caminho: Path) -> float | None:
    """Lê a duração da saída do próprio ffmpeg (o pacote não traz ffprobe)."""
    exe = ffmpeg()
    if not exe:
        return None
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", _rodar([exe, "-hide_banner", "-i", str(caminho)]).stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def extrair_audio(origem: Path, destino: Path) -> None:
    exe = ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg não encontrado: instale o ffmpeg ou o pacote imageio-ffmpeg para processar vídeo.")
    r = _rodar([exe, "-hide_banner", "-loglevel", "error", "-y", "-i", str(origem), "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "libmp3lame", "-b:a", "48k", str(destino)])
    if r.returncode != 0 or not destino.exists() or destino.stat().st_size == 0:
        detalhe = (r.stderr or "").strip().splitlines()[-1:] or ["sem trilha de áudio?"]
        raise RuntimeError(f"Não foi possível extrair o áudio do arquivo ({detalhe[0][:160]}).")


def cortar(audio: Path, pasta: Path, total_s: float, parte_s: int) -> list[tuple[Path, float]]:
    """Partes de `parte_s` segundos (cópia sem recodificar). Devolve (arquivo, início em segundos)."""
    exe = ffmpeg()
    partes = []
    inicio, i = 0.0, 0
    while inicio < total_s:
        alvo = pasta / f"parte-{i:03d}.mp3"
        r = _rodar([exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{inicio:.2f}", "-t", str(parte_s),
                    "-i", str(audio), "-c", "copy", str(alvo)])
        if r.returncode != 0:
            raise RuntimeError(f"Falha ao cortar o áudio na parte {i + 1}.")
        if alvo.stat().st_size > 1024:  # descarta sobra de milissegundos no fim
            partes.append((alvo, inicio))
        inicio += parte_s
        i += 1
    return partes


def whisper(caminho: Path, chave: str, dica: str = "", tentativas: int = 3) -> list[dict]:
    """Uma chamada ao Whisper com `verbose_json` (segmentos com início em segundos). Repete em 429/5xx."""
    cfg = get_settings()
    for n in range(tentativas):
        with caminho.open("rb") as f:
            r = httpx.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {chave}"},
                           data={"model": cfg.modelo_transcricao, "response_format": "verbose_json", "language": "pt",
                                 **({"prompt": dica[:800]} if dica else {})},
                           files={"file": (caminho.name, f)}, timeout=900)
        if r.status_code in (429, 500, 502, 503, 504) and n < tentativas - 1:
            time.sleep(2 ** (n + 1))
            continue
        if r.status_code == 401:
            raise RuntimeError("A OpenAI recusou a chave. Confira em Configurações › Chaves de API.")
        if r.status_code == 429:
            raise RuntimeError("A OpenAI limitou as chamadas (cota ou créditos esgotados).")
        r.raise_for_status()
        return r.json().get("segments", [])
    return []


def transcrever(midia: Path, chave: str, dica: str = "", progresso: Callable[[str], None] = lambda _: None,
                transcritor: Callable[..., list[dict]] | None = None) -> tuple[list[Fala], float]:
    """Transcreve áudio ou vídeo de qualquer tamanho. Devolve as falas e a duração em segundos."""
    cfg = get_settings()
    transcritor = transcritor or whisper
    pasta = midia.parent / f".tmp-{midia.stem}"
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        if ffmpeg():
            progresso("Extraindo o áudio")
            audio = pasta / "audio.mp3"
            extrair_audio(midia, audio)
            total = duracao(audio) or duracao(midia) or 0
            partes = cortar(audio, pasta, total, cfg.parte_transcricao_s) if total > cfg.parte_transcricao_s else [(audio, 0.0)]
        else:
            if tipo_da_midia(midia.name) == "video" or midia.stat().st_size > LIMITE_API:
                raise RuntimeError("Sem ffmpeg só dá para transcrever áudio de até 25 MB.")
            partes, total = [(midia, 0.0)], 0

        falas: list[Fala] = []
        for i, (arq, inicio) in enumerate(partes, 1):
            progresso(f"Transcrevendo parte {i} de {len(partes)}" if len(partes) > 1 else "Transcrevendo com Whisper")
            # a dica ajuda o modelo com nomes próprios; nas partes seguintes, o fim da anterior dá continuidade
            contexto = dica + (" " + " ".join(f.texto for f in falas[-3:]) if falas else "")
            for s in transcritor(arq, chave, contexto.strip()):
                texto = (s.get("text") or "").strip()
                if texto:
                    falas.append(Fala(int(inicio + float(s["start"])), texto))
        if not total and falas:
            total = falas[-1].inicio + 10
        return falas, total
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
