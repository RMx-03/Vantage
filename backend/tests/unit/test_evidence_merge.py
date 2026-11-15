from datetime import UTC, datetime, timedelta

from app.domain.research import (
    ComponentQuality,
    EvidenceDetails,
    NewsItem,
    NewsSnapshot,
)
from app.services.evidence import canonical_url, merge_news, normalize_title

T0 = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _item(
    provider: str,
    title: str,
    *,
    evidence_id: str | None = None,
    url: str | None = None,
    event_time: datetime | None = T0,
    tagged: list[str] | None = None,
) -> NewsItem:
    return NewsItem(
        evidence_id=evidence_id or f"{provider}-{title}",
        provider=provider,
        title=title,
        url=url,
        event_time=event_time,
        retrieved_at=T0,
        details=EvidenceDetails(providers=[provider], tagged_symbols=tagged or []),
    )


def _snap(
    provider: str,
    items: list[NewsItem],
    *,
    quality: ComponentQuality | None = None,
    error_code: str | None = None,
    retrieved_at: datetime = T0,
    coverage_start: datetime | None = None,
    coverage_end: datetime | None = None,
) -> NewsSnapshot:
    return NewsSnapshot(
        symbol="AAPL",
        items=items,
        provider=provider,
        retrieved_at=retrieved_at,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        quality=quality
        or (ComponentQuality.FRESH if items else ComponentQuality.MISSING),
        error_code=error_code,
    )


def _failed(provider: str) -> NewsSnapshot:
    return _snap(
        provider,
        [],
        quality=ComponentQuality.FAILED,
        error_code="NEWS_PROVIDER_FAILED",
    )


def test_canonical_url_rules() -> None:
    assert (
        canonical_url("HTTPS://WWW.Example.com/a/b/?utm_source=x&b=2&a=1#frag")
        == "https://example.com/a/b?a=1&b=2"
    )
    assert canonical_url("https://example.com/") == "https://example.com"
    assert canonical_url(None) is None
    assert canonical_url("javascript:alert(1)") is None


def test_normalize_title() -> None:
    assert normalize_title("  Apple's  Q4: Beat!! ") == "apple s q4 beat"


def test_one_snapshot_is_returned_unchanged() -> None:
    snap = _snap("yfinance", [_item("yfinance", "A")])
    assert merge_news([snap], symbol="AAPL", limit=10) is snap


def test_same_canonical_url_merges_and_unions_providers() -> None:
    a = _snap(
        "alpaca",
        [_item("alpaca", "One", url="https://www.x.com/s/", tagged=["AAPL"])],
    )
    f = _snap(
        "finnhub",
        [
            _item(
                "finnhub", "Other", url="https://x.com/s?utm_source=z", tagged=["MSFT"]
            )
        ],
    )
    merged = merge_news([a, f], symbol="AAPL", limit=10)
    assert len(merged.items) == 1
    kept = merged.items[0]
    assert kept.provider == "alpaca"
    assert kept.details is not None
    assert kept.details.providers == ["alpaca", "finnhub"]
    assert kept.details.tagged_symbols == ["AAPL"]
    # inputs are not mutated
    assert a.items[0].details is not None
    assert a.items[0].details.providers == ["alpaca"]


def test_same_title_three_hours_apart_merges_keeping_earlier() -> None:
    early = T0 - timedelta(hours=3)
    a = _snap("alpaca", [_item("alpaca", "Big News!", event_time=T0)])
    f = _snap("finnhub", [_item("finnhub", "big news", event_time=early)])
    merged = merge_news([a, f], symbol="AAPL", limit=10)
    assert len(merged.items) == 1
    assert merged.items[0].event_time == early
    assert merged.items[0].provider == "finnhub"
    assert merged.items[0].details is not None
    assert merged.items[0].details.providers == ["finnhub", "alpaca"]


def test_same_title_thirty_hours_apart_does_not_merge() -> None:
    a = _snap("alpaca", [_item("alpaca", "Same", event_time=T0)])
    f = _snap(
        "finnhub", [_item("finnhub", "Same", event_time=T0 - timedelta(hours=30))]
    )
    assert len(merge_news([a, f], symbol="AAPL", limit=10).items) == 2


def test_same_title_without_event_time_does_not_merge() -> None:
    a = _snap("alpaca", [_item("alpaca", "Same", event_time=None)])
    f = _snap("finnhub", [_item("finnhub", "Same", event_time=None)])
    assert len(merge_news([a, f], symbol="AAPL", limit=10).items) == 2


def test_tie_goes_to_earlier_snapshot() -> None:
    a = _snap("alpaca", [_item("alpaca", "T", url="https://x.com/s")])
    f = _snap("finnhub", [_item("finnhub", "T", url="https://x.com/s")])
    merged = merge_news([f, a], symbol="AAPL", limit=10)
    assert merged.items[0].provider == "finnhub"
    assert merged.items[0].details is not None
    assert merged.items[0].details.providers == ["finnhub", "alpaca"]


