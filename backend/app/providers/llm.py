import json
import re
from collections.abc import Callable
from typing import Any
import httpx
from groq import APIConnectionError
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.errors import VantageError
from app.domain.research import (
    AIInterpretation,
    NewsSnapshot,
    ResearchMetric,
)
from app.prompts.research_interpretation import (
    SYSTEM_INSTRUCTION,
    build_interpretation_input,
)
from app.providers.contracts import InterpretationProvider


_ABSTENTION_REASONS = frozenset(
    {"MODEL_NOT_RUN", "MODEL_UNAVAILABLE", "MODEL_OUTPUT_INVALID"}
)
_NUMERIC_CLAIM = re.compile(
    r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"million|billion|trillion)\b",
    re.IGNORECASE,
)
_UNSAFE_LANGUAGE = re.compile(
    # Trading instructions and recommendations; do not match shareholder,
    # resellers, buybacks, or historical statements such as "plans on hold".
    r"\b(?:buy|buying|sell|selling|hold|holding|purchase|avoid|recommend)\s+"
    r"(?:(?:this|that|the|these|those|your|their|our|its|a)\s+)?"
    r"(?:stock|stocks|share|shares|security|securities|position|positions)\b"
    r"|\b(?:should|must|consider|recommend|recommended|recommends|advise|advised)\b"
    r"(?:\s+\w+){0,3}\s+(?:buy|buying|sell|selling|hold|holding|invest|investing)\b"
    r"|\b(?:a|strong)\s+(?:buy|sell|hold)\b"
    r"|\b(?:buy|sell|hold)\s+(?:rating|recommendation)\b"
    r"|(?:^|[.!?;:]\s*)(?:buy|sell|hold)(?:\s+(?:now|immediately))?\s*(?:[.!?;:]|$)"
    r"|\b(?:invest|investing)\s+in\b"
    r"|\b(?:suitable|appropriate|ideal|perfect)\s+for\b"
    r"|\bgood\s+fit\s+for\s+(?:you|your|investors|retirees)\b"
    r"|\byour\s+(?:portfolio|risk\s+tolerance|investment\s+goals|financial\s+"
    r"(?:goals|situation)|retirement)\b"
    r"|\b(?:target[\s-]+prices?|price[\s-]+targets?)\b"
    r"|\b(?:guarantee|guarantees|guaranteed|guaranteeing|risk[\s-]+free)\b"
    # Certain future outcomes are outside historical interpretation.
    r"|\b(?:will|going\s+to|certain\s+to|sure\s+to|bound\s+to|set\s+to)\b"
    r"(?:\s+\w+){0,3}\s+(?:rise|fall|gain|grow|increase|decrease|drop|rally|"
    r"recover|outperform|underperform|deliver|return|profit|double|triple|"
    r"go\s+(?:up|down)|make\s+money)\b"
    r"|\b(?:cannot|can't|can\s+not)\s+lose\b"
    r"|\b(?:returns?|profits?|gains?)\s+(?:are|is)\s+(?:certain|assured)\b",
    re.IGNORECASE,
)


def is_transient_model_error(error: Exception) -> bool:
    """Retry only typed transport failures or explicit retryable HTTP statuses."""
    if isinstance(
        error,
        (
            TimeoutError,
            ConnectionError,
            httpx.TimeoutException,
            httpx.NetworkError,
            APIConnectionError,
        ),
    ):
        return True
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(error, "code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    return isinstance(status, int) and (status == 429 or 500 <= status < 600)


def _request_with_retries(request: Callable[[], Any], max_retries: int) -> Any:
    for attempt in range(max_retries + 1):
        try:
            return request()
        except VantageError:
            raise
        except Exception as exc:
            if attempt < max_retries and is_transient_model_error(exc):
                continue
            raise VantageError(
                code="MODEL_UNAVAILABLE",
                safe_message="AI interpretation provider was unavailable.",
            ) from exc
    raise ValueError("max_retries must be non-negative")


class DisabledInterpretationProvider(InterpretationProvider):
    name: str = "disabled"
    model: str = "none"
    enabled: bool = False

    def interpret(
        self, *, symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot
    ) -> None:
        return None


def validate_interpretation(
    payload: object, allowed_evidence_ids: set[str]
) -> AIInterpretation:
    try:
        if isinstance(payload, str):
            payload = json.loads(payload)
        result = AIInterpretation.model_validate(payload)
    except (ValidationError, json.JSONDecodeError, TypeError) as exc:
        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation was unavailable.",
        ) from exc
    if not set(result.evidence_ids) <= allowed_evidence_ids:
        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation referenced unsupported evidence.",
        )
    authored_fields = [result.summary, *result.warnings, result.abstention_reason or ""]
    if any(_NUMERIC_CLAIM.search(text) for text in authored_fields):
        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation contained unsupported numeric claims.",
        )
    if any(_UNSAFE_LANGUAGE.search(text) for text in authored_fields):
        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation contained unsupported advisory or predictive language.",
        )
    if result.abstained:
        consistent = (
            result.sentiment_label == "unavailable"
            and result.sentiment_score is None
            and not result.evidence_ids
            and result.abstention_reason in _ABSTENTION_REASONS
        )
    else:
        consistent = (
            result.sentiment_label != "unavailable"
            and result.abstention_reason is None
            and bool(result.evidence_ids)
        )
    if not consistent:
        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation contained inconsistent abstention fields.",
        )
    return result


