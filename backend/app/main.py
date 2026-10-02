from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.errors import vantage_error_response
from app.api.v1.routes import router as v1_router
from app.core.config import settings, validate_auth_settings
from app.domain.errors import RUN_ALREADY_FINALIZED, SafeError, VantageError
from app.telemetry.tracing import configure_telemetry, get_tracer

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
    # Fail closed before serving a single request. PyJWT signs and verifies
    # HS256 with a zero-length key and only warns, so an application that boots
    # without a real secret issues tokens anyone can forge.
    validate_auth_settings(settings)
    configure_telemetry(app)
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
        "**Vantage** provides transparent, traceable end-of-day research "
        "assistance for supported US-listed equities."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------


@app.exception_handler(VantageError)
async def vantage_error_handler(request: Request, exc: VantageError) -> JSONResponse:
    return vantage_error_response(exc)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    safe_error = SafeError(
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        retryable=False,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


@app.middleware("http")
async def research_run_trace(request: Request, call_next):
    research_runs_path = f"{settings.API_V1_PREFIX.rstrip('/')}/research-runs"
    if request.method == "POST" and request.url.path.rstrip("/") == research_runs_path:
        with get_tracer().start_as_current_span("research_run"):
            return await call_next(request)
    return await call_next(request)


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
