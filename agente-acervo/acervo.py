"""Agente "Pergunte ao acervo" — Às Sábias Reflexões.

Responde perguntas sobre episódios antigos usando SOMENTE as transcrições,
sempre citando o episódio e o minuto de onde veio a informação.

Fluxo (RAG simples):
  1. Carrega as transcrições de dados/transcricoes/*.txt
  2. Divide cada episódio em trechos curtos com timestamp
  3. (Opcional) O Claude reescreve a pergunta com as palavras que alguém usaria ao falar do assunto
  4. Busca os trechos mais parecidos com a pergunta (TF-IDF com pedaços de palavras)
  5. Se nada for relevante o suficiente, responde "não encontrei" SEM chamar o modelo
  6. Caso contrário, envia os trechos ao Claude com a regra de citar a fonte

Uso pela linha de comando:
  python acervo.py "O que foi dito sobre medo de mudar de carreira?"

Histórico da busca (medido com avaliar.py — ver README):
  v1: palavras inteiras, trechos de 6 falas, limiar 0.08
  v2: pedaços de palavras (3 a 5 letras), trechos de 3 falas, limiar 0.12,
      reescrita opcional da pergunta pelo Claude
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PASTA_TRANSCRICOES = Path(__file__).parent / "dados" / "transcricoes"
MODELO = os.getenv("MODELO_CLAUDE", "claude-sonnet-5-5")

# Parâmetros da busca (v2)
LINHAS_POR_TRECHO = 3       # trechos curtos: em fala natural, um assunto dura poucas frases
SOBREPOSICAO = 1            # repete 1 fala entre trechos vizinhos para não cortar ideias no meio
TOP_K = 5                   # quantos trechos vão para o modelo
LIMIAR_RELEVANCIA = 0.12    # abaixo disso, consideramos que o acervo não fala do assunto
REESCREVER_PERGUNTA = os.getenv("REESCREVER_PERGUNTA", "0") == "1"

LINHA_TS = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+)$")


@dataclass
class Trecho:
    episodio: str
    titulo: str
    inicio: str
    texto: str
    minutos: list[str] = field(default_factory=list)  # horários de todas as falas do trecho

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
            minutos=[m for m, _ in bloco],
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
        # Pedaços de 3 a 5 letras: "culpa" também casa com "culpada", "descanso" com "descansar"
        self._vet = TfidfVectorizer(preprocessor=_normalizar, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        self._matriz = self._vet.fit_transform(t.texto for t in self.trechos)

    def buscar(self, pergunta: str, k: int = TOP_K, limiar: float = LIMIAR_RELEVANCIA) -> list[tuple[Trecho, float]]:
        notas = cosine_similarity(self._vet.transform([pergunta]), self._matriz)[0]
        ordem = notas.argsort()[::-1][:k]
        return [(self.trechos[i], float(notas[i])) for i in ordem if notas[i] >= limiar]


PROMPT_REESCRITA = """Você ajuda a buscar trechos em transcrições de um podcast de conversa.
Reescreva a pergunta abaixo como 1 ou 2 frases curtas, em português informal, com as palavras e
situações concretas que alguém provavelmente usaria AO FALAR desse assunto em voz alta.
Não responda à pergunta. Devolva só as frases.

Exemplo:
Pergunta: como lidar com elogio sem se justificar
Frases: alguém falou que minha roupa é linda e eu já disse que comprei na promoção, com desconto

Pergunta: {pergunta}
Frases:"""


def reescrever_pergunta(pergunta: str, cliente) -> str:
    """Pede ao Claude as palavras que a pessoa usaria ao falar do assunto (chamada curta e barata)."""
    msg = cliente.messages.create(
        model=MODELO,
        max_tokens=120,
        messages=[{"role": "user", "content": PROMPT_REESCRITA.format(pergunta=pergunta)}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def buscar_com_reescrita(acervo: Acervo, pergunta: str, cliente) -> list[tuple[Trecho, float]]:
    """Busca com a pergunta original e com a reescrita; fica com a melhor nota de cada trecho."""
    melhores: dict[int, tuple[Trecho, float]] = {}
    for consulta in (pergunta, f"{pergunta} {reescrever_pergunta(pergunta, cliente)}"):
        for t, nota in acervo.buscar(consulta):
            if id(t) not in melhores or nota > melhores[id(t)][1]:
                melhores[id(t)] = (t, nota)
    return sorted(melhores.values(), key=lambda x: -x[1])[:TOP_K]


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


def responder(acervo: Acervo, pergunta: str, cliente=None, reescrever: bool = REESCREVER_PERGUNTA) -> dict:
    """Retorna {'resposta': str, 'fontes': list[Trecho], 'chamou_modelo': bool}."""
    def _cliente():
        if cliente is not None:
            return cliente
        import anthropic
        return anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente

    if reescrever:
        cliente = _cliente()
        achados = buscar_com_reescrita(acervo, pergunta, cliente)
    else:
        achados = acervo.buscar(pergunta)
    if not achados:
        return {"resposta": RESPOSTA_SEM_FONTE, "fontes": [], "chamou_modelo": False}
    cliente = _cliente()

    contexto = "\n\n".join(
        f'<trecho fonte="{t.citacao}" titulo="{t.titulo}">\n{t.texto}\n</trecho>' for t, _ in achados
    )
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
