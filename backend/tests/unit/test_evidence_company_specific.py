from datetime import UTC, datetime, timedelta

from app.domain.research import (
    ComponentQuality,
    EvidenceDetails,
    FilingsSnapshot,
    NewsItem,
    NewsSnapshot,
    SourceType,
)
from app.services.evidence import (
    EVIDENCE_FILING_LIMIT,
    EVIDENCE_INSIDER_LIMIT,
    assemble_evidence,
    company_search_name,
    is_company_specific,
)

NOW = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)


def _item(
    evidence_id: str,
    title: str = "Headline",
    *,
    source_type: SourceType = "news",
    tagged: list[str] | None = None,
    summary: str | None = None,
    event_time: datetime | None = None,
    parse_state: str | None = None,
    with_details: bool = True,
) -> NewsItem:
    details = None
    if with_details:
        details = EvidenceDetails(
            tagged_symbols=tagged or [],
            parse_state=parse_state,  # type: ignore[arg-type]
        )
    return NewsItem(
        evidence_id=evidence_id,
        provider="p",
        title=title,
        summary=summary,
        event_time=event_time,
        retrieved_at=NOW,
        source_type=source_type,
        details=details,
    )


def _news(items: list[NewsItem]) -> NewsSnapshot:
    return NewsSnapshot(
        symbol="AAPL",
        items=items,
        provider="p",
        retrieved_at=NOW,
        quality=ComponentQuality.FRESH,
    )


def _filings(
    items: list[NewsItem],
    *,
    company_name: str | None = "Apple Inc.",
    quality: ComponentQuality = ComponentQuality.FRESH,
) -> FilingsSnapshot:
    return FilingsSnapshot(
        symbol="AAPL",
        items=items,
        provider="sec",
        retrieved_at=NOW,
        quality=quality,
        company_name=company_name,
    )


def test_company_search_name_strips_legal_suffixes() -> None:
    assert company_search_name("Apple Inc.") == "Apple"
    assert company_search_name("JPMORGAN CHASE & CO") == "JPMORGAN CHASE"
    assert company_search_name("Meta Platforms, Inc.") == "Meta Platforms"
    assert company_search_name("WALMART INC. /DE/") == "WALMART"
    assert company_search_name("Foo Holdings Co., Ltd.") == "Foo Holdings"
    assert company_search_name("Berkshire Hathaway Inc /NY") == "Berkshire Hathaway"
    assert company_search_name("AT&T INC.") == "AT&T"
    assert company_search_name("Acme Group") == "Acme Group"


def test_company_search_name_too_short_or_missing() -> None:
    assert company_search_name("AG") is None
    assert company_search_name(None) is None


def test_news_tagged_and_named_is_company_specific() -> None:
    item = _item("a", "Apple reports results", tagged=["AAPL"])
    assert is_company_specific(item, symbol="AAPL", company_name="Apple Inc.")


def test_news_with_more_than_three_tags_is_not() -> None:
    item = _item("a", "Apple reports results", tagged=["AAPL", "A", "B", "C"])
    assert not is_company_specific(item, symbol="AAPL", company_name="Apple Inc.")


def test_news_without_name_or_ticker_in_text_is_not() -> None:
    item = _item("a", "Chipmakers rally", tagged=["AAPL"])
    assert not is_company_specific(item, symbol="AAPL", company_name="Apple Inc.")


def test_news_without_details_is_not() -> None:
    item = _item("a", "Apple reports results", with_details=False)
    assert not is_company_specific(item, symbol="AAPL", company_name="Apple Inc.")


def test_news_not_tagged_with_symbol_is_not() -> None:
    item = _item("a", "Apple reports results", tagged=["MSFT"])
    assert not is_company_specific(item, symbol="AAPL", company_name="Apple Inc.")


def test_ticker_match_is_case_sensitive_whole_word() -> None:
    def check(title: str) -> bool:
        item = _item("a", title, tagged=["AAPL"])
        return is_company_specific(item, symbol="AAPL", company_name=None)

    assert check("AAPL shares rise")
    assert check("$AAPL moves")
    assert check("Stock (AAPL) rises")
    assert check("NASDAQ:AAPL up")
    assert not check("aapl shares rise")
    assert not check("AAPLX fund")
    assert not check("XAAPL fund")


def test_summary_can_carry_the_match() -> None:
    item = _item("a", "Quarterly update", tagged=["AAPL"], summary="apple inc news")
    assert is_company_specific(item, symbol="AAPL", company_name="Apple Inc.")


def test_one_character_ticker_matches_only_by_name() -> None:
    plain = _item("a", "The market rallied", tagged=["T"])
    assert not is_company_specific(plain, symbol="T", company_name=None)
    assert not is_company_specific(plain, symbol="T", company_name="AT&T INC.")
    named = _item("b", "AT&T raises outlook", tagged=["T"])
    assert is_company_specific(named, symbol="T", company_name="AT&T INC.")
    letter = _item("c", "T shares rise", tagged=["T"])
    assert not is_company_specific(letter, symbol="T", company_name=None)


