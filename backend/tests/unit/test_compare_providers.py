from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import (
    ComponentQuality,
    CrossCheckClose,
    DailyBar,
    MarketSnapshot,
    PriceCrossCheckSnapshot,
)
from scripts.compare_providers import (
    PARITY_TICKERS,
    _compare_ticker,
    render_report,
    TickerResult,
    close_deviations,
    crosscheck_deviations,
    dollar_volume_gap,
    evaluate,
    main,
    return_gap_pp,
)

START = date(2026, 1, 5)


def bar(
    offset: int, adjusted: float, close: float = 100.0, volume: int = 1000
) -> DailyBar:
    return DailyBar(
        symbol="AAPL",
        session_date=START + timedelta(days=offset),
        open=close,
        high=close,
        low=close,
        close=close,
        adjusted_close=adjusted,
        volume=volume,
        currency="USD",
        provider="test",
        retrieved_at=datetime(2026, 1, 30, tzinfo=UTC),
        adjustment_state="split_and_dividend_adjusted",
    )


def bars(values: list[float]) -> list[DailyBar]:
    return [bar(i, v) for i, v in enumerate(values)]


def result(
    symbol: str = "AAPL",
    deviations: list[float] | None = None,
    gap: float | None = 0.1,
    dollar: float | None = 0.01,
    error: str | None = None,
) -> TickerResult:
    return TickerResult(
        symbol=symbol,
        deviations=[0.1] * 10 if deviations is None else deviations,
        return_gap_pp=gap,
        dollar_volume_gap=dollar,
        crosscheck_deviations=None,
        error=error,
    )


def test_tickers_are_the_25_named() -> None:
    assert len(PARITY_TICKERS) == 25
    assert len(set(PARITY_TICKERS)) == 25
    assert "BRK.B" in PARITY_TICKERS


def test_close_deviation_within_and_outside() -> None:
    devs = close_deviations(bars([100.4, 100.0]), bars([100.0, 100.6]))
    assert devs[0] == pytest.approx(0.4)
    assert devs[1] == pytest.approx(100 * 0.6 / 100.6)
    assert devs[0] <= 0.5
    assert devs[1] > 0.5


def test_close_deviation_ignores_mismatched_dates() -> None:
    a = bars([100.0, 101.0, 102.0])
    b = [bar(1, 101.0), bar(5, 50.0)]
    assert close_deviations(a, b) == [0.0]


def test_crosscheck_deviations_match_on_session_date() -> None:
    closes = [
        CrossCheckClose(session_date=START, adjusted_close=100.0),
        CrossCheckClose(session_date=START + timedelta(days=9), adjusted_close=1.0),
    ]
    devs = crosscheck_deviations(bars([100.5, 100.0]), closes)
    assert devs == [pytest.approx(0.5)]


def test_return_gap_pp() -> None:
    a = bars([100.0, 105.0, 110.0])
    b = bars([100.0, 100.0, 109.0])
    assert return_gap_pp(a, b) == pytest.approx(1.0)


def test_return_gap_needs_two_common_dates() -> None:
    with pytest.raises(ValueError):
        return_gap_pp(bars([100.0]), bars([100.0]))


def test_dollar_volume_gap() -> None:
    a = [bar(0, 100.0, close=10.0, volume=1000), bar(1, 100.0, close=10.0, volume=1000)]
    b = [bar(0, 100.0, close=10.0, volume=900), bar(1, 100.0, close=10.0, volume=900)]
    assert dollar_volume_gap(a, b) == pytest.approx(1000 / 9000)


def test_dollar_volume_gap_errors() -> None:
    with pytest.raises(ValueError):
        dollar_volume_gap(bars([1.0]), [bar(9, 1.0)])
    with pytest.raises(ValueError):
        dollar_volume_gap([bar(0, 1.0)], [bar(0, 1.0, volume=0)])


def test_evaluate_passes_inside_bounds() -> None:
    verdict = evaluate([result(), result("MSFT")])
    assert verdict.passed
    assert verdict.failed_tickers == []


def test_evaluate_bounds_are_inclusive() -> None:
    verdict = evaluate([result(deviations=[0.5] * 10, gap=0.5, dollar=0.10)])
    assert verdict.passed


def test_evaluate_fails_pooled_share_below_99_percent() -> None:
    ok = result(deviations=[0.1] * 99)
    bad = result("MSFT", deviations=[0.6] * 2)
    verdict = evaluate([ok, bad])
    assert not verdict.passed
    assert verdict.within_share < 0.99
    ok_one_bad = evaluate([result(deviations=[0.1] * 99 + [0.6])])
    assert ok_one_bad.passed


