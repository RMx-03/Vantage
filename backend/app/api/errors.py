"""Translate VantageError into its HTTP response.

Kept outside the exception handler so a route that must attach headers to an
error response — clearing a dead cookie, for instance — can build the same
response itself. Headers set on an injected Response are discarded once an
exception handler takes over, so re-raising is not an option there.
"""

from fastapi import status
from fastapi.responses import JSONResponse

from app.domain.errors import RUN_ALREADY_FINALIZED, SafeError, VantageError


def vantage_error_response(
    exc: VantageError, *, status_code: int | None = None
) -> JSONResponse:
    if status_code is None:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if exc.code in {
            "MARKET_DATA_PROVIDER_FAILED",
            "MODEL_UNAVAILABLE",
            "EXTERNAL_SERVICE_UNAVAILABLE",
        }:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif exc.code in {"RUN_NOT_FOUND", "NOT_FOUND"}:
            status_code = status.HTTP_404_NOT_FOUND
        elif exc.code == RUN_ALREADY_FINALIZED:
            status_code = status.HTTP_409_CONFLICT
        elif exc.code in {
            "INVALID_SYMBOL",
            "INVALID_PRICE_SERIES",
            "BAD_REQUEST",
            "VALIDATION_ERROR",
            "MODEL_OUTPUT_INVALID",
            "INVALID_CURSOR",
            "UNSUPPORTED_INSTRUMENT",
            "AUTH_WEAK_PASSWORD",
        }:
            status_code = status.HTTP_400_BAD_REQUEST
        elif exc.code in {"AUTH_REQUIRED", "AUTH_INVALID", "AUTH_TOKEN_EXPIRED"}:
            status_code = status.HTTP_401_UNAUTHORIZED
        elif exc.code in {"AUTH_RATE_LIMITED"}:
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        elif exc.code in {
            "AUTH_ACCOUNT_LOCKED",
            "CROSS_SITE_REQUEST_REJECTED",
            "AUTH_EMAIL_UNVERIFIED",
        }:
            status_code = status.HTTP_403_FORBIDDEN

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
