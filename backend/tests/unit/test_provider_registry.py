import logging

import pytest

from app.core.config import Settings
from app.domain.errors import VantageError
from app.providers.llm import (
    DisabledInterpretationProvider,
    GeminiInterpretationProvider,
    GroqInterpretationProvider,
    OllamaInterpretationProvider,
)
from app.providers.registry import (
    ProviderRegistry,
    build_interpretation_provider,
    build_providers,
    default_registry,
)
from app.providers.yfinance_provider import YFinanceSnapshotProvider


def test_default_settings_build_todays_providers() -> None:
    providers = build_providers(Settings(_env_file=None))

    assert isinstance(providers.market, YFinanceSnapshotProvider)
    assert len(providers.news) == 1
    assert isinstance(providers.news[0], YFinanceSnapshotProvider)
    assert providers.filings is None
    assert providers.fundamentals is None
    assert providers.macro is None
    assert providers.crosscheck is None
    assert providers.not_configured == (
        "filings",
        "fundamentals",
        "macro",
        "crosscheck",
    )


def test_unknown_name_is_config_error_without_echo() -> None:
    with pytest.raises(VantageError) as exc:
        build_providers(Settings(_env_file=None, MARKET_PROVIDER="alpacca"))

    assert exc.value.code == "CONFIG_ERROR"
    assert "alpacca" not in exc.value.safe_message


def test_empty_selector_is_config_error() -> None:
    with pytest.raises(VantageError) as exc:
        build_providers(Settings(_env_file=None, MARKET_PROVIDER=""))
    assert exc.value.code == "CONFIG_ERROR"


def test_unknown_optional_role_name_is_config_error() -> None:
    with pytest.raises(VantageError) as exc:
        build_providers(Settings(_env_file=None, FILINGS_PROVIDER="edgarr"))
    assert exc.value.code == "CONFIG_ERROR"
    assert "edgarr" not in exc.value.safe_message


@pytest.mark.parametrize(
    ("provider_name", "expected_cls"),
    [
        ("disabled", DisabledInterpretationProvider),
        ("gemini", GeminiInterpretationProvider),
        ("groq", GroqInterpretationProvider),
        ("ollama", OllamaInterpretationProvider),
    ],
)
def test_llm_names_build_the_same_classes(
    provider_name: str, expected_cls: type
) -> None:
    provider = build_interpretation_provider(
        Settings(_env_file=None, LLM_PROVIDER=provider_name)
    )
    assert isinstance(provider, expected_cls)


def test_unknown_llm_keeps_its_message() -> None:
    with pytest.raises(VantageError) as exc:
        build_interpretation_provider(Settings(_env_file=None, LLM_PROVIDER="nope"))
    assert exc.value.code == "CONFIG_ERROR"
    assert (
        exc.value.safe_message
        == "The configured AI interpretation provider is unsupported."
    )


def test_factory_returning_none_marks_role_not_configured() -> None:
    registry = ProviderRegistry()
    registry.register("market", "yfinance", lambda s: None)
    registry.register("news", "yfinance", lambda s: YFinanceSnapshotProvider())
    for name, factory in (
        ("disabled", lambda s: DisabledInterpretationProvider()),
        ("gemini", lambda s: DisabledInterpretationProvider()),
    ):
        registry.register("llm", name, factory)

    providers = build_providers(
        Settings(_env_file=None, LLM_PROVIDER="disabled"), registry
    )

    assert providers.market is None
    assert "market" in providers.not_configured


def test_two_news_providers_build_with_keys() -> None:
    providers = build_providers(
        Settings(
            _env_file=None,
            NEWS_PROVIDERS=["alpaca", "finnhub"],
            ALPACA_API_KEY_ID="id",
            ALPACA_API_SECRET_KEY="secret",
            FINNHUB_API_KEY="fh",
        )
    )
    assert [p.name for p in providers.news] == ["alpaca", "finnhub"]
    assert "news" not in providers.not_configured


def test_missing_alpaca_key_leaves_one_news_provider_configured() -> None:
    providers = build_providers(
        Settings(
            _env_file=None,
            NEWS_PROVIDERS=["alpaca", "finnhub"],
            FINNHUB_API_KEY="fh",
        )
    )
    assert [p.name for p in providers.news] == ["finnhub"]
    assert "news" not in providers.not_configured


def test_duplicate_registration_raises() -> None:
    registry = ProviderRegistry()
    registry.register("market", "x", lambda s: None)
    with pytest.raises(ValueError):
        registry.register("market", "x", lambda s: None)


def test_names_are_sorted() -> None:
    assert default_registry().names("llm") == ("disabled", "gemini", "groq", "ollama")


# (role attribute, settings that select it, key fields, header holding the value)
_CRED_CASES = [
    (
        "market",
        {"MARKET_PROVIDER": "alpaca"},
        ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"),
        "APCA-API-KEY-ID",
    ),
    (
        "news",
        {"NEWS_PROVIDERS": ["alpaca"]},
        ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"),
        "APCA-API-KEY-ID",
    ),
    (
        "news",
        {"NEWS_PROVIDERS": ["finnhub"]},
        ("FINNHUB_API_KEY",),
        "X-Finnhub-Token",
    ),
    (
        "filings",
        {"FILINGS_PROVIDER": "edgar"},
        ("SEC_USER_AGENT",),
        "User-Agent",
    ),
    ("macro", {"MACRO_PROVIDER": "fred"}, ("FRED_API_KEY",), None),
    (
        "crosscheck",
        {"PRICE_CROSSCHECK_PROVIDER": "tiingo"},
        ("TIINGO_API_KEY",),
        "Authorization",
    ),
]


def _built(role: str, providers):
    built = getattr(providers, role)
    return built[0] if role == "news" and built else built


@pytest.mark.parametrize(("role", "select", "fields", "header"), _CRED_CASES)
def test_credentials_are_stripped(role, select, fields, header) -> None:
    values = {f: f"  value-{f.lower()}\t" for f in fields}
    providers = build_providers(Settings(_env_file=None, **select, **values))
    built = _built(role, providers)
    assert built is not None
    if header is not None:
        sent = built._http._client.headers[header]
        assert "  " not in sent and not sent.endswith(("\t", " "))
        if header != "Authorization" and header != "User-Agent":
            assert sent == f"value-{fields[0].lower()}"


@pytest.mark.parametrize("planted", ["cl\u00e9-secret", "key\u2013secret"])
@pytest.mark.parametrize(("role", "select", "fields", "header"), _CRED_CASES)
def test_unusable_credentials_leave_the_role_unconfigured(
    role, select, fields, header, planted, caplog
) -> None:
    values = {f: "plainvalue" for f in fields}
    values[fields[-1]] = planted
    with caplog.at_level(logging.DEBUG):
        providers = build_providers(Settings(_env_file=None, **select, **values))
    assert _built(role, providers) in (None, ())
    assert planted not in caplog.text
    assert "provider_credential_unusable" in caplog.text
    assert role in providers.not_configured


def test_whitespace_only_credential_is_unconfigured(caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        providers = build_providers(
            Settings(
                _env_file=None,
                NEWS_PROVIDERS=["finnhub"],
                FINNHUB_API_KEY="   ",
            )
        )
    assert providers.news == ()
    assert "news" in providers.not_configured