def test_dedup_does_not_depend_on_pairwise_order() -> None:
    # A and C share a URL; B shares a title with C only. All one story each
    # way round, with the earliest item kept.
    a = _item("alpaca", "Alpha", url="https://x.com/s", event_time=T0)
    b = _item("finnhub", "Gamma", event_time=T0 + timedelta(hours=1))
    c = _item(
        "yfinance",
        "Gamma",
        url="https://x.com/s?utm_medium=m",
        event_time=T0 + timedelta(hours=2),
    )
    merged = merge_news(
        [_snap("alpaca", [a]), _snap("finnhub", [b]), _snap("yfinance", [c])],
        symbol="AAPL",
        limit=10,
    )
    assert [i.provider for i in merged.items] == ["finnhub", "alpaca"]
    assert merged.items[1].details is not None
    assert merged.items[1].details.providers == ["alpaca", "yfinance"]
    assert merged.items[0].details is not None
    assert merged.items[0].details.providers == ["finnhub"]


def test_ordering_and_limit() -> None:
    items = [
        _item("a", "n", evidence_id="z", event_time=None),
        _item("a", "o", evidence_id="b", event_time=T0),
        _item("a", "p", evidence_id="a", event_time=T0),
        _item("a", "q", evidence_id="c", event_time=T0 + timedelta(hours=1)),
    ]
    merged = merge_news([_snap("a", items), _snap("b", [])], symbol="AAPL", limit=3)
    assert [i.evidence_id for i in merged.items] == ["c", "a", "b"]


def test_header_fields_and_coverage() -> None:
    a = _snap(
        "alpaca",
        [_item("alpaca", "A")],
        retrieved_at=T0,
        coverage_start=T0 - timedelta(days=7),
        coverage_end=T0,
    )
    f = _snap(
        "finnhub",
        [_item("finnhub", "B", event_time=T0 - timedelta(days=1))],
        retrieved_at=T0 + timedelta(seconds=5),
        coverage_start=T0 - timedelta(days=5),
        coverage_end=T0 + timedelta(hours=1),
    )
    merged = merge_news([a, f], symbol="AAPL", limit=10)
    assert merged.provider == "alpaca,finnhub"
    assert merged.symbol == "AAPL"
    assert merged.retrieved_at == T0 + timedelta(seconds=5)
    assert merged.coverage_start == T0 - timedelta(days=7)
    assert merged.coverage_end == T0 + timedelta(hours=1)


def test_coverage_ignores_none_values() -> None:
    a = _snap("alpaca", [_item("alpaca", "A")])
    f = _snap("finnhub", [], coverage_start=T0, coverage_end=T0)
    merged = merge_news([a, f], symbol="AAPL", limit=10)
    assert merged.coverage_start == T0
    assert merged.coverage_end == T0


def test_all_failed_is_failed() -> None:
    merged = merge_news(
        [_failed("alpaca"), _failed("finnhub")], symbol="AAPL", limit=10
    )
    assert merged.quality == ComponentQuality.FAILED
    assert merged.error_code == "NEWS_PROVIDER_FAILED"
    assert merged.items == []
    assert merged.provider == "alpaca,finnhub"


def test_some_failed_is_partial_without_error_code() -> None:
    # An error code would make quality.py read the whole news role as failed.
    ok = _snap("finnhub", [_item("finnhub", "A")])
    merged = merge_news([_failed("alpaca"), ok], symbol="AAPL", limit=10)
    assert merged.quality == ComponentQuality.PARTIAL
    assert merged.error_code is None
    assert merged.provider == "alpaca,finnhub"
    assert len(merged.items) == 1


def test_any_partial_success_is_partial() -> None:
    a = _snap("alpaca", [_item("alpaca", "A")], quality=ComponentQuality.PARTIAL)
    f = _snap("finnhub", [_item("finnhub", "B")])
    merged = merge_news([a, f], symbol="AAPL", limit=10)
    assert merged.quality == ComponentQuality.PARTIAL
    assert merged.error_code is None


def test_all_missing_is_missing() -> None:
    merged = merge_news(
        [_snap("alpaca", []), _snap("finnhub", [])], symbol="AAPL", limit=10
    )
    assert merged.quality == ComponentQuality.MISSING
    assert merged.error_code is None


def test_fresh_otherwise() -> None:
    a = _snap("alpaca", [_item("alpaca", "A")])
    f = _snap("finnhub", [])
    merged = merge_news([a, f], symbol="AAPL", limit=10)
    assert merged.quality == ComponentQuality.FRESH


def test_non_latin_titles_without_urls_do_not_merge() -> None:
    a = _item("alpaca", "苹果发布新产品", url=None, event_time=T0)
    f = _item(
        "finnhub", "特斯拉交付量上升", url=None, event_time=T0 + timedelta(hours=1)
    )
    merged = merge_news(
        [_snap("alpaca", [a]), _snap("finnhub", [f])], symbol="AAPL", limit=10
    )
    assert len(merged.items) == 2
