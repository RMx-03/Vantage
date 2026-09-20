from datetime import UTC, datetime
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
import pytest
import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    MarketSnapshot,
    ModelQuality,
    NewsItem,
    NewsSnapshot,
    ResearchMetric,
)
from app.agents.research_graph import create_research_graph
from app.prompts.research_interpretation import SYSTEM_INSTRUCTION
from app.providers.llm import (
    PROVIDER_ABSTENTION_REASONS,
    GeminiInterpretationProvider,
    GroqInterpretationProvider,
    OllamaInterpretationProvider,
    build_interpretation_provider,
    validate_interpretation,
)


def test_interpretation_rejects_model_authored_numeric_claims() -> None:
    payload = {
        "sentiment_label": "positive",
        "sentiment_score": 0.2,
        "summary": "The company will gain 25 percent next year.",
        "evidence_ids": [],
        "warnings": [],
    }
    with pytest.raises(VantageError) as exc_info:
        validate_interpretation(payload, set())
    assert exc_info.value.code == "MODEL_OUTPUT_INVALID"


def valid_interpretation_json() -> dict[str, Any]:
    return {
        "sentiment_label": "mixed",
        "sentiment_score": 0.15,
        "summary": "Recent revenue growth is offset by elevated market volatility.",
        "evidence_ids": ["news-1"],
        "warnings": [],
        "abstained": False,
        "abstention_reason": None,
    }


def abstained_interpretation_json() -> dict[str, Any]:
    return {
        **valid_interpretation_json(),
        "sentiment_label": "unavailable",
        "sentiment_score": None,
        "evidence_ids": [],
        "abstained": True,
        "abstention_reason": "MODEL_UNAVAILABLE",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"sentiment_label": "positive"},
        {"sentiment_score": 0.0},
        {"evidence_ids": ["news-1"]},
        {"abstention_reason": None},
        {"abstention_reason": ""},
        {"abstention_reason": "INSUFFICIENT_EVIDENCE"},
        {"abstention_reason": "Confidence is 80 percent."},
    ],
)
def test_abstention_requires_consistent_unavailable_state(overrides) -> None:
    with pytest.raises(VantageError) as caught:
        validate_interpretation(
            {**abstained_interpretation_json(), **overrides}, {"news-1"}
        )
    assert caught.value.code == "MODEL_OUTPUT_INVALID"


@pytest.mark.parametrize(
    "overrides",
    [
        {"sentiment_label": "unavailable"},
        {"evidence_ids": []},
        {"abstention_reason": "MODEL_UNAVAILABLE"},
        {"abstention_reason": ""},
    ],
)
def test_non_abstention_requires_evidence_and_no_reason(overrides) -> None:
    with pytest.raises(VantageError) as caught:
        validate_interpretation(
            {**valid_interpretation_json(), **overrides}, {"news-1"}
        )
    assert caught.value.code == "MODEL_OUTPUT_INVALID"


UNSAFE_AUTHORED_TEXT = [
    "Revenue grew 25 percent.",
    "Confidence is eighty percent.",
    "Buy this stock.",
    "SELL the shares now.",
    "Hold this security.",
    "Consider buying this security.",
    "Investors should sell their shares.",
    "We recommend holding the stock.",
    "This stock is a strong buy.",
    "The shares have a hold rating.",
    "Invest in this company.",
    "Add this stock to your portfolio.",
    "This investment is suitable for retirees.",
    "This stock fits your risk tolerance.",
    "The stock is ideal for conservative investors.",
    "The target price is above the current market price.",
    "Our price target remains unchanged.",
    "These returns are guaranteed.",
    "This is a risk-free investment.",
    "The stock will rise soon.",
    "The share price will certainly fall next quarter.",
    "The stock is certain to outperform.",
    "The price is going to increase.",
    "Buy now.",
    "Sell immediately.",
    "Hold.",
    "We recommend this stock.",
    "Purchase this security.",
    "Avoid this stock.",
    "This stock is a good fit for you.",
    "This is a suitable investment for your retirement.",
    "The stock will go up.",
    "You will make money.",
    "The shares cannot lose value.",
    "Positive returns are certain.",
    "Buy AAPL.",
    "Sell it now.",
    "Hold onto these shares.",
    "  Buy now.",
    "This is a risk\u2011free investment.",
    "The shares can\u2019t lose value.",
    "Recommendation: **BUY**",
    "Recommendation: __SELL__",
    "Revenue grew \u00bd percent.",
    "Revenue grew \u216b percent.",
    "Revenue increased by half.",
    "Costs decreased by a quarter.",
    "Revenue gained by half.",
    "Backlog plunged by half.",
    "Headcount jumped by a quarter.",
    "Revenue was half of the previous total.",
    "Half of revenue came from services.",
    "One third of revenue came from services.",
]


