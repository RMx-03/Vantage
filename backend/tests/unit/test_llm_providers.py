from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
import pytest

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import (
    AIInterpretation,
    ComponentQuality,
    NewsItem,
    NewsSnapshot,
    ResearchMetric,
)
from app.providers.llm import (
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
