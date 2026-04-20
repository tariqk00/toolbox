"""
Groq provider — remote inference, text-only, high rate limits.
Primary fallback when Ollama fails or is unreachable.
"""
import os
import logging
from .base import AIProvider, ProviderSkip

logger = logging.getLogger("DriveSorter.AI.Groq")

GROQ_MODEL = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SECRET_PATH = os.path.join(_BASE_DIR, 'config', 'groq_secret')

_client = None


def _get_client():
    global _client
    if _client is None:
        from groq import Groq
        key = os.getenv('GROQ_API_KEY')
        if not key and os.path.exists(_SECRET_PATH):
            with open(_SECRET_PATH) as f:
                key = f.read().strip()
        if not key:
            raise ValueError("Groq API key missing (config/groq_secret or GROQ_API_KEY)")
        _client = Groq(api_key=key)
    return _client


class GroqProvider(AIProvider):
    name = "Groq"

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
                model=GROQ_MODEL,
                messages=[{'role': 'user', 'content': full_prompt}],
                max_tokens=512,
            )
            text = resp.choices[0].message.content.strip()
            tokens = resp.usage.total_tokens if resp.usage else 0
            logger.info(f"  [Groq/{GROQ_MODEL}] tokens={tokens}")
            return text, tokens
        except Exception as e:
            msg = str(e)
            if '429' in msg or 'rate_limit' in msg.lower():
                raise ProviderSkip(f"Groq rate limited: {e}")
            raise