@pytest.mark.parametrize("text", UNSAFE_AUTHORED_TEXT)
@pytest.mark.parametrize("field", ["summary", "warnings", "abstention_reason"])
def test_unsafe_text_is_rejected_in_every_authored_field(field, text) -> None:
    payload = (
        abstained_interpretation_json()
        if field == "abstention_reason"
        else valid_interpretation_json()
    )
    payload[field] = (
        ["Historical evidence is limited.", text] if field == "warnings" else text
    )
    with pytest.raises(VantageError) as caught:
        validate_interpretation(payload, {"news-1"})
    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    # A contradictory reason alone also fails the state invariant. Require the
    # text scanner's diagnosis so omitting reason scanning cannot pass this test.
    assert caught.value.safe_message in {
        "AI interpretation contained unsupported numeric claims.",
        "AI interpretation contained unsupported advisory or predictive language.",
    }


@pytest.mark.parametrize(
    "text",
    [
        "Shareholder concerns were discussed at half-time.",
        "The statement was half-hearted and the outlook remains uncertain.",
        "Management was criticized for a pattern of half-hearted responses.",
        "The company reported mixed quarter results.",
        "End of quarter results were mixed.",
        "The report relied on statements of third parties.",
        "The report was prepared by a third party.",
        "Buy orders were processed through the exchange.",
        "Sell orders reflected historical activity.",
        "The report describes buy-side and sell-side activity.",
        "The company put its expansion plans on hold.",
        "The company\u2019s **historical** outlook remains uncertain\u2014coverage is limited.",
    ],
)
def test_safety_normalization_preserves_accepted_original_text(text) -> None:
    result = validate_interpretation(
        {**valid_interpretation_json(), "summary": text, "warnings": [text]},
        {"news-1"},
    )
    assert result.summary == text
    assert result.warnings == [text]


@pytest.mark.parametrize("reason", ["MODEL_UNAVAILABLE", "MODEL_OUTPUT_INVALID"])
def test_stable_abstention_reasons_are_accepted_without_evidence(reason) -> None:
    result = validate_interpretation(
        {**abstained_interpretation_json(), "abstention_reason": reason}, set()
    )
    assert result.abstained is True
    assert result.abstention_reason == reason
    assert result.sentiment_label == "unavailable"
    assert result.sentiment_score is None
    assert result.evidence_ids == []


def test_model_not_run_is_rejected_from_a_provider() -> None:
    """A model that ran cannot claim the reserved never-invoked sentinel."""
    with pytest.raises(VantageError) as caught:
        validate_interpretation(
            {**abstained_interpretation_json(), "abstention_reason": "MODEL_NOT_RUN"},
            set(),
        )
    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert "MODEL_NOT_RUN" not in PROVIDER_ABSTENTION_REASONS
    assert "MODEL_NOT_RUN" not in SYSTEM_INSTRUCTION


def test_internal_not_run_placeholder_bypasses_the_provider_validator() -> None:
    """The code-generated sentinel keeps working; it never crosses the validator."""
    provider = MagicMock()
    provider.enabled = True
    now = datetime(2026, 9, 14, 21, 0, tzinfo=UTC)
    market = MarketSnapshot(
        symbol="AAPL",
        bars=[],
        provider="mock_market",
        retrieved_at=now,
        as_of=now,
        latest_completed_session=now.date(),
        content_hash="a" * 64,
        quality=ComponentQuality.FRESH,
    )
    news = NewsSnapshot(
        symbol="AAPL",
        items=[],
        provider="mock_news",
        retrieved_at=now,
        quality=ComponentQuality.MISSING,
    )
    state = create_research_graph(provider).invoke(
        {"symbol": "AAPL", "market": market, "news": news}
    )
    provider.interpret.assert_not_called()
    assert state["interpretation"].abstention_reason == "MODEL_NOT_RUN"
    assert state["policy"].data_quality.model is ModelQuality.NOT_RUN


