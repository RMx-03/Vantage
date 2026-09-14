import json
from typing import Any
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
    return result


class GeminiInterpretationProvider(InterpretationProvider):
    name: str = "gemini"

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-2.5-flash",
        client: Any = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from google import genai
        return genai.Client(api_key=self.api_key)

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

        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=user_content,
                    config=config,
                )
            except Exception as e:
                err_str = str(e).lower()
                is_timeout = (
                    isinstance(e, (TimeoutError, ConnectionError))
                    or "timeout" in err_str
                    or "deadline" in err_str
                )
                if is_timeout and attempt == 0:
                    continue
                code = "MODEL_UNAVAILABLE" if is_timeout else "MODEL_UNAVAILABLE"
                raise VantageError(
                    code=code,
                    safe_message=f"Gemini call failed: {e}",
                ) from e

            # Check refusal
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                if finish_reason and str(finish_reason).upper() in {
                    "SAFETY",
                    "RECITATION",
                    "BLOCKLIST",
                    "OTHER",
                }:
                    raise VantageError(
                        code="MODEL_OUTPUT_INVALID",
                        safe_message="Model refused or blocked content.",
                    )

            raw_text = getattr(response, "text", "") or ""
            if not raw_text.strip():
                raise VantageError(
                    code="MODEL_OUTPUT_INVALID",
                    safe_message="Model returned empty response.",
                )

            try:
                return validate_interpretation(raw_text, allowed_evidence_ids)
            except VantageError:
                if attempt == 0:
                    continue
                raise

        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation was unavailable after retry.",
        )


class GroqInterpretationProvider(InterpretationProvider):
    name: str = "groq"

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        json_schema_models: list[str] | None = None,
        client: Any = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.json_schema_models = json_schema_models or [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
        ]
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        import groq
        return groq.Groq(api_key=self.api_key)

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

        for attempt in range(2):
            try:
                completion = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format=response_format,
                )
            except Exception as e:
                err_str = str(e).lower()
                is_timeout = (
                    isinstance(e, (TimeoutError, ConnectionError))
                    or "timeout" in err_str
                )
                if is_timeout and attempt == 0:
                    continue
                code = "MODEL_UNAVAILABLE" if is_timeout else "MODEL_UNAVAILABLE"
                raise VantageError(
                    code=code,
                    safe_message=f"Groq provider call failed: {e}",
                ) from e

            choices = getattr(completion, "choices", None)
            if not choices:
                if attempt == 0:
                    continue
                raise VantageError(
                    code="MODEL_OUTPUT_INVALID",
                    safe_message="Groq returned no choices.",
                )

            choice = choices[0]
            message = getattr(choice, "message", None)
            refusal = getattr(message, "refusal", None)
            if refusal:
                raise VantageError(
                    code="MODEL_OUTPUT_INVALID",
                    safe_message=f"Groq refused request: {refusal}",
                )

            raw_content = getattr(message, "content", "") or ""
            try:
                return validate_interpretation(raw_content, allowed_evidence_ids)
            except VantageError:
                if attempt == 0:
                    continue
                raise

        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation was unavailable after retry.",
        )


class OllamaInterpretationProvider(InterpretationProvider):
    name: str = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "vantage-fin",
        timeout_seconds: int = 60,
        client: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
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

        for attempt in range(2):
            try:
                resp = client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
            except Exception as e:
                err_str = str(e).lower()
                is_timeout = (
                    isinstance(e, (TimeoutError, ConnectionError))
                    or "timeout" in err_str
                )
                if is_timeout and attempt == 0:
                    continue
                raise VantageError(
                    code="MODEL_UNAVAILABLE",
                    safe_message=f"Ollama call failed: {e}",
                ) from e

            status_code = getattr(resp, "status_code", 200)
            if status_code in {401, 403}:
                raise VantageError(
                    code="MODEL_OUTPUT_INVALID",
                    safe_message="Ollama request was refused or unauthorized.",
                )
            if status_code >= 400:
                if attempt == 0:
                    continue
                raise VantageError(
                    code="MODEL_UNAVAILABLE",
                    safe_message=f"Ollama returned HTTP error {status_code}.",
                )

            try:
                resp_json = resp.json()
                msg = resp_json.get("message", {})
                content = msg.get("content", "")
            except Exception:
                if attempt == 0:
                    continue
                raise VantageError(
                    code="MODEL_OUTPUT_INVALID",
                    safe_message="Failed to parse Ollama response.",
                )

            try:
                return validate_interpretation(content, allowed_evidence_ids)
            except VantageError:
                if attempt == 0:
                    continue
                raise

        raise VantageError(
            code="MODEL_OUTPUT_INVALID",
            safe_message="AI interpretation was unavailable after retry.",
        )


def build_interpretation_provider(settings: Settings) -> InterpretationProvider:
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "gemini":
        return GeminiInterpretationProvider(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )
    if provider == "groq":
        return GroqInterpretationProvider(
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            json_schema_models=settings.GROQ_JSON_SCHEMA_MODELS,
        )
    if provider == "ollama":
        return OllamaInterpretationProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            timeout_seconds=settings.OLLAMA_TIMEOUT_SECONDS,
        )
    raise VantageError(
        code="CONFIG_ERROR",
        safe_message=f"Unsupported LLM provider: {settings.LLM_PROVIDER}",
    )
