"""
Groq provider — remote inference, text-only, high rate limits.
Primary fallback when Ollama fails or is unreachable.
"""
import os
import logging
from .base import AIProvider, ProviderSkip, RateLimitError, QuotaExhaustedError

logger = logging.getLogger("DriveSorter.AI.Groq")

GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

_client = None

def _get_client():
    global _client
    if _client is None:
        from groq import Groq
        key = os.getenv('GROQ_API_KEY')
        if not key:
            # Try config file
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'config', 'groq_secret')
            if os.path.exists(path):
                with open(path) as f:
                    key = f.read().strip()
        if not key:
            raise ValueError("GROQ_API_KEY not found in env or config/groq_secret")
        _client = Groq(api_key=key)
    return _client

class GroqProvider(AIProvider):
    name = "Groq"

    def __init__(self, model_name: str = None):
        self.model_name = model_name or GROQ_MODEL

    def supports(self, mime_type: str) -> bool:
        # Groq handles text only — PDFs and images go to Gemini
        return mime_type == 'text/plain'

    def analyze(self, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, int]:
        if os.getenv('GROQ_PROVIDER') == 'off':
            raise ProviderSkip("Groq disabled via GROQ_PROVIDER=off")

        text_content = content_bytes.decode('utf-8', errors='ignore')
        full_prompt = f"{prompt}\n\nCONTENT TO ANALYZE:\n{text_content}"

        try:
            client = _get_client()
            resp = client.chat.completions.create(
                model=self.model_name,
                messages=[{'role': 'user', 'content': full_prompt}],
                max_tokens=512,
            )
            text = resp.choices[0].message.content.strip()
            tokens = resp.usage.total_tokens if resp.usage else 0
            logger.info(f"  [Groq/{self.model_name}] tokens={tokens}")
            return text, tokens
        except Exception as e:
            msg = str(e).lower()
            if any(x in msg for x in ['blocked_api_access', 'insufficient_funds', 'organization_spend_limit']):
                raise QuotaExhaustedError(f"Groq budget exhausted: {e}")
            if '429' in msg or 'rate_limit' in msg:
                raise RateLimitError(f"Groq rate limited: {e}")
            raise