@pytest.mark.parametrize(
    "text",
    [
        "Shareholder concerns reflected a household spending slowdown.",
        "The company sells software through resellers.",
        "The company put its expansion plans on hold.",
        "Buyback activity and seller demand were discussed in the report.",
        "Management discussed goodwill and withholding obligations.",
        "Reported earnings were mixed and future performance remains uncertain.",
        "The company sells shares through its employee benefit program.",
        "The report recommends monitoring the quality of historical evidence.",
    ],
)
@pytest.mark.parametrize("score", [None, -1.0, 0.0, 1.0])
def test_cited_historical_text_avoids_substring_false_positives(text, score) -> None:
    result = validate_interpretation(
        {
            **valid_interpretation_json(),
            "summary": text,
            "warnings": [text],
            "sentiment_score": score,
        },
        {"news-1"},
    )
    assert result.summary == text
    assert result.sentiment_score == score
    assert result.evidence_ids == ["news-1"]


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 9, 14, 21, 0, tzinfo=UTC)


@pytest.fixture
def metrics(fixed_now: datetime) -> list[ResearchMetric]:
    return [
        ResearchMetric(
            key="return_1_session",
            label="1-session return",
            value=0.015,
            unit="ratio",
            window_sessions=1,
            as_of=fixed_now,
            calculation_version="eod-metrics-v1",
            quality=ComponentQuality.FRESH,
        )
    ]


@pytest.fixture
def news(fixed_now: datetime) -> NewsSnapshot:
    return NewsSnapshot(
        symbol="AAPL",
        items=[
            NewsItem(
                evidence_id="news-1",
                provider="fixture",
                publisher="Reuters",
                title="Apple reports quarterly results",
                url="https://example.com/news-1",
                event_time=fixed_now,
                retrieved_at=fixed_now,
                content_hash="a" * 64,
            )
        ],
        provider="fixture",
        retrieved_at=fixed_now,
        quality=ComponentQuality.FRESH,
    )


def gemini_factory(
    *, response: dict | None = None, failure: str | None = None
) -> GeminiInterpretationProvider:
    mock_client = MagicMock()
    if failure == "timeout":
        mock_client.models.generate_content.side_effect = TimeoutError(
            "Gemini call timed out"
        )
    elif failure == "refusal":
        mock_resp = MagicMock()
        mock_resp.text = ""
        mock_resp.candidates = [MagicMock(finish_reason="SAFETY")]
        mock_client.models.generate_content.return_value = mock_resp
    elif failure == "malformed":
        mock_resp = MagicMock()
        mock_resp.text = "NOT JSON {"
        mock_resp.candidates = [MagicMock(finish_reason="STOP")]
        mock_client.models.generate_content.return_value = mock_resp
    elif failure == "schema":
        mock_resp = MagicMock()
        mock_resp.text = '{"sentiment_label": "INVALID_LABEL", "sentiment_score": 99.0}'
        mock_resp.candidates = [MagicMock(finish_reason="STOP")]
        mock_client.models.generate_content.return_value = mock_resp
    else:
        mock_resp = MagicMock()
        import json

        mock_resp.text = json.dumps(response or valid_interpretation_json())
        mock_resp.candidates = [MagicMock(finish_reason="STOP")]
        mock_client.models.generate_content.return_value = mock_resp
    return GeminiInterpretationProvider(
        api_key="test-key", model="gemini-2.5-flash", client=mock_client
    )


def groq_factory(
    *, response: dict | None = None, failure: str | None = None
) -> GroqInterpretationProvider:
    mock_client = MagicMock()
    if failure == "timeout":
        mock_client.chat.completions.create.side_effect = TimeoutError(
            "Groq call timed out"
        )
    elif failure == "refusal":
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_choice.message.refusal = "Content blocked by safety policy"
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )
    elif failure == "malformed":
        mock_choice = MagicMock()
        mock_choice.message.content = "{bad json"
        mock_choice.message.refusal = None
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )
    elif failure == "schema":
        mock_choice = MagicMock()
        mock_choice.message.content = '{"sentiment_label": "bad", "summary": ""}'
        mock_choice.message.refusal = None
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )
    else:
        import json

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(
            response or valid_interpretation_json()
        )
        mock_choice.message.refusal = None
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[mock_choice]
        )
    return GroqInterpretationProvider(
        api_key="test-key", model="llama-3.3-70b-versatile", client=mock_client
    )


