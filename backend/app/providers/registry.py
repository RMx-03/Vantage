"""One registry that builds every provider role from settings.

Later stages add providers by registering factories; nothing else in the
research path needs to know which implementation serves a role.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.core.config import Settings
from app.domain.errors import VantageError
from app.providers.alpaca import AlpacaMarketProvider, AlpacaNewsProvider
from app.providers.contracts import (
    FilingsProvider,
    FundamentalsProvider,
    InterpretationProvider,
    MacroProvider,
    MarketDataProvider,
    NewsProvider,
    PriceCrossCheckProvider,
)
from app.providers.finnhub import FinnhubNewsProvider
from app.providers.fixture_provider import FixtureProvider
from app.providers.llm import (
    DisabledInterpretationProvider,
    GeminiInterpretationProvider,
    GroqInterpretationProvider,
    OllamaInterpretationProvider,
)
from app.providers.yfinance_provider import YFinanceSnapshotProvider

ProviderRole = Literal["market", "news", "filings", "macro", "crosscheck", "llm"]
ProviderFactory = Callable[[Settings], object | None]

# Roles where the literal name "none" turns the role off.
_OPTIONAL_ROLES: frozenset[str] = frozenset({"filings", "macro", "crosscheck"})


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[tuple[str, str], ProviderFactory] = {}

    def register(self, role: ProviderRole, name: str, factory: ProviderFactory) -> None:
        key = (role, name)
        if key in self._factories:
            raise ValueError(f"Provider already registered for {role}: {name}")
        self._factories[key] = factory

    def names(self, role: ProviderRole) -> tuple[str, ...]:
        return tuple(sorted(n for r, n in self._factories if r == role))

    def build(self, role: ProviderRole, name: str, settings: Settings) -> object | None:
        if role in _OPTIONAL_ROLES and name == "none":
            return None
        factory = self._factories.get((role, name))
        if factory is None:
            message = (
                "The configured AI interpretation provider is unsupported."
                if role == "llm"
                else f"The configured {role} data provider is unsupported."
            )
            raise VantageError(code="CONFIG_ERROR", safe_message=message)
        return factory(settings)


@dataclass(frozen=True)
class ProviderSet:
    market: MarketDataProvider | None
    news: tuple[NewsProvider, ...]
    filings: FilingsProvider | None
    fundamentals: FundamentalsProvider | None
    macro: MacroProvider | None
    crosscheck: PriceCrossCheckProvider | None
    llm: InterpretationProvider
    not_configured: tuple[str, ...]


def _fixture(_: Settings) -> object:
    return FixtureProvider()


def _yfinance(_: Settings) -> object:
    return YFinanceSnapshotProvider()


def _alpaca_market(s: Settings) -> object | None:
    if not (s.ALPACA_API_KEY_ID and s.ALPACA_API_SECRET_KEY):
        return None
    return AlpacaMarketProvider(
        s.ALPACA_API_KEY_ID,
        s.ALPACA_API_SECRET_KEY,
        timeout_seconds=float(s.PROVIDER_TIMEOUT_SECONDS),
    )


def _alpaca_news(s: Settings) -> object | None:
    if not (s.ALPACA_API_KEY_ID and s.ALPACA_API_SECRET_KEY):
        return None
    return AlpacaNewsProvider(
        s.ALPACA_API_KEY_ID,
        s.ALPACA_API_SECRET_KEY,
        timeout_seconds=float(s.PROVIDER_TIMEOUT_SECONDS),
    )


def _finnhub_news(s: Settings) -> object | None:
    if not s.FINNHUB_API_KEY:
        return None
    return FinnhubNewsProvider(
        s.FINNHUB_API_KEY, timeout_seconds=float(s.PROVIDER_TIMEOUT_SECONDS)
    )


@lru_cache(maxsize=1)
def default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register("market", "alpaca", _alpaca_market)
    registry.register("market", "yfinance", _yfinance)
    registry.register("news", "alpaca", _alpaca_news)
    registry.register("news", "finnhub", _finnhub_news)
    registry.register("news", "yfinance", _yfinance)
    registry.register("market", "fixture", _fixture)
    registry.register("news", "fixture", _fixture)
    registry.register("llm", "disabled", lambda s: DisabledInterpretationProvider())
    registry.register(
        "llm",
        "gemini",
        lambda s: GeminiInterpretationProvider(
            api_key=s.GEMINI_API_KEY,
            model=s.GEMINI_MODEL,
            timeout_seconds=s.LLM_TIMEOUT_SECONDS,
            max_retries=s.LLM_MAX_RETRIES,
        ),
    )
    registry.register(
        "llm",
        "groq",
        lambda s: GroqInterpretationProvider(
            api_key=s.GROQ_API_KEY,
            model=s.GROQ_MODEL,
            json_schema_models=s.GROQ_JSON_SCHEMA_MODELS,
            timeout_seconds=s.LLM_TIMEOUT_SECONDS,
            max_retries=s.LLM_MAX_RETRIES,
        ),
    )
    registry.register(
        "llm",
        "ollama",
        lambda s: OllamaInterpretationProvider(
            base_url=s.OLLAMA_BASE_URL,
            model=s.OLLAMA_MODEL,
            timeout_seconds=s.LLM_TIMEOUT_SECONDS,
            max_retries=s.LLM_MAX_RETRIES,
        ),
    )
    return registry


def build_interpretation_provider(
    settings: Settings, registry: ProviderRegistry | None = None
) -> InterpretationProvider:
    reg = registry or default_registry()
    provider = reg.build("llm", settings.LLM_PROVIDER.lower().strip(), settings)
    if provider is None:
        raise VantageError(
            code="CONFIG_ERROR",
            safe_message="The configured AI interpretation provider is unsupported.",
        )
    return provider  # type: ignore[return-value]


def build_providers(
    settings: Settings, registry: ProviderRegistry | None = None
) -> ProviderSet:
    reg = registry or default_registry()
    market = reg.build("market", settings.MARKET_PROVIDER, settings)
    news = tuple(
        provider
        for name in settings.NEWS_PROVIDERS
        if (provider := reg.build("news", name, settings)) is not None
    )
    filings = reg.build("filings", settings.FILINGS_PROVIDER, settings)
    macro = reg.build("macro", settings.MACRO_PROVIDER, settings)
    crosscheck = reg.build("crosscheck", settings.PRICE_CROSSCHECK_PROVIDER, settings)
    fundamentals = (
        filings if callable(getattr(filings, "fetch_fundamentals", None)) else None
    )
    llm = build_interpretation_provider(settings, reg)

    not_configured = tuple(
        role
        for role, built in (
            ("market", market),
            ("news", news or None),
            ("filings", filings),
            ("fundamentals", fundamentals),
            ("macro", macro),
            ("crosscheck", crosscheck),
        )
        if built is None
    )
    return ProviderSet(
        market=market,  # type: ignore[arg-type]
        news=news,  # type: ignore[arg-type]
        filings=filings,  # type: ignore[arg-type]
        fundamentals=fundamentals,  # type: ignore[arg-type]
        macro=macro,  # type: ignore[arg-type]
        crosscheck=crosscheck,  # type: ignore[arg-type]
        llm=llm,
        not_configured=not_configured,
    )
