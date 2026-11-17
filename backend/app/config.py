from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'acervo.db').as_posix()}"
    storage_dir: Path = BACKEND_DIR / "storage"
    cors_origins: list[str] = ["http://localhost:5102", "http://127.0.0.1:5102"]
    anthropic_api_key: str | None = None
    modelo_claude: str = "claude-sonnet-5-5"
    openai_api_key: str | None = None  # transcrição (Whisper) e, opcionalmente, embeddings
    voyage_api_key: str | None = None
    provedor_embeddings: str = "local"  # local | voyage | openai
    reescrever_pergunta: bool = False   # o Claude reescreve a pergunta antes da busca (1 chamada extra)
    n8n_token: str | None = None        # segredo compartilhado do webhook do n8n
    limite_midia_mb: int = 2048          # upload de áudio/vídeo (o arquivo vai direto para o disco)
    modelo_transcricao: str = "whisper-1"  # o único da OpenAI que devolve marcação de tempo por segmento
    parte_transcricao_s: int = 1200      # o áudio é cortado em partes de 20 min (~7 MB) — a API aceita até 25 MB
    ffmpeg_bin: str | None = None        # se vazio: ffmpeg do PATH ou o binário do pacote imageio-ffmpeg
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
