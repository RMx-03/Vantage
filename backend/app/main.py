from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import router as v1_router
from app.core.config import settings
from app.domain.errors import SafeError, VantageError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Vantage backend started")
    logger.info("Swagger UI available at http://localhost:8000/docs")
    logger.info("Ollama endpoint configured at %s", settings.OLLAMA_BASE_URL)
    yield
    logger.info("Vantage backend shutting down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "**Vantage** is a fully localized, multi-agent AI platform for "
        "event-driven quantitative financial research."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------


@app.exception_handler(VantageError)
async def vantage_error_handler(request: Request, exc: VantageError) -> JSONResponse:
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    if exc.code in {
        "MARKET_DATA_PROVIDER_FAILED",
        "MODEL_UNAVAILABLE",
        "EXTERNAL_SERVICE_UNAVAILABLE",
    }:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code in {"RUN_NOT_FOUND", "NOT_FOUND"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "INVALID_SYMBOL",
        "INVALID_PRICE_SERIES",
        "BAD_REQUEST",
        "VALIDATION_ERROR",
        "MODEL_OUTPUT_INVALID",
    }:
        status_code = status.HTTP_400_BAD_REQUEST

    safe_error = SafeError(
        code=exc.code,
        message=exc.safe_message,
        run_id=exc.run_id,
        retryable=exc.retryable,
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": safe_error.model_dump()},
    )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/", tags=["health"], summary="Health check")
async def health_check() -> dict:
    """
    Root health-check endpoint.

    Returns the application status and current version. Use this to confirm
    the server is running before sending analysis requests.
    """
    return {"status": "ok", "version": settings.APP_VERSION}
