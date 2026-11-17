/** Como o backend deste projeto sobe dentro do navegador na demonstração online. */
export const CONFIG_DEMO = {
  nome: "Acervo · Às Sábias Reflexões",
  repo: "https://github.com/Luizamiller/sabias-reflexoes-ia",
  servidor: {
    pacotes: ["fastapi", "pydantic", "sqlalchemy", "numpy", "scikit-learn", "cryptography", "httpx"],
    micropip: ["pydantic-settings", "python-multipart"],
    env: {"DATABASE_URL": "sqlite:////tmp/acervo.db", "STORAGE_DIR": "/tmp/storage"} as Record<string, string>,
    inicio: "from app.db import Base, engine\nfrom app.seed import semear\nBase.metadata.create_all(engine)\nsemear()\nfrom app.main import app",
  },
};
