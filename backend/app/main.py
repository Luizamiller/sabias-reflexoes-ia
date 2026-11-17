import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import get_settings

cfg = get_settings()
logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s · %(message)s")
log = logging.getLogger("acervo")

app = FastAPI(title="Acervo · Às Sábias Reflexões", version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.exception_handler(Exception)
async def erro_inesperado(request: Request, exc: Exception):
    log.exception("erro em %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Algo deu errado do nosso lado. Tente de novo."}, status_code=500)


DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str):
        alvo = DIST / caminho
        return FileResponse(alvo if alvo.is_file() else DIST / "index.html")
