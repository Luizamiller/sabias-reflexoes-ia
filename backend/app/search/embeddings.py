"""Vetores para a busca semântica, atrás de uma interface única.

- `LocalLSA` (padrão): análise semântica latente sobre TF-IDF de palavras — roda localmente, sem
  download nem chave, e aproxima termos que aparecem em contextos parecidos. É modesta; serve para
  o acervo funcionar em qualquer máquina e para medir o ganho da busca híbrida de forma honesta.
- `VoyageEmbedder` / `OpenAIEmbedder`: embeddings de provedores, ativados por variável de ambiente.
  Em produção com Postgres, os vetores podem ir para uma coluna pgvector (ver docs/ARQUITETURA.md).
"""
from __future__ import annotations

from typing import Protocol

import httpx
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize


class Embedder(Protocol):
    nome: str

    def ajustar_e_codificar(self, textos: list[str]) -> np.ndarray: ...
    def codificar(self, textos: list[str]) -> np.ndarray: ...


def _norm(txt: str) -> str:
    import unicodedata
    txt = unicodedata.normalize("NFKD", txt.lower())
    return "".join(c for c in txt if not unicodedata.combining(c))


class LocalLSA:
    nome = "local-lsa"

    def __init__(self, dimensoes: int = 48):
        self.dimensoes = dimensoes

    def ajustar_e_codificar(self, textos: list[str]) -> np.ndarray:
        self.vet = TfidfVectorizer(preprocessor=_norm, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
        m = self.vet.fit_transform(textos)
        n = max(2, min(self.dimensoes, m.shape[0] - 1, m.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=n, random_state=7)
        return normalize(self.svd.fit_transform(m))

    def codificar(self, textos: list[str]) -> np.ndarray:
        return normalize(self.svd.transform(self.vet.transform(textos)))


class _ProvedorHTTP:
    url: str
    modelo: str
    nome: str

    def __init__(self, chave: str):
        self.chave = chave

    def _chamar(self, textos: list[str]) -> np.ndarray:
        r = httpx.post(self.url, headers={"Authorization": f"Bearer {self.chave}"},
                       json={"model": self.modelo, "input": textos}, timeout=30)
        r.raise_for_status()
        return normalize(np.array([d["embedding"] for d in r.json()["data"]], dtype=np.float32))

    def ajustar_e_codificar(self, textos: list[str]) -> np.ndarray:
        return np.vstack([self._chamar(textos[i: i + 64]) for i in range(0, len(textos), 64)])

    def codificar(self, textos: list[str]) -> np.ndarray:
        return self._chamar(textos)


class VoyageEmbedder(_ProvedorHTTP):
    url, modelo, nome = "https://api.voyageai.com/v1/embeddings", "voyage-3.5-lite", "voyage"


class OpenAIEmbedder(_ProvedorHTTP):
    url, modelo, nome = "https://api.openai.com/v1/embeddings", "text-embedding-3-small", "openai"


def escolher(provedor: str, voyage_key: str | None, openai_key: str | None) -> Embedder:
    if provedor == "voyage" and voyage_key:
        return VoyageEmbedder(voyage_key)
    if provedor == "openai" and openai_key:
        return OpenAIEmbedder(openai_key)
    return LocalLSA()