def ollama_factory(
    *, response: dict | None = None, failure: str | None = None
) -> OllamaInterpretationProvider:
    mock_client = MagicMock()
    if failure == "timeout":
        mock_client.post.side_effect = TimeoutError("Ollama call timed out")
    elif failure == "refusal":
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Model refused request"
        mock_client.post.return_value = mock_resp
    elif failure == "malformed":
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "not-json"}}
        mock_client.post.return_value = mock_resp
    elif failure == "schema":
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": '{"sentiment_label": "bad"}'}
        }
        mock_client.post.return_value = mock_resp
    else:
        import json

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": json.dumps(response or valid_interpretation_json())}
        }
        mock_client.post.return_value = mock_resp
    return OllamaInterpretationProvider(
        base_url="http://localhost:11434", model="vantage-fin", client=mock_client
    )


@pytest.mark.parametrize("factory", [gemini_factory, groq_factory, ollama_factory])
def test_valid_output_round_trips(
    factory, metrics: list[ResearchMetric], news: NewsSnapshot
) -> None:
    provider = factory(response=valid_interpretation_json())
    result = provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert result.sentiment_label == "mixed"
    assert result.evidence_ids == ["news-1"]
    assert result.sentiment_score == 0.15


@pytest.mark.parametrize("failure", ["timeout", "refusal", "malformed", "schema"])
def test_failure_never_becomes_neutral(
    failure: str, metrics: list[ResearchMetric], news: NewsSnapshot
) -> None:
    provider = gemini_factory(failure=failure)
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code in {"MODEL_UNAVAILABLE", "MODEL_OUTPUT_INVALID"}


def test_unknown_evidence_id_is_rejected(
    metrics: list[ResearchMetric], news: NewsSnapshot
) -> None:
    provider = gemini_factory(
        response={**valid_interpretation_json(), "evidence_ids": ["invented"]}
    )
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code == "MODEL_OUTPUT_INVALID"


def test_retry_succeeds_after_transient_failure(
    metrics: list[ResearchMetric], news: NewsSnapshot
) -> None:
    mock_client = MagicMock()
    import json

    mock_resp = MagicMock()
    mock_resp.text = json.dumps(valid_interpretation_json())
    mock_resp.candidates = [MagicMock(finish_reason="STOP")]
    # Attempt 1 times out, Attempt 2 succeeds
    mock_client.models.generate_content.side_effect = [
        TimeoutError("Connection dropped"),
        mock_resp,
    ]
    provider = GeminiInterpretationProvider(
        api_key="test-key", model="gemini-2.5-flash", client=mock_client
    )
    result = provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert result.sentiment_label == "mixed"
    assert mock_client.models.generate_content.call_count == 2


def test_retry_exhaustion_raises_error(
    metrics: list[ResearchMetric], news: NewsSnapshot
) -> None:
    mock_client = MagicMock()
    # Both attempts time out
    mock_client.models.generate_content.side_effect = [
        TimeoutError("Attempt 1 timeout"),
        TimeoutError("Attempt 2 timeout"),
    ]
    provider = GeminiInterpretationProvider(
        api_key="test-key", model="gemini-2.5-flash", client=mock_client
    )
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code == "MODEL_UNAVAILABLE"
    assert mock_client.models.generate_content.call_count == 2


def test_refusal_is_never_retried(
    metrics: list[ResearchMetric], news: NewsSnapshot
) -> None:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = ""
    mock_resp.candidates = [MagicMock(finish_reason="SAFETY")]
    mock_client.models.generate_content.return_value = mock_resp
    provider = GeminiInterpretationProvider(
        api_key="test-key", model="gemini-2.5-flash", client=mock_client
    )
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code in {"MODEL_UNAVAILABLE", "MODEL_OUTPUT_INVALID"}
    # Call count must be exactly 1, no retries on refusal
    assert mock_client.models.generate_content.call_count == 1


@pytest.mark.parametrize(
    ("provider_name", "expected_cls"),
    [
        ("gemini", GeminiInterpretationProvider),
        ("groq", GroqInterpretationProvider),
        ("ollama", OllamaInterpretationProvider),
    ],
)
def test_build_interpretation_provider(provider_name: str, expected_cls: type) -> None:
    settings = Settings(LLM_PROVIDER=provider_name)
    provider = build_interpretation_provider(settings)
    assert isinstance(provider, expected_cls)