class GeminiInterpretationProvider(InterpretationProvider):
    name: str = "gemini"
    enabled: bool = True

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.5-flash",
        client: Any = None,
        timeout_seconds: int = 30,
        max_retries: int = 1,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._client = client
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=self.timeout_seconds * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def interpret(
        self, *, symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot
    ) -> AIInterpretation:
        allowed_evidence_ids = {item.evidence_id for item in news.items}
        input_data = build_interpretation_input(symbol, metrics, news)
        user_content = json.dumps(input_data)

        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AIInterpretation,
            system_instruction=SYSTEM_INSTRUCTION,
        )

        client = self._get_client()

        response = _request_with_retries(
            lambda: client.models.generate_content(
                model=self.model, contents=user_content, config=config
            ),
            self.max_retries,
        )
        if getattr(response, "candidates", None):
            finish_reason = getattr(response.candidates[0], "finish_reason", None)
            reason = getattr(finish_reason, "value", finish_reason)
            if reason in {"SAFETY", "RECITATION", "BLOCKLIST", "OTHER"}:
                raise VantageError(
                    code="MODEL_OUTPUT_INVALID",
                    safe_message="Model refused or blocked content.",
                )
        return validate_interpretation(
            getattr(response, "text", "") or "", allowed_evidence_ids
        )


class GroqInterpretationProvider(InterpretationProvider):
    name: str = "groq"
    enabled: bool = True

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        json_schema_models: list[str] | None = None,
        client: Any = None,
        timeout_seconds: int = 30,
        max_retries: int = 1,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.json_schema_models = json_schema_models or [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
        ]
        self._client = client
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        import groq

        return groq.Groq(
            api_key=self.api_key, timeout=self.timeout_seconds, max_retries=0
        )

    def interpret(
        self, *, symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot
    ) -> AIInterpretation:
        allowed_evidence_ids = {item.evidence_id for item in news.items}
        input_data = build_interpretation_input(symbol, metrics, news)
        user_content = json.dumps(input_data)

        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_content},
        ]

        if self.model in self.json_schema_models:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ai_interpretation",
                    "schema": AIInterpretation.model_json_schema(),
                    "strict": True,
                },
            }
        else:
            response_format = {"type": "json_object"}

        client = self._get_client()

        completion = _request_with_retries(
            lambda: client.chat.completions.create(
                model=self.model, messages=messages, response_format=response_format
            ),
            self.max_retries,
        )
        choices = getattr(completion, "choices", None)
        if not choices:
            raise VantageError(
                code="MODEL_OUTPUT_INVALID", safe_message="Groq returned no choices."
            )
        message = getattr(choices[0], "message", None)
        if getattr(message, "refusal", None):
            raise VantageError(
                code="MODEL_OUTPUT_INVALID",
                safe_message="AI interpretation provider refused the request.",
            )
        return validate_interpretation(
            getattr(message, "content", "") or "", allowed_evidence_ids
        )


class OllamaInterpretationProvider(InterpretationProvider):
    name: str = "ollama"
    enabled: bool = True

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "vantage-fin",
        timeout_seconds: int = 30,
        client: Any = None,
        max_retries: int = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        import httpx

        return httpx.Client(timeout=float(self.timeout_seconds))

    def interpret(
        self, *, symbol: str, metrics: list[ResearchMetric], news: NewsSnapshot
    ) -> AIInterpretation:
        allowed_evidence_ids = {item.evidence_id for item in news.items}
        input_data = build_interpretation_input(symbol, metrics, news)
        user_content = json.dumps(input_data)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_content},
            ],
            "format": AIInterpretation.model_json_schema(),
            "stream": False,
        }

        client = self._get_client()

        def request() -> Any:
            response = client.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.timeout_seconds
            )
            if response.status_code in {401, 403}:
                raise VantageError(
                    code="MODEL_OUTPUT_INVALID",
                    safe_message="Ollama request was refused or unauthorized.",
                )
            response.raise_for_status()
            return response

        resp = _request_with_retries(request, self.max_retries)
        try:
            content = resp.json()["message"]["content"]
        except (ValueError, TypeError, KeyError) as exc:
            raise VantageError(
                code="MODEL_OUTPUT_INVALID",
                safe_message="Failed to parse Ollama response.",
            ) from exc
        return validate_interpretation(content, allowed_evidence_ids)


def build_interpretation_provider(settings: Settings) -> InterpretationProvider:
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "disabled":
        return DisabledInterpretationProvider()
    if provider == "gemini":
        return GeminiInterpretationProvider(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )
    if provider == "groq":
        return GroqInterpretationProvider(
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            json_schema_models=settings.GROQ_JSON_SCHEMA_MODELS,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )
    if provider == "ollama":
        return OllamaInterpretationProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )
    raise VantageError(
        code="CONFIG_ERROR",
        safe_message="The configured AI interpretation provider is unsupported.",
    )
