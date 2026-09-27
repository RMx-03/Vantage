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


def test_app_refuses_to_start_without_a_valid_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup must run validate_auth_settings.

    PyJWT signs and verifies HS256 with a zero-length key, emitting only a
    warning. An application that boots with an empty AUTH_JWT_SECRET therefore
    accepts tokens anyone can forge, so refusing to start is the only safe
    behaviour.
    """
    from fastapi.testclient import TestClient

    from app.core.config import settings as live_settings
    from app.main import app

    monkeypatch.setattr(live_settings, "AUTH_JWT_SECRET", "")

    with pytest.raises(RuntimeError, match="AUTH_JWT_SECRET"):
        with TestClient(app):
            pass


def test_app_starts_with_a_valid_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.core.config import settings as live_settings
    from app.main import app

    monkeypatch.setattr(live_settings, "AUTH_JWT_SECRET", "z" * 48)

    with TestClient(app) as client:
        assert client.get("/").status_code == 200


def test_settings_repr_does_not_expose_secret_values() -> None:
    """A traceback must never print credentials.

    Pydantic's default repr prints every field, so any AttributeError touching
    settings dumped the live Gemini key, both Langfuse keys, the telemetry salt
    and the JWT signing secret into the output — CI logs, error trackers and
    crash reports included.
    """
    probe = Settings(
        AUTH_JWT_SECRET="j" * 40,
        GEMINI_API_KEY="AIza-secret-gemini-value",
        GROQ_API_KEY="gsk-secret-groq-value",
        LANGFUSE_SECRET_KEY="sk-lf-secret-langfuse-value",
        LANGFUSE_PUBLIC_KEY="pk-lf-public-langfuse-value",
        TELEMETRY_USER_SALT="salt-secret-value",
    )  # type: ignore[call-arg]

    rendered = repr(probe) + str(probe)

    for secret in (
        "j" * 40,
        "AIza-secret-gemini-value",
        "gsk-secret-groq-value",
        "sk-lf-secret-langfuse-value",
        "pk-lf-public-langfuse-value",
        "salt-secret-value",
    ):
        assert secret not in rendered, f"{secret!r} leaked through the settings repr"


def test_settings_repr_still_shows_non_secret_fields() -> None:
    """Redaction must not make the repr useless for debugging."""
    rendered = repr(Settings(AUTH_JWT_SECRET="j" * 40))  # type: ignore[call-arg]
    assert "APP_NAME" in rendered
    assert "Vantage" in rendered


def test_the_shipped_telemetry_salt_default_is_refused() -> None:
    """The salt is what keeps hashed emails and IPs irreversible.

    IPv4 has roughly 4.3 billion addresses. With a publicly known salt, every
    ip_hash in auth_attempts and refresh_tokens can be reversed in seconds, so
    a deployment still carrying the shipped default does not in fact keep raw
    addresses out of the database.
    """
    with pytest.raises(RuntimeError, match="TELEMETRY_USER_SALT"):
        validate_auth_settings(_settings(TELEMETRY_USER_SALT="vantage-telemetry-salt"))


def test_an_empty_telemetry_salt_is_refused() -> None:
    with pytest.raises(RuntimeError, match="TELEMETRY_USER_SALT"):
        validate_auth_settings(_settings(TELEMETRY_USER_SALT=""))


def test_a_strong_telemetry_salt_is_accepted() -> None:
    validate_auth_settings(_settings(TELEMETRY_USER_SALT="s" * 32))