@pytest.fixture(params=["gemini", "groq", "ollama"])
def adapter(request, monkeypatch):
    """Replace only the network boundary; run the real builder and adapter."""
    name = request.param

    def build(outcomes, *, max_retries=1, timeout_seconds=7):
        def response(payload):
            if isinstance(payload, (Exception, httpx.Response, SimpleNamespace)):
                return payload
            content = payload if isinstance(payload, str) else json.dumps(payload)
            if name == "gemini":
                return SimpleNamespace(text=content, candidates=[])
            if name == "groq":
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=content, refusal=None)
                        )
                    ]
                )
            return httpx.Response(
                200,
                json={"message": {"content": content}},
                request=httpx.Request("POST", "http://localhost/api/chat"),
            )

        call = MagicMock(side_effect=[response(item) for item in outcomes])
        client = MagicMock()
        if name == "gemini":
            from google import genai

            client.models.generate_content = call
            constructor = MagicMock(return_value=client)
            monkeypatch.setattr(genai, "Client", constructor)
        elif name == "groq":
            import groq

            client.chat.completions.create = call
            constructor = MagicMock(return_value=client)
            monkeypatch.setattr(groq, "Groq", constructor)
        else:
            client.post = call
            constructor = MagicMock(return_value=client)
            monkeypatch.setattr(httpx, "Client", constructor)
        provider = build_interpretation_provider(
            Settings(
                _env_file=None,
                LLM_PROVIDER=name,
                GEMINI_API_KEY="test",
                GROQ_API_KEY="test",
                LLM_MAX_RETRIES=max_retries,
                LLM_TIMEOUT_SECONDS=timeout_seconds,
            )
        )
        return provider, call, constructor

    return name, build


def transport_error(name, kind):
    request = httpx.Request("POST", "http://localhost/model")
    if kind == "timeout":
        return httpx.ReadTimeout("timed out", request=request)
    if kind == "connection":
        if name == "groq":
            from groq import APIConnectionError

            return APIConnectionError(request=request)
        return httpx.ConnectError("connection failed", request=request)
    if kind == "misleading_message":
        return ValueError("timeout in invalid configuration")
    if name == "gemini":
        from google.genai.errors import APIError

        return APIError(kind, {"error": {"message": "provider error"}})
    response = httpx.Response(kind, request=request)
    if name == "groq":
        from groq import APIStatusError

        return APIStatusError("provider error", response=response, body=None)
    return httpx.HTTPStatusError("provider error", request=request, response=response)


@pytest.mark.parametrize("kind", ["timeout", "connection", 429, 500, 503])
def test_each_adapter_retries_transient_failure(adapter, kind, metrics, news):
    name, build = adapter
    provider, call, _ = build(
        [transport_error(name, kind), valid_interpretation_json()]
    )
    result = provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert result.sentiment_label == "mixed"
    assert result.evidence_ids == ["news-1"]
    assert call.call_count == 2


@pytest.mark.parametrize("max_retries", [0, 1, 3])
@pytest.mark.parametrize("error_kind", ["timeout", "builtin_timeout"])
def test_each_adapter_exhausts_exact_retry_budget(
    adapter, max_retries, error_kind, metrics, news
):
    name, build = adapter
    error = (
        TimeoutError()
        if error_kind == "builtin_timeout"
        else transport_error(name, error_kind)
    )
    provider, call, _ = build([error] * 6, max_retries=max_retries)
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code == "MODEL_UNAVAILABLE"
    assert call.call_count == max_retries + 1


@pytest.mark.parametrize("kind", [400, 401, 403, 404, 422, "misleading_message"])
def test_each_adapter_never_retries_permanent_errors(adapter, kind, metrics, news):
    name, build = adapter
    provider, call, _ = build(
        [transport_error(name, kind), valid_interpretation_json()]
    )
    with pytest.raises(VantageError):
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert call.call_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "",
        {"bad": "schema"},
        {**valid_interpretation_json(), "evidence_ids": ["invented"]},
        {**valid_interpretation_json(), "summary": "Revenue grew 25 percent."},
        {**valid_interpretation_json(), "evidence_ids": []},
        {**valid_interpretation_json(), "summary": "The stock will rise soon."},
        {**valid_interpretation_json(), "warnings": ["Consider buying this security."]},
        {**abstained_interpretation_json(), "sentiment_label": "positive"},
        {**valid_interpretation_json(), "summary": "Buy AAPL."},
        {**valid_interpretation_json(), "warnings": ["Recommendation: **BUY**"]},
        {**valid_interpretation_json(), "summary": "Revenue grew \u00bd percent."},
    ],
)
def test_each_adapter_never_retries_invalid_output(adapter, payload, metrics, news):
    _, build = adapter
    provider, call, _ = build([payload, valid_interpretation_json()])
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert call.call_count == 1


