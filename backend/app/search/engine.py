"""Busca no acervo — evolução direta de `agente-acervo/acervo.py`.

Versões (medidas com `app.eval`, ver README):
  v1: palavras inteiras, trechos de 6 falas, limiar 0,08
  v2: pedaços de palavras (3 a 5 letras), trechos de 3 falas, limiar 0,12   ← original
  v3: híbrida — v2 + vetores semânticos, fundidos por Reciprocal Rank Fusion

O critério de "não encontrei" continua conservador: um trecho só conta como relevante se a
nota lexical passar do limiar da v2 OU a nota semântica passar do limiar semântico. Se nada
for relevante, o modelo de linguagem nem é chamado.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .embeddings import Embedder, LocalLSA

LINHA_TS = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+)$")

VERSOES = {
    "v1": dict(linhas=6, sobreposicao=2, limiar=0.08, analisador="palavras", semantica=False),
    "v2": dict(linhas=3, sobreposicao=1, limiar=0.12, analisador="pedacos", semantica=False),
    "v3": dict(linhas=3, sobreposicao=1, limiar=0.12, analisador="pedacos", semantica=True, limiar_sem=0.55),
}
PADRAO = "v3"
TOP_K = 5

STOPWORDS = """a à ao aos as às até com como da das de do dos e é em essa esse eu foi mais mas me
meu minha muito na nas não no nos o os ou para pela pelo por que se sem seu sua um uma você vai ter
sobre então aí né tipo assim gente coisa""".split()


def normalizar(txt: str) -> str:
    """Minúsculas e sem acentos, para 'reflexão' e 'reflexao' casarem."""
    txt = unicodedata.normalize("NFKD", txt.lower())
    return "".join(c for c in txt if not unicodedata.combining(c))


def mmss(seg: float) -> str:
    s = int(round(seg))
    return f"{s // 60:02d}:{s % 60:02d}"


def segundos(ts: str) -> int:
    partes = [int(p) for p in ts.split(":")]
    return partes[0] * 60 + partes[1] if len(partes) == 2 else partes[0] * 3600 + partes[1] * 60 + partes[2]


@dataclass
class Fala:
    inicio: int  # segundos
    texto: str


@dataclass
class Trecho:
    episodio_id: int
    episodio: str  # número exibido
    titulo: str
    inicio: str  # mm:ss
    texto: str
    minutos: list[str] = field(default_factory=list)

    @property
    def citacao(self) -> str:
        return f"Ep. {self.episodio} – {self.inicio}"


def ler_transcricao(texto: str) -> tuple[dict, list[Fala]]:
    """Formato original: cabeçalho `chave: valor`, linha `---`, depois `[mm:ss] fala`."""
    if "\n---\n" in texto:
        cabecalho, _, corpo = texto.partition("\n---\n")
    else:
        cabecalho, corpo = "", texto
    meta = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in cabecalho.splitlines()) if v}
    falas = [Fala(segundos(m.group(1)), m.group(2).strip()) for l in corpo.splitlines() if (m := LINHA_TS.match(l.strip()))]
    return meta, falas


def fatiar(episodio_id: int, numero: str, titulo: str, falas: list[Fala], linhas: int, sobreposicao: int) -> list[Trecho]:
    passo = max(1, linhas - sobreposicao)
    trechos = []
    for i in range(0, len(falas), passo):
        bloco = falas[i: i + linhas]
        trechos.append(Trecho(episodio_id, numero, titulo, mmss(bloco[0].inicio), " ".join(f.texto for f in bloco),
                              [mmss(f.inicio) for f in bloco]))
        if i + linhas >= len(falas):
            break
    return trechos


@dataclass
class Resultado:
    trecho: Trecho
    nota: float           # nota usada na ordenação
    lexical: float
    semantica: float | None


class Indice:
    def __init__(self, episodios: list[tuple[int, str, str, list[Fala]]], versao: str = PADRAO,
                 embedder: Embedder | None = None):
        self.cfg = VERSOES[versao]
        self.versao = versao
        self.trechos = [t for eid, num, tit, falas in episodios
                        for t in fatiar(eid, num, tit, falas, self.cfg["linhas"], self.cfg["sobreposicao"])]
        if not self.trechos:
            self._lex = None
            return
        if self.cfg["analisador"] == "palavras":
            stop = sorted({normalizar(w) for w in STOPWORDS})
            self._vet = TfidfVectorizer(preprocessor=normalizar, stop_words=stop, ngram_range=(1, 2), sublinear_tf=True)
        else:  # pedaços de 3 a 5 letras: "culpa" casa com "culpada"
            self._vet = TfidfVectorizer(preprocessor=normalizar, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self._lex = self._vet.fit_transform(t.texto for t in self.trechos)
        self.embedder = None
        if self.cfg["semantica"]:
            self.embedder = embedder or LocalLSA()
            self._sem = self.embedder.ajustar_e_codificar([t.texto for t in self.trechos])

    def buscar(self, pergunta: str, k: int = TOP_K, limiar: float | None = None) -> list[Resultado]:
        if self._lex is None:
            return []
        limiar = self.cfg["limiar"] if limiar is None else limiar
        lex = cosine_similarity(self._vet.transform([pergunta]), self._lex)[0]
        if not self.cfg["semantica"]:
            ordem = lex.argsort()[::-1][:k]
            return [Resultado(self.trechos[i], float(lex[i]), float(lex[i]), None) for i in ordem if lex[i] >= limiar]

        q = self.embedder.codificar([pergunta])
        sem = (self._sem @ q.T).ravel()
        # Com a LSA local, a nota semântica acompanha a lexical (medido: não acrescenta acertos e deixa passar
        # perguntas fora do tema), então ela só reordena. Com embeddings de provedor, também amplia o que conta
        # como relevante — limiar ainda não calibrado com episódios reais.
        relevantes = lex >= limiar
        if self.embedder.nome != "local-lsa":
            relevantes |= sem >= self.cfg["limiar_sem"]
        # Reciprocal Rank Fusion: robusta a escalas diferentes das duas notas
        rank_lex = np.empty_like(lex); rank_lex[lex.argsort()[::-1]] = np.arange(len(lex))
        rank_sem = np.empty_like(sem); rank_sem[sem.argsort()[::-1]] = np.arange(len(sem))
        rrf = 1 / (60 + rank_lex) + 1 / (60 + rank_sem)
        ordem = [i for i in rrf.argsort()[::-1] if relevantes[i]][:k]
        return [Resultado(self.trechos[i], float(rrf[i]), float(lex[i]), float(sem[i])) for i in ordem]
