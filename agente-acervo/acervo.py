"""Agente "Pergunte ao acervo" — Às Sábias Reflexões.

Responde perguntas sobre episódios antigos usando SOMENTE as transcrições,
sempre citando o episódio e o minuto de onde veio a informação.

Fluxo (RAG simples):
  1. Carrega as transcrições de dados/transcricoes/*.txt
  2. Divide cada episódio em trechos com timestamp
  3. Busca os trechos mais parecidos com a pergunta (TF-IDF)
  4. Se nada for relevante o suficiente, responde "não encontrei" SEM chamar o modelo
  5. Caso contrário, envia os trechos ao Claude com a regra de citar a fonte

Uso pela linha de comando:
  python acervo.py "O que foi dito sobre medo de mudar de carreira?"
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PASTA_TRANSCRICOES = Path(__file__).parent / "dados" / "transcricoes"
MODELO = os.getenv("MODELO_CLAUDE", "claude-sonnet-5-5")
LINHAS_POR_TRECHO = 6       # cada trecho ≈ 6 falas consecutivas
SOBREPOSICAO = 2            # repete 2 linhas entre trechos vizinhos para não cortar ideias no meio
TOP_K = 5                   # quantos trechos vão para o modelo
LIMIAR_RELEVANCIA = 0.08    # abaixo disso, consideramos que o acervo não fala do assunto

STOPWORDS_PT = set("""
a à ao aos as às até com como da das de dei do dos e é ela elas ele eles em entre era eram essa esse
esta este eu foi for foram há isso isto já la lhe mais mas me mesmo meu minha muito na nas não nem no
nos nós o os ou para pela pelas pelo pelos por qual quando que quem se sem ser seu sua são só também
te tem têm tinha um uma umas uns você vocês vai vou ter sobre então aí né tipo assim gente coisa
""".split())

LINHA_TS = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+)$")


@dataclass
class Trecho:
    episodio: str
    titulo: str
    inicio: str
    texto: str

    @property
    def citacao(self) -> str:
        return f"Ep. {self.episodio} – {self.inicio}"


def _normalizar(txt: str) -> str:
    """Minúsculas e sem acentos, para 'reflexão' e 'reflexao' casarem na busca."""
    txt = unicodedata.normalize("NFKD", txt.lower())
    return "".join(c for c in txt if not unicodedata.combining(c))


def carregar_episodio(caminho: Path) -> list[Trecho]:
    """Lê um .txt no formato:

        titulo: Nome do episódio
        episodio: 12
        ---
        [00:00] fala...
        [00:15] fala...
    """
    cabecalho, _, corpo = caminho.read_text(encoding="utf-8").partition("\n---\n")
    meta = dict(
        (k.strip().lower(), v.strip())
        for k, _, v in (l.partition(":") for l in cabecalho.splitlines())
        if v
    )
    falas = [m.groups() for l in corpo.splitlines() if (m := LINHA_TS.match(l.strip()))]
    if not falas:
        raise ValueError(f"{caminho.name}: nenhuma linha no formato [mm:ss] texto")

    passo = LINHAS_POR_TRECHO - SOBREPOSICAO
    trechos = []
    for i in range(0, len(falas), passo):
        bloco = falas[i : i + LINHAS_POR_TRECHO]
        trechos.append(Trecho(
            episodio=meta.get("episodio", caminho.stem),
            titulo=meta.get("titulo", caminho.stem),
            inicio=bloco[0][0],
            texto=" ".join(t for _, t in bloco),
        ))
        if i + LINHAS_POR_TRECHO >= len(falas):
            break
    return trechos


class Acervo:
    def __init__(self, pasta: Path = PASTA_TRANSCRICOES):
        arquivos = sorted(pasta.glob("*.txt"))
        if not arquivos:
            raise FileNotFoundError(f"Nenhuma transcrição em {pasta}")
        self.trechos = [t for a in arquivos for t in carregar_episodio(a)]
        self.episodios = sorted({(t.episodio, t.titulo) for t in self.trechos})
        stop = {_normalizar(w) for w in STOPWORDS_PT}
        self._vet = TfidfVectorizer(preprocessor=_normalizar, stop_words=list(stop), ngram_range=(1, 2), sublinear_tf=True)
        self._matriz = self._vet.fit_transform(t.texto for t in self.trechos)

    def buscar(self, pergunta: str, k: int = TOP_K) -> list[tuple[Trecho, float]]:
        notas = cosine_similarity(self._vet.transform([pergunta]), self._matriz)[0]
        ordem = notas.argsort()[::-1][:k]
        return [(self.trechos[i], float(notas[i])) for i in ordem if notas[i] >= LIMIAR_RELEVANCIA]


SYSTEM = """Você é o assistente do acervo do podcast "Às Sábias Reflexões".
Responda à pergunta usando SOMENTE os trechos de transcrição fornecidos.

Regras:
- Toda afirmação deve terminar com a fonte entre parênteses, exatamente como aparece no trecho, ex.: (Ep. 3 – 12:40).
- Se os trechos não respondem à pergunta, diga claramente que o acervo não trata desse assunto. Não complete com conhecimento próprio.
- Não atribua a uma pessoa algo que ela não disse nos trechos.
- Responda em português do Brasil, em no máximo 3 parágrafos curtos.
- Ao final, sugira o episódio mais relevante para ouvir completo."""

RESPOSTA_SEM_FONTE = (
    "Não encontrei esse assunto nas transcrições do acervo. "
    "Tente reformular a pergunta ou usar outras palavras."
)


def responder(acervo: Acervo, pergunta: str, cliente=None) -> dict:
    """Retorna {'resposta': str, 'fontes': list[Trecho], 'chamou_modelo': bool}."""
    achados = acervo.buscar(pergunta)
    if not achados:
        return {"resposta": RESPOSTA_SEM_FONTE, "fontes": [], "chamou_modelo": False}

    contexto = "\n\n".join(
        f'<trecho fonte="{t.citacao}" titulo="{t.titulo}">\n{t.texto}\n</trecho>' for t, _ in achados
    )
    if cliente is None:
        import anthropic
        cliente = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente

    msg = cliente.messages.create(
        model=MODELO,
        max_tokens=1000,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"<trechos>\n{contexto}\n</trechos>\n\nPergunta: {pergunta}"}],
    )
    texto = "".join(b.text for b in msg.content if b.type == "text")
    return {"resposta": texto, "fontes": [t for t, _ in achados], "chamou_modelo": True}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Uso: python acervo.py "sua pergunta"')
    r = responder(Acervo(), " ".join(sys.argv[1:]))
    print(r["resposta"])
    if r["fontes"]:
        print("\nTrechos consultados:", ", ".join(t.citacao for t in r["fontes"]))