def test_each_adapter_applies_timeout_and_disables_sdk_retries(adapter, metrics, news):
    name, build = adapter
    provider, call, constructor = build([valid_interpretation_json()])
    provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    options = constructor.call_args.kwargs
    if name == "gemini":
        assert options["http_options"].timeout == 7000
        assert options["http_options"].retry_options.attempts == 1
    elif name == "groq":
        assert options["timeout"] == 7
        assert options["max_retries"] == 0
    else:
        assert options["timeout"] == 7
        assert call.call_args.kwargs["timeout"] == 7


def test_disabled_provider_is_first_class(metrics, news):
    provider = build_interpretation_provider(
        Settings(_env_file=None, LLM_PROVIDER="disabled")
    )
    assert provider.name == "disabled"
    assert provider.model == "none"
    assert provider.enabled is False
    assert provider.interpret(symbol="AAPL", metrics=metrics, news=news) is None


@pytest.mark.parametrize(
    "values",
    [{"LLM_TIMEOUT_SECONDS": 0}, {"LLM_TIMEOUT_SECONDS": -1}, {"LLM_MAX_RETRIES": -1}],
)
def test_invalid_execution_bounds_are_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429, 500, 503])
@pytest.mark.parametrize("adapter", ["ollama"], indirect=True)
def test_ollama_http_status_controls_retry(adapter, status, metrics, news):
    _, build = adapter
    response = httpx.Response(
        status, request=httpx.Request("POST", "http://localhost/api/chat")
    )
    provider, call, _ = build([response, valid_interpretation_json()])
    if status == 429 or status >= 500:
        assert (
            provider.interpret(
                symbol="AAPL", metrics=metrics, news=news
            ).sentiment_label
            == "mixed"
        )
        assert call.call_count == 2
    else:
        with pytest.raises(VantageError):
            provider.interpret(symbol="AAPL", metrics=metrics, news=news)
        assert call.call_count == 1


@pytest.mark.parametrize("factory", [gemini_factory, groq_factory, ollama_factory])
def test_every_provider_refusal_is_not_retried(factory, metrics, news):
    provider = factory(failure="refusal")
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    client = provider._client
    call = {
        "gemini": client.models.generate_content,
        "groq": client.chat.completions.create,
        "ollama": client.post,
    }[provider.name]
    assert call.call_count == 1


@pytest.mark.parametrize("adapter", ["groq"], indirect=True)
def test_default_groq_llama_uses_json_object_mode(adapter, metrics, news):
    _, build = adapter
    provider, call, _ = build([valid_interpretation_json()])

    provider.interpret(symbol="AAPL", metrics=metrics, news=news)

    assert call.call_args.kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "model",
    ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"],
)
def test_groq_uses_strict_schema_for_supported_models(model, metrics, news):
    provider = groq_factory()
    provider.model = model

    provider.interpret(symbol="AAPL", metrics=metrics, news=news)

    response_format = provider._client.chat.completions.create.call_args.kwargs[
        "response_format"
    ]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True


@pytest.mark.parametrize("adapter", ["groq"], indirect=True)
def test_groq_no_choices_is_not_retried(adapter, metrics, news):
    _, build = adapter
    provider, call, _ = build(
        [SimpleNamespace(choices=[]), valid_interpretation_json()]
    )
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert call.call_count == 1


@pytest.mark.parametrize(
    "body", [None, [], {"message": None}, {"message": []}, {"message": {"content": 12}}]
)
@pytest.mark.parametrize("adapter", ["ollama"], indirect=True)
def test_ollama_invalid_envelope_is_not_retried(adapter, body, metrics, news):
    _, build = adapter
    response = httpx.Response(
        200, json=body, request=httpx.Request("POST", "http://localhost/api/chat")
    )
    provider, call, _ = build([response, valid_interpretation_json()])
    with pytest.raises(VantageError) as caught:
        provider.interpret(symbol="AAPL", metrics=metrics, news=news)
    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert call.call_count == 1