def test_share_class_symbol_matches_dash_and_dot() -> None:
    dash = _item("a", "BRK-B shares", tagged=["BRK.B"])
    assert is_company_specific(dash, symbol="BRK.B", company_name=None)
    tag_dash = _item("b", "BRK.B shares", tagged=["BRK-B"])
    assert is_company_specific(tag_dash, symbol="BRK.B", company_name=None)


def test_tags_compare_upper_cased() -> None:
    item = _item("a", "Apple reports", tagged=["aapl"])
    assert is_company_specific(item, symbol="aapl", company_name="Apple Inc.")


def test_filing_and_insider_are_company_specific_without_text() -> None:
    for kind in ("filing", "insider_transaction"):
        item = _item("a", "Form 4", source_type=kind, with_details=False)  # type: ignore[arg-type]
        assert is_company_specific(item, symbol="AAPL", company_name=None)


def test_assemble_caps_filings_at_ten() -> None:
    filings = [
        _item(
            f"f{i:02d}",
            "8-K",
            source_type="filing",
            event_time=NOW - timedelta(days=i),
        )
        for i in range(12)
    ]
    out = assemble_evidence(_news([]), _filings(filings), symbol="AAPL")
    assert len(out) == EVIDENCE_FILING_LIMIT == 10
    assert {i.evidence_id for i in out} == {f"f{i:02d}" for i in range(10)}


def test_assemble_caps_insiders_and_drops_not_fetched() -> None:
    insiders = [
        _item(
            f"i{i:02d}",
            "Form 4",
            source_type="insider_transaction",
            event_time=NOW - timedelta(days=i),
            parse_state="parsed",
        )
        for i in range(12)
    ]
    insiders.append(
        _item(
            "skipped",
            "Form 4",
            source_type="insider_transaction",
            event_time=NOW + timedelta(days=1),
            parse_state="not_fetched",
        )
    )
    out = assemble_evidence(_news([]), _filings(insiders), symbol="AAPL")
    ids = {i.evidence_id for i in out}
    assert EVIDENCE_INSIDER_LIMIT == 10
    assert len(out) == 10
    assert "skipped" not in ids


def test_assemble_orders_by_time_desc_none_last_then_id() -> None:
    news = [
        _item("n1", "Apple up", tagged=["AAPL"], event_time=NOW - timedelta(days=1)),
        _item("n0", "Apple flat", tagged=["AAPL"], event_time=None),
    ]
    filings = [
        _item("f1", "10-K", source_type="filing", event_time=NOW),
        _item("a0", "8-K", source_type="filing", event_time=None),
        _item("f2", "8-K", source_type="filing", event_time=NOW - timedelta(days=1)),
    ]
    out = assemble_evidence(_news(news), _filings(filings), symbol="AAPL")
    assert [i.evidence_id for i in out] == ["f1", "f2", "n1", "a0", "n0"]


def test_assemble_sets_company_specific_and_does_not_mutate() -> None:
    news = [
        _item("n1", "Apple up", tagged=["AAPL"]),
        _item("n2", "Markets", tagged=["AAPL"]),
        _item("n3", "Apple up", with_details=False),
    ]
    filings = [_item("f1", "10-K", source_type="filing", with_details=False)]
    snap, fsnap = _news(news), _filings(filings)
    before = (snap.model_dump(), fsnap.model_dump())
    out = {i.evidence_id: i for i in assemble_evidence(snap, fsnap, symbol="AAPL")}
    assert out["n1"].details is not None
    assert out["n1"].details.company_specific is True
    assert out["n1"].details.tagged_symbols == ["AAPL"]
    assert out["n2"].details is not None
    assert out["n2"].details.company_specific is False
    assert out["n3"].details == EvidenceDetails(company_specific=False)
    assert out["f1"].details == EvidenceDetails(company_specific=True)
    assert (snap.model_dump(), fsnap.model_dump()) == before


def test_assemble_without_usable_filings_returns_news_only() -> None:
    news = [_item("n1", "Apple up", tagged=["AAPL"])]
    filing = _item("f1", "10-K", source_type="filing")
    for filings in (
        None,
        _filings([filing], quality=ComponentQuality.FAILED),
        _filings([filing], quality=ComponentQuality.MISSING),
    ):
        out = assemble_evidence(_news(news), filings, symbol="AAPL")
        assert [i.evidence_id for i in out] == ["n1"]
        assert out[0].details is not None
        assert out[0].details.company_specific is False  # no name configured


def test_assemble_with_no_company_name_matches_ticker_only() -> None:
    news = [_item("n1", "Apple up", tagged=["AAPL"])]
    out = assemble_evidence(_news(news), _filings([], company_name=None), symbol="AAPL")
    assert out[0].details is not None
    assert out[0].details.company_specific is False
