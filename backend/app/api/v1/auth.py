import hashlib

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from app.api.client_ip import client_ip
from app.api.errors import vantage_error_response
from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.domain.auth import (
    AUTH_RATE_LIMITED,
    AUTH_REQUIRED,
    GENERIC_ACCEPTED_MESSAGE,
)
from app.domain.errors import VantageError
from app.repositories.auth_attempts import AuthAttemptRepository, attempt_key
from app.repositories.users import UserRepository
from app.services.account import AccountService
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class CredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


class AcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    email: str
    email_verified: bool


def get_auth_service() -> AuthService:
    return AuthService()


def _client_ip_hash(request: Request) -> str | None:
    """Salted hash of the client address. The raw address is never stored."""
    address = client_ip(request)
    if address is None:
        return None
    salted = f"{settings.TELEMETRY_USER_SALT}:{address}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def _cookie_kwargs() -> dict[str, object]:
    """Attributes shared by setting and clearing the refresh cookie.

    They must match exactly or the browser treats the clear as a different
    cookie and silently keeps the old one. Domain and SameSite are configured
    rather than fixed because the SPA (Vercel) and API (Heroku) may or may not
    share a registrable domain. See ADR-0006.
    """
    kwargs: dict[str, object] = {
        "key": settings.AUTH_COOKIE_NAME,
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE.capitalize()
        if settings.AUTH_COOKIE_SAMESITE
        else "Lax",
        "path": f"{settings.API_V1_PREFIX}/auth",
    }
    if settings.AUTH_COOKIE_DOMAIN:
        kwargs["domain"] = settings.AUTH_COOKIE_DOMAIN
    return kwargs


def reject_cross_site(request: Request) -> None:
    """Refuse cookie-authenticated actions initiated from another site.

    SameSite=Lax already withholds the cookie from cross-site POSTs, but the
    cookie's SameSite is configuration. Sec-Fetch-Site is computed by the
    browser, cannot be set by page script, and survives the Vercel proxy as
    "same-origin", so this holds regardless of topology. Non-browser clients
    omit the header and are not CSRF vectors, so its absence is allowed.
    """
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise VantageError(
            code="CROSS_SITE_REQUEST_REJECTED",
            safe_message="This request must come from the Vantage application.",
        )


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        value=raw_token,
        max_age=settings.AUTH_REFRESH_TOKEN_TTL_SECONDS,
        **_cookie_kwargs(),  # type: ignore[arg-type]
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(**_cookie_kwargs())  # type: ignore[arg-type]


@router.post(
    "/register", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedResponse
)
def register(
    payload: CredentialsRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> AcceptedResponse:
    service.register(
        email=str(payload.email),
        password=payload.password,
        ip_hash=_client_ip_hash(request),
    )
    # Identical body whether or not the address was already registered.
    return AcceptedResponse(message=GENERIC_ACCEPTED_MESSAGE)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: CredentialsRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    issued = service.login(
        email=str(payload.email),
        password=payload.password,
        user_agent=request.headers.get("user-agent"),
        ip_hash=_client_ip_hash(request),
    )
    _set_refresh_cookie(response, issued.refresh_token)
    return TokenResponse(access_token=issued.access_token, expires_in=issued.expires_in)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(reject_cross_site)],
)
def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    raw = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not raw:
        raise VantageError(
            code=AUTH_REQUIRED, safe_message="Authentication is required."
        )

    try:
        issued = service.refresh(
            raw,
            user_agent=request.headers.get("user-agent"),
            ip_hash=_client_ip_hash(request),
        )
    except VantageError as exc:
        # A dead cookie must not linger: the browser would retry it forever.
        # Build the error response here rather than re-raising — the exception
        # handler constructs a fresh response and would discard the deletion.
        failure = vantage_error_response(exc)
        _clear_refresh_cookie(failure)
        return failure  # type: ignore[return-value]

    _set_refresh_cookie(response, issued.refresh_token)
    return TokenResponse(access_token=issued.access_token, expires_in=issued.expires_in)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(reject_cross_site)],
)
def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> Response:
    raw = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if raw:
        service.logout(raw)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.logout_all(user.id)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
