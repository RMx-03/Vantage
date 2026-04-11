def build_sentiment_prompt(ticker: str, news_context: list[str]) -> str:
    """Builds the prompt to send to Ollama for sentiment analysis."""
    
    news_text = "\n".join([f"- {news}" for news in news_context]) if news_context else "No significant news found."
    
    return f"""You are an advanced quantitative financial analyst. Read the following news headlines related to the ticker {ticker}.

News Context:
{news_text}

Task: Output a JSON response containing a single key "sentiment_score". 
The score must be a float between -1.0 (extremely negative) to 1.0 (extremely positive). 
Focus only on the financial and risk implications for {ticker}.
Do not include any string, introductory text or markdown formatting except the JSON.

Expected Output Format:
{{
  "sentiment_score": <float>
}}
"""
