from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Root of the repository (two levels up from this file: core/ → app/ → backend/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    """
    Centralised application configuration.

    All values can be overridden by setting the corresponding environment
    variable (case-insensitive) or by placing them in a .env file at
    backend/.env.
    """

    # ------------------------------------------------------------------
    # Application metadata
    # ------------------------------------------------------------------
    APP_NAME: str = "Vantage"
    APP_VERSION: str = "0.1.0"

    # ------------------------------------------------------------------
    # Local model store
    # vantage_ai/ lives at the repo root and is gitignored.
    # It holds the fine-tuned .gguf file used by Ollama.
    # ------------------------------------------------------------------
    VANTAGE_AI_DIR: Path = _REPO_ROOT / "vantage_ai"

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    API_V1_PREFIX: str = "/api/v1"

    # ------------------------------------------------------------------
    # CORS — origins allowed to call the API
    # ------------------------------------------------------------------
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # CRA / other dev server
    ]

    # ------------------------------------------------------------------
    # Ollama — local LLM server (used from Phase 3 onwards)
    # ------------------------------------------------------------------
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "vantage-fin"
    OLLAMA_TIMEOUT_SECONDS: int = 60
    OLLAMA_MAX_RETRIES: int = 2

    # ------------------------------------------------------------------
    # Risk thresholds (used from Phase 2 onwards)
    # ------------------------------------------------------------------
    VOLATILITY_THRESHOLD: float = 0.40  # annualised vol ceiling
    SENTIMENT_REJECTION_THRESHOLD: float = 0.2  # sentiment floor

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# ---------------------------------------------------------------------------
# Singleton — import this everywhere, never instantiate Settings directly.
# ---------------------------------------------------------------------------
settings = Settings()
