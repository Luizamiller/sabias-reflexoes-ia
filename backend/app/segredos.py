"""Chaves de API cadastradas pelo painel.

- Guardadas cifradas (Fernet) na tabela `configuracoes`, nunca em texto puro.
- A chave-mestra vem de `SEGREDO_MESTRE` ou de um arquivo gerado na primeira vez em `storage/.chave-mestra`
  (fora do git). Sem a chave-mestra, os valores do banco não servem para nada.
- A API nunca devolve a chave inteira: só uma máscara (`sk-ant…9f2c`).
- Prioridade: chave do painel > variável de ambiente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import Configuracao, agora


@dataclass(frozen=True)
class Provedor:
    id: str
    nome: str
    uso: str
    env: str
    prefixo: str | None


PROVEDORES = {
    "anthropic": Provedor("anthropic", "Anthropic (Claude)", "Gera o pacote de conteúdo e responde no assistente", "anthropic_api_key", "sk-ant-"),
    "openai": Provedor("openai", "OpenAI (Whisper)", "Transcreve áudio e vídeo com marcação de tempo", "openai_api_key", "sk-"),
    "voyage": Provedor("voyage", "Voyage AI", "Embeddings opcionais para a busca semântica", "voyage_api_key", None),
}


def _fernet() -> Fernet:
    mestre = os.environ.get("SEGREDO_MESTRE")
    if not mestre:
        arq = get_settings().storage_dir / ".chave-mestra"
        if not arq.exists():
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_bytes(Fernet.generate_key())
            try:
                os.chmod(arq, 0o600)
            except OSError:
                pass
        mestre = arq.read_text().strip()
    return Fernet(mestre.encode() if isinstance(mestre, str) else mestre)


def mascarar(chave: str) -> str:
    return f"{chave[:6]}…{chave[-4:]}" if len(chave) > 12 else "…"


def _linha(db: Session, provedor: str) -> Configuracao | None:
    return db.get(Configuracao, f"segredo:{provedor}")


def _do_painel(db: Session, provedor: str) -> str | None:
    c = _linha(db, provedor)
    if not c or not c.valor:
        return None
    try:
        return _fernet().decrypt(c.valor.encode()).decode()
    except InvalidToken:
        return None  # chave-mestra trocada: tratar como ausente


def chave(provedor: str, db: Session | None = None) -> str | None:
    """Chave efetiva do provedor: painel, senão ambiente. Só para uso no servidor."""
    proprio = db is None
    db = db or SessionLocal()
    try:
        return _do_painel(db, provedor) or getattr(get_settings(), PROVEDORES[provedor].env) or None
    finally:
        if proprio:
            db.close()


def status(db: Session) -> list[dict]:
    cfg = get_settings()
    saida = []
    for p in PROVEDORES.values():
        painel = _do_painel(db, p.id)
        env = getattr(cfg, p.env) or None
        efetiva = painel or env
        linha = _linha(db, p.id) if painel else None
        saida.append({"provedor": p.id, "nome": p.nome, "uso": p.uso, "configurada": bool(efetiva),
                      "origem": "painel" if painel else ("ambiente" if env else None),
                      "mascara": mascarar(efetiva) if efetiva else None,
                      "atualizado_em": linha.atualizado_em.isoformat() if linha and linha.atualizado_em else None})
    return saida


def validar_formato(provedor: str, valor: str) -> str | None:
    p = PROVEDORES[provedor]
    if len(valor) < 20 or any(c.isspace() for c in valor):
        return "A chave parece incompleta. Copie de novo, sem espaços."
    if p.prefixo and not valor.startswith(p.prefixo):
        return f"Chaves da {p.nome.split(' ')[0]} começam com “{p.prefixo}”."
    if provedor == "openai" and valor.startswith("sk-ant-"):
        return "Essa é uma chave da Anthropic, não da OpenAI."
    return None


def salvar(db: Session, provedor: str, valor: str) -> None:
    c = _linha(db, provedor) or Configuracao(chave=f"segredo:{provedor}", valor="")
    c.valor = _fernet().encrypt(valor.encode()).decode()
    c.atualizado_em = agora()
    db.merge(c)
    db.commit()


def remover(db: Session, provedor: str) -> None:
    c = _linha(db, provedor)
    if c:
        db.delete(c)
        db.commit()


def testar(provedor: str, valor: str, cliente: httpx.Client | None = None) -> tuple[bool, str]:
    """Chamada mínima e gratuita (listar modelos) para confirmar que a chave é aceita."""
    http = cliente or httpx.Client(timeout=15)
    try:
        if provedor == "anthropic":
            r = http.get("https://api.anthropic.com/v1/models", params={"limit": 1},
                         headers={"x-api-key": valor, "anthropic-version": "2023-06-01"})
        elif provedor == "openai":
            r = http.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {valor}"})
        else:
            r = http.post("https://api.voyageai.com/v1/embeddings", headers={"Authorization": f"Bearer {valor}"},
                          json={"input": ["teste"], "model": "voyage-3.5-lite"})
    except httpx.HTTPError:
        return False, "Não foi possível falar com o provedor agora. Verifique a conexão."
    finally:
        if cliente is None:
            http.close()
    if r.status_code == 200:
        return True, "Chave aceita pelo provedor."
    if r.status_code in (401, 403):
        return False, "O provedor recusou a chave (inválida, revogada ou sem permissão)."
    if r.status_code == 429:
        return True, "Chave válida, mas o provedor está limitando as chamadas agora (cota ou créditos)."
    return False, f"O provedor respondeu {r.status_code}."
