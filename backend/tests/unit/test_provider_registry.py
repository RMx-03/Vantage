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


def test_two_news_providers_are_refused_until_merge() -> None:
    with pytest.raises(VantageError) as exc:
        build_providers(
            Settings(_env_file=None, NEWS_PROVIDERS=["yfinance", "fixture"])
        )
    assert exc.value.code == "CONFIG_ERROR"


def test_duplicate_registration_raises() -> None:
    registry = ProviderRegistry()
    registry.register("market", "x", lambda s: None)
    with pytest.raises(ValueError):
        registry.register("market", "x", lambda s: None)


def test_names_are_sorted() -> None:
    assert default_registry().names("llm") == ("disabled", "gemini", "groq", "ollama")