def me(user: AuthenticatedUser = Depends(get_current_user)) -> MeResponse:
    stored = UserRepository().find_by_public_id(user.id)
    if stored is None:
        raise VantageError(
            code=AUTH_REQUIRED, safe_message="Authentication is required."
        )
    return MeResponse(
        id=str(stored.public_id),
        email=stored.email,
        email_verified=stored.email_verified,
    )


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    password: str


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str


def get_account_service() -> AccountService:
    return AccountService()


def get_attempt_repository() -> AuthAttemptRepository:
    return AuthAttemptRepository()


@router.post("/verify-email", response_model=AcceptedResponse)
def verify_email(
    payload: TokenRequest,
    accounts: AccountService = Depends(get_account_service),
) -> AcceptedResponse | JSONResponse:
    try:
        accounts.verify_email(payload.token)
    except VantageError as exc:
        return vantage_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
    return AcceptedResponse(message="Your address is confirmed.")


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
)
def resend_verification(
    payload: EmailRequest,
    accounts: AccountService = Depends(get_account_service),
    attempts: AuthAttemptRepository = Depends(get_attempt_repository),
) -> AcceptedResponse:
    key = attempt_key("resend", str(payload.email))
    if attempts.is_rate_limited(
        key,
        window_seconds=settings.AUTH_EMAIL_ACTION_WINDOW_SECONDS,
        max_attempts=settings.AUTH_EMAIL_ACTION_MAX_ATTEMPTS,
    ):
        raise VantageError(
            code=AUTH_RATE_LIMITED,
            safe_message="Too many attempts. Try again shortly.",
            retryable=True,
        )
    attempts.record(key)
    accounts.resend_verification(str(payload.email))
    return AcceptedResponse(message=GENERIC_ACCEPTED_MESSAGE)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
)
def forgot_password(
    payload: EmailRequest,
    accounts: AccountService = Depends(get_account_service),
    attempts: AuthAttemptRepository = Depends(get_attempt_repository),
) -> AcceptedResponse:
    key = attempt_key("reset", str(payload.email))
    if attempts.is_rate_limited(
        key,
        window_seconds=settings.AUTH_EMAIL_ACTION_WINDOW_SECONDS,
        max_attempts=settings.AUTH_EMAIL_ACTION_MAX_ATTEMPTS,
    ):
        raise VantageError(
            code=AUTH_RATE_LIMITED,
            safe_message="Too many attempts. Try again shortly.",
            retryable=True,
        )
    attempts.record(key)
    accounts.request_password_reset(str(payload.email))
    # Identical body for registered and unregistered addresses.
    return AcceptedResponse(message=GENERIC_ACCEPTED_MESSAGE)


@router.post("/reset-password", response_model=AcceptedResponse)
def reset_password(
    payload: ResetPasswordRequest,
    response: Response,
    accounts: AccountService = Depends(get_account_service),
) -> AcceptedResponse | JSONResponse:
    try:
        accounts.reset_password(payload.token, payload.password)
    except VantageError as exc:
        # Nothing was revoked on failure, so the session cookie stays. Clearing
        # it on an expired link or a weak password signed out a valid session.
        return vantage_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
    # Every session was revoked; the browser's cookie is now dead.
    _clear_refresh_cookie(response)
    return AcceptedResponse(message="Your password has been changed. Sign in again.")


@router.post("/change-password", response_model=AcceptedResponse)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    accounts: AccountService = Depends(get_account_service),
) -> AcceptedResponse:
    accounts.change_password(user.id, payload.current_password, payload.new_password)
    _clear_refresh_cookie(response)
    return AcceptedResponse(message="Your password has been changed. Sign in again.")
