import hashlib

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.domain.auth import AUTH_REQUIRED, GENERIC_ACCEPTED_MESSAGE
from app.domain.errors import VantageError
from app.repositories.users import UserRepository
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
    client = request.client
    if client is None:
        return None
    salted = f"{settings.TELEMETRY_USER_SALT}:{client.host}"
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
    service: AuthService = Depends(get_auth_service),
) -> AcceptedResponse:
    service.register(email=str(payload.email), password=payload.password)
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


@router.post("/refresh", response_model=TokenResponse)
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
    except VantageError:
        # A dead cookie must not linger: the browser would retry with it forever.
        _clear_refresh_cookie(response)
        raise

    _set_refresh_cookie(response, issued.refresh_token)
    return TokenResponse(access_token=issued.access_token, expires_in=issued.expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
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
