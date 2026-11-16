import pytest
from pydantic import ValidationError

from app.core.config import Settings

PROVIDER_ENV = (
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "FINNHUB_API_KEY",
    "FRED_API_KEY",
    "TIINGO_API_KEY",
    "SEC_USER_AGENT",
    "MARKET_PROVIDER",
    "NEWS_PROVIDERS",
    "FILINGS_PROVIDER",
    "MACRO_PROVIDER",
    "PRICE_CROSSCHECK_PROVIDER",
    "PROVIDER_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def _clean_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)


def build() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_provider_defaults_are_the_free_providers() -> None:
    s = build()
    assert s.MARKET_PROVIDER == "alpaca"
    assert s.NEWS_PROVIDERS == ["alpaca", "finnhub"]
    assert s.FILINGS_PROVIDER == "edgar"
    assert s.MACRO_PROVIDER == "fred"
    assert s.PRICE_CROSSCHECK_PROVIDER == "none"
    assert s.PROVIDER_TIMEOUT_SECONDS == 6
    for name in (
        "ALPACA_API_KEY_ID",
        "ALPACA_API_SECRET_KEY",
        "FINNHUB_API_KEY",
        "FRED_API_KEY",
        "TIINGO_API_KEY",
        "SEC_USER_AGENT",
    ):
        assert getattr(s, name) == ""


@pytest.mark.parametrize(
    "name",
    [
        "MARKET_PROVIDER",
        "FILINGS_PROVIDER",
        "MACRO_PROVIDER",
        "PRICE_CROSSCHECK_PROVIDER",
    ],
)
def test_selectors_are_trimmed_and_lowercased(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, " YFinance ")
    assert getattr(build(), name) == "yfinance"


def test_news_providers_parse_comma_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWS_PROVIDERS", "yfinance, fixture")
    assert build().NEWS_PROVIDERS == ["yfinance", "fixture"]
    monkeypatch.setenv("NEWS_PROVIDERS", "yfinance, yfinance,")
    assert build().NEWS_PROVIDERS == ["yfinance"]
    monkeypatch.setenv("NEWS_PROVIDERS", " ")
    with pytest.raises(ValidationError, match="NEWS_PROVIDERS"):
        build()


def test_provider_timeout_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValidationError, match="PROVIDER_TIMEOUT_SECONDS"):
        build()


def test_provider_secrets_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-test-123"
    agent = "Vantage research owner@example.com"
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", secret)
    monkeypatch.setenv("SEC_USER_AGENT", agent)
    s = build()
    text = repr(s)
    assert secret not in text and agent not in text
    pairs = dict(s.__repr_args__())
    assert pairs["ALPACA_API_SECRET_KEY"] == "***redacted***"
    assert pairs["SEC_USER_AGENT"] == "***redacted***"
    assert secret not in str(list(pairs.values()))
    assert agent not in str(list(pairs.values()))
