"""Mede a qualidade da busca contra um gabarito — portado de `agente-acervo/avaliar.py`.

A busca acerta quando algum dos 3 primeiros trechos cobre um dos minutos esperados (do episódio
esperado ou de uma alternativa aceita), ou, para perguntas fora do acervo, quando não devolve nada.

Uso:
  uv run python -m app.eval                          # v1, v2 e v3 nos dois gabaritos
  uv run python -m app.eval --versao v2 --mostrar    # detalhe por pergunta
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .search.engine import VERSOES, Indice, ler_transcricao

DATA = Path(__file__).resolve().parents[1] / "data"


def carregar_exemplos(numeros: set[str] | None = None) -> list:
    eps = []
    for arq in sorted((DATA / "transcricoes").glob("*.txt")):
        meta, falas = ler_transcricao(arq.read_text(encoding="utf-8"))
        num = meta.get("episodio", arq.stem)
        if numeros is None or num in numeros:
            eps.append((int(num), num, meta.get("titulo", arq.stem), falas))
    return eps


def acertou(item: dict, achados) -> bool:
    if item["episodio"] is None:
        return not achados
    alvos = [(str(item["episodio"]), set(item["minutos"]))] + [(str(a["episodio"]), set(a["minutos"])) for a in item.get("alternativos", [])]
    return any(r.trecho.episodio == ep and set(r.trecho.minutos) & mins for r in achados for ep, mins in alvos)


def avaliar(gabarito: list[dict], episodios: list, versao: str, mostrar: bool = False) -> dict:
    ind = Indice(episodios, versao)
    linhas = []
    for item in gabarito:
        achados = ind.buscar(item["pergunta"], k=3)
        ok = acertou(item, achados)
        linhas.append({"pergunta": item["pergunta"], "ok": ok, "achados": [r.trecho.citacao for r in achados]})
        if mostrar:
            print(f"  {'ok   ' if ok else 'ERRO '} {item['pergunta'][:55]:55} → {', '.join(r.trecho.citacao for r in achados) or 'nada encontrado'}")
    acertos = sum(l["ok"] for l in linhas)
    return {"versao": versao, "acertos": acertos, "total": len(linhas), "taxa": round(acertos / len(linhas), 3), "linhas": linhas}


def relatorio(mostrar: bool = False, versoes: list[str] | None = None) -> dict:
    suites = {
        "original (2 episódios, 9 perguntas)": (json.loads((DATA / "gabarito_v1.json").read_text(encoding="utf-8")), carregar_exemplos({"1", "2"})),
        "ampliado (6 episódios, 20 perguntas)": (json.loads((DATA / "gabarito_v3.json").read_text(encoding="utf-8")), carregar_exemplos()),
    }
    saida = {}
    for nome, (gab, eps) in suites.items():
        saida[nome] = {}
        for v in versoes or list(VERSOES):
            if mostrar:
                print(f"\n[{nome}] {v}")
            r = avaliar(gab, eps, v, mostrar)
            saida[nome][v] = r
            print(f"{nome:40} {v}: {r['acertos']}/{r['total']} ({r['taxa']:.0%})")
    return saida


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--versao", choices=list(VERSOES))
    ap.add_argument("--mostrar", action="store_true")
    a = ap.parse_args()
    relatorio(a.mostrar, [a.versao] if a.versao else None)
