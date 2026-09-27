from pathlib import Path
from typing import List, Union, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root of the repository (two levels up from this file: core/ → app/ → backend/)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _BACKEND_DIR.parent

GROQ_STRICT_JSON_SCHEMA_MODELS: tuple[str, ...] = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
)


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
    # Semantic product version used for API display and package identity.
    APP_VERSION: str = "0.1.0"
    # Immutable revision of the running artifact (Git SHA or image/build digest).
    # Recorded on every research run so a persisted result identifies the exact
    # code that produced it. Defaults to "development" outside a built artifact.
    CODE_REVISION: str = "development"

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
    NEWS_LOOKBACK_DAYS: int = 7

    # ------------------------------------------------------------------
    # CORS — origins allowed to call the API
    # ------------------------------------------------------------------
    ALLOWED_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json

                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # ------------------------------------------------------------------
    # Ollama — local LLM server (used from Phase 3 onwards)
    # ------------------------------------------------------------------
    LLM_PROVIDER: str = "ollama"
    LLM_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    LLM_MAX_RETRIES: int = Field(default=1, ge=0)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "vantage-fin"

    # ------------------------------------------------------------------
    # Multi-Provider Cloud LLMs (Phase 3 Architecture Shift)
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_JSON_SCHEMA_MODELS: list[str] = Field(
        default_factory=lambda: list(GROQ_STRICT_JSON_SCHEMA_MODELS)
    )

    # ------------------------------------------------------------------
    # Supabase Authentication
    # ------------------------------------------------------------------
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # ------------------------------------------------------------------
    # First-party authentication (Phase 2)
    # ------------------------------------------------------------------
    # HS256 signing secret for access tokens. There is deliberately no
    # usable default: an application that signs tokens with a shipped
    # default is an application with no authentication at all.
    AUTH_JWT_SECRET: str = ""
    AUTH_JWT_ISSUER: str = "vantage"
    AUTH_JWT_AUDIENCE: str = "vantage-api"
    AUTH_ACCESS_TOKEN_TTL_SECONDS: int = Field(default=900, gt=0)
    AUTH_REFRESH_TOKEN_TTL_SECONDS: int = Field(default=2592000, gt=0)
    AUTH_COOKIE_NAME: str = "vantage_refresh"
    # Only ever false for local plain-HTTP development.
    AUTH_COOKIE_SECURE: bool = True
    # Configuration rather than constants so topology changes never need a code
    # change. "lax" is correct for every current deployment: local development
    # (localhost:5173 to localhost:8000 is same-site — SameSite ignores port) and
    # production, where a Vercel rewrite proxies /api to Heroku so the browser
    # sees one origin.
    AUTH_COOKIE_SAMESITE: str = "lax"
    # Empty means host-only, which is what production uses. `vercel.app` is on the
    # Public Suffix List, so a Domain-scoped cookie cannot be set there anyway.
    AUTH_COOKIE_DOMAIN: str = ""
    # Generous on purpose: corporate NAT, campus networks and mobile CGNAT
    # put many legitimate users behind one address. This bounds the Argon2
    # flood, it is not an anti-abuse control.
    AUTH_REGISTER_MAX_ATTEMPTS: int = Field(default=20, gt=0)
    AUTH_REGISTER_WINDOW_SECONDS: int = Field(default=3600, gt=0)
    AUTH_LOGIN_MAX_ATTEMPTS: int = Field(default=10, gt=0)
    AUTH_LOGIN_WINDOW_SECONDS: int = Field(default=900, gt=0)

    # ------------------------------------------------------------------
    # Database (PostgreSQL)
    # ------------------------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://vantage_runtime:vantage_runtime@localhost:5433/vantage_test"
    MIGRATION_DATABASE_URL: str = (
        "postgresql+psycopg://vantage_owner:vantage_owner@localhost:5433/vantage_test"
    )

    # ------------------------------------------------------------------
    # Telemetry and Observability (Phase 1 Task 8)
    # ------------------------------------------------------------------
    TRACE_EXPORT_ENABLED: bool = False
    TELEMETRY_USER_SALT: str = "vantage-telemetry-salt"
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_TIMEOUT_SECONDS: int = Field(default=5, gt=0)

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

# Substrings that mark a secret as a non-secret example value. A deployment
# that ships one of these is misconfigured, and failing to start is the only
# safe response.
_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "placeholder",
    "example",
    "your-secret",
)


def validate_auth_settings(active: Settings) -> None:
    """Fail fast when authentication is misconfigured.

    Called during application startup. Raising here stops the process; the
    alternative is a running API that issues forgeable tokens.
    """
    secret = active.AUTH_JWT_SECRET
    if not secret:
        raise RuntimeError("AUTH_JWT_SECRET must be set; refusing to start.")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "AUTH_JWT_SECRET must be at least 32 bytes; refusing to start."
        )
    lowered = secret.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        raise RuntimeError(
            "AUTH_JWT_SECRET looks like a placeholder; refusing to start."
        )
