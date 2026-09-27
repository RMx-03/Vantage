import pytest

from app.core.config import Settings, validate_auth_settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"AUTH_JWT_SECRET": "x" * 32}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_defaults_match_the_spec() -> None:
    s = _settings()
    assert s.AUTH_ACCESS_TOKEN_TTL_SECONDS == 900
    assert s.AUTH_REFRESH_TOKEN_TTL_SECONDS == 2592000
    assert s.AUTH_COOKIE_NAME == "vantage_refresh"
    assert s.AUTH_COOKIE_SAMESITE == "lax"
    assert s.AUTH_COOKIE_DOMAIN == ""
    assert s.AUTH_JWT_ISSUER == "vantage"
    assert s.AUTH_JWT_AUDIENCE == "vantage-api"


def test_empty_secret_is_refused() -> None:
    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        validate_auth_settings(_settings(AUTH_JWT_SECRET=""))


def test_short_secret_is_refused() -> None:
    with pytest.raises(RuntimeError, match="at least 32"):
        validate_auth_settings(_settings(AUTH_JWT_SECRET="tooshort"))


def test_placeholder_secret_is_refused() -> None:
    with pytest.raises(RuntimeError, match="placeholder"):
        validate_auth_settings(_settings(AUTH_JWT_SECRET="change-me" + "0" * 30))


def test_valid_secret_is_accepted() -> None:
    validate_auth_settings(_settings(AUTH_JWT_SECRET="a" * 32))
