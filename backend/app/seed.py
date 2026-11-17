"""Carrega os episódios de exemplo (FICTÍCIOS) pelo mesmo pipeline usado em produção.

Uso:  uv run python -m app.seed
"""
from __future__ import annotations

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .eval import DATA
from .models import Episodio, Segmento
from .pipeline.processar import processar
from .search.engine import ler_transcricao


def semear() -> int:
    criados = []
    with SessionLocal() as db:
        if db.scalar(select(Episodio).limit(1)):
            return 0
        for arq in sorted((DATA / "transcricoes").glob("*.txt")):
            meta, falas = ler_transcricao(arq.read_text(encoding="utf-8"))
            ep = Episodio(numero=meta.get("episodio", arq.stem), titulo=meta.get("titulo", arq.stem),
                          convidados=meta.get("convidados", "Sem convidados"), origem="exemplo",
                          duracao_s=falas[-1].inicio + 15)
            ep.segmentos = [Segmento(inicio_s=f.inicio, texto=f.texto) for f in falas]
            db.add(ep)
            db.flush()
            criados.append(ep.id)
        db.commit()
    for eid in criados:
        processar(eid)
    return len(criados)


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    n = semear()
    print(f"{n} episódios de exemplo carregados." if n else "Acervo já tinha episódios; nada a fazer.")
