"""Mede a qualidade da busca do acervo contra um gabarito de perguntas.

Para cada pergunta, o gabarito diz em qual episódio e em quais minutos está a resposta
(ou que o acervo NÃO fala do assunto). A busca acerta quando:
  - algum dos 3 primeiros trechos cobre um dos minutos esperados; ou
  - para perguntas fora do acervo, quando não devolve nenhum trecho.

Uso:
  python avaliar.py                       # versão atual (v2), gabarito de exemplo
  python avaliar.py --versao v1           # compara com a versão anterior
  python avaliar.py --pasta dados/privado --gabarito dados/privado/gabarito.json
                                          # episódios reais (pasta fora do Git)

Rode sempre antes e depois de mudar a busca, e registre o resultado no README.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

import acervo as A

AQUI = Path(__file__).parent

VERSOES = {
    "v1": dict(linhas=6, sobreposicao=2, limiar=0.08, analisador="palavras"),
    "v2": dict(linhas=A.LINHAS_POR_TRECHO, sobreposicao=A.SOBREPOSICAO, limiar=A.LIMIAR_RELEVANCIA, analisador="pedacos"),
}

STOPWORDS_V1 = """a à ao aos as às até com como da das de do dos e é em essa esse eu foi mais mas me
meu minha muito na nas não no nos o os ou para pela pelo por que se sem seu sua um uma você vai ter
sobre então aí né tipo assim gente coisa""".split()


def montar_acervo(pasta: Path, cfg: dict) -> A.Acervo:
    A.LINHAS_POR_TRECHO, A.SOBREPOSICAO = cfg["linhas"], cfg["sobreposicao"]
    ac = A.Acervo(pasta)
    if cfg["analisador"] == "palavras":  # recria a busca da v1
        stop = sorted({A._normalizar(w) for w in STOPWORDS_V1})
        ac._vet = TfidfVectorizer(preprocessor=A._normalizar, stop_words=stop, ngram_range=(1, 2), sublinear_tf=True)
        ac._matriz = ac._vet.fit_transform(t.texto for t in ac.trechos)
    return ac


def avaliar(pasta: Path, gabarito: list[dict], versao: str, mostrar: bool = True) -> float:
    cfg = VERSOES[versao]
    ac = montar_acervo(pasta, cfg)
    acertos = 0
    for item in gabarito:
        achados = ac.buscar(item["pergunta"], k=3, limiar=cfg["limiar"])
        if item["episodio"] is None:
            ok = not achados
        else:
            ok = any(t.episodio == str(item["episodio"]) and set(t.minutos) & set(item["minutos"]) for t, _ in achados)
        acertos += ok
        if mostrar:
            onde = ", ".join(f"{t.citacao}" for t, _ in achados) or "nada encontrado"
            print(f"{'✅' if ok else '❌'} {item['pergunta'][:55]:55} → {onde}")
    taxa = acertos / len(gabarito)
    if mostrar:
        print(f"\n{versao}: {acertos}/{len(gabarito)} acertos ({taxa:.0%})")
    return taxa


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--versao", choices=VERSOES, default="v2")
    p.add_argument("--pasta", type=Path, default=AQUI / "dados" / "transcricoes")
    p.add_argument("--gabarito", type=Path, default=AQUI / "dados" / "gabarito.json")
    a = p.parse_args()
    avaliar(a.pasta, json.loads(a.gabarito.read_text(encoding="utf-8")), a.versao)
