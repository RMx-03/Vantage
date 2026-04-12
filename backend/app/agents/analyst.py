import logging

from app.models.state import AgentState

logger = logging.getLogger(__name__)


def run_analyst(state: AgentState) -> dict:
    """
    Analyst node — produces a sentiment score from scraped news context.
    Supports multi-provider routing (Ollama, Gemini, Groq).

    Args:
        state: Current AgentState (reads 'ticker' and 'news_context')

    Returns:
        Partial state dict with 'sentiment_score' and 'current_step'.
    """
    ticker = state["ticker"]
    news_context = state.get("news_context", [])

    logger.info(
        "[analyst] Analysing sentiment for %s (%d headline(s))",
        ticker,
        len(news_context),
    )

    from app.prompts.sentiment_prompt import build_sentiment_prompt
    from app.core.config import settings
    import json

    prompt = build_sentiment_prompt(ticker, news_context)
    sentiment_score = 0.0

    try:
        provider = settings.LLM_PROVIDER.lower()
        response_text = ""

        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(settings.GEMINI_MODEL)
            # Use JSON mode if model supports it, but relies mainly on the prompt
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                )
            )
            response_text = response.text

        elif provider == "groq":
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=settings.GROQ_MODEL,
                response_format={"type": "json_object"},
            )
            response_text = chat_completion.choices[0].message.content

        else:
            # Default to Ollama
            import httpx
            payload = {
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
            with httpx.Client(timeout=settings.OLLAMA_TIMEOUT_SECONDS) as client:
                resp = client.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
                resp.raise_for_status()
                outer = resp.json()
                response_text = outer.get("response", "{}")

        # Unified Parsing
        inner = json.loads(response_text) if isinstance(response_text, str) else response_text
        sentiment_score = max(-1.0, min(1.0, float(inner.get("sentiment_score", 0.0))))
        logger.info("[analyst] Successfully retrieved sentiment from %s.", provider)

    except Exception as e:
        logger.error("[analyst] Failed to connect / parse %s. Error: %s", settings.LLM_PROVIDER, e)
        sentiment_score = 0.0 # Default if failed

    logger.info(
        "[analyst] Sentiment score for %s: %.2f",
        ticker,
        sentiment_score,
    )

    return {
        "sentiment_score": sentiment_score,
        "current_step": "analyst_complete",
    }