def test_evaluate_fails_return_gap() -> None:
    verdict = evaluate([result(gap=0.51)])
    assert not verdict.passed
    assert verdict.failed_tickers[0][0] == "AAPL"
    assert "return" in verdict.failed_tickers[0][1]


def test_evaluate_fails_dollar_volume_gap() -> None:
    verdict = evaluate([result(dollar=0.11)])
    assert not verdict.passed
    assert "dollar" in verdict.failed_tickers[0][1]


def test_evaluate_fetch_failure_is_listed_and_fails() -> None:
    failed = TickerResult("AAPL", [], None, None, None, "The provider is unavailable.")
    verdict = evaluate([result("MSFT"), failed])
    assert not verdict.passed
    assert verdict.failed_tickers == [("AAPL", "fetch failed")]


def test_main_exits_2_without_alpaca_keys(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(_env_file=None, ALPACA_API_KEY_ID="", ALPACA_API_SECRET_KEY="")
    assert main([], settings=settings) == 2
    assert "Alpaca keys are not set" in capsys.readouterr().err


NOW = datetime(2026, 1, 30, tzinfo=UTC)


class StubMarket:
    def __init__(
        self,
        values: list[float],
        *,
        quality: ComponentQuality = ComponentQuality.FRESH,
        error_code: str | None = None,
    ) -> None:
        self.values = values
        self.quality = quality
        self.error_code = error_code
        self.symbols: list[str] = []

    def fetch_daily_snapshot(
        self, symbol: str, start: date, end: date, retrieved_at: datetime, **_: object
    ) -> MarketSnapshot:
        self.symbols.append(symbol)
        return MarketSnapshot(
            symbol="AAPL",
            bars=bars(self.values),
            provider="stub",
            retrieved_at=NOW,
            as_of=NOW,
            latest_completed_session=START,
            content_hash="a" * 64,
            quality=self.quality,
            error_code=self.error_code,
        )


class StubCross:
    def __init__(
        self,
        *,
        raises: bool = False,
        quality: ComponentQuality = ComponentQuality.FRESH,
        error_code: str | None = None,
    ) -> None:
        self.raises = raises
        self.quality = quality
        self.error_code = error_code

    def fetch_adjusted_closes(
        self, symbol: str, start: date, end: date, retrieved_at: datetime
    ) -> PriceCrossCheckSnapshot:
        if self.raises:
            raise VantageError(code="X", safe_message="Tiingo is unavailable.")
        return PriceCrossCheckSnapshot(
            symbol="AAPL",
            provider="tiingo",
            retrieved_at=NOW,
            quality=self.quality,
            error_code=self.error_code,
            closes=[CrossCheckClose(session_date=START, adjusted_close=100.0)],
        )


def _compare(ref, cand, cross, symbol: str = "AAPL") -> TickerResult:
    return _compare_ticker(symbol, ref, cand, cross, START, START, NOW)


def test_share_class_symbol_uses_a_dash_for_yfinance_only() -> None:
    ref, cand = StubMarket([100.0, 101.0]), StubMarket([100.0, 101.0])
    out = _compare(ref, cand, None, symbol="BRK.B")
    assert ref.symbols == ["BRK-B"]
    assert cand.symbols == ["BRK.B"]
    assert out.symbol == "BRK.B"
    verdict = evaluate([out])
    assert "BRK.B" in render_report([out], verdict, START, START, False)


@pytest.mark.parametrize(
    "cross",
    [
        StubCross(raises=True),
        StubCross(quality=ComponentQuality.MISSING),
        StubCross(quality=ComponentQuality.FAILED, error_code="TIINGO_FAILED"),
    ],
)
def test_tiingo_trouble_keeps_the_main_comparison(cross: StubCross) -> None:
    out = _compare(StubMarket([100.0, 101.0]), StubMarket([100.0, 101.0]), cross)
    assert out.error is None
    assert out.return_gap_pp == pytest.approx(0.0)
    assert out.crosscheck_deviations is None
    assert out.note is not None and "cross-check unavailable" in out.note
    assert evaluate([out]).failed_tickers == []
    report = render_report([out], evaluate([out]), START, START, True)
    assert "cross-check unavailable" in report


def test_non_fresh_provider_state_is_named_in_the_note() -> None:
    ref = StubMarket([100.0, 101.0])
    cand = StubMarket(
        [100.0], quality=ComponentQuality.PARTIAL, error_code="ALPACA_PARTIAL"
    )
    out = _compare(ref, cand, None)
    assert out.error is not None
    assert "Alpaca" in out.error and "partial" in out.error
    assert "ALPACA_PARTIAL" in out.error
    assert "Too few" not in out.error


def test_too_few_sessions_message_stays_when_both_are_fresh() -> None:
    out = _compare(StubMarket([100.0]), StubMarket([100.0]), None)
    assert out.error == "Too few matching sessions to compare."
