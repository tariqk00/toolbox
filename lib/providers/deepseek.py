"""
DeepSeek provider — remote inference via DeepSeek API (OpenAI compatible).
Low-cost efficiency workhorse.
"""
import os
import logging
from .base import AIProvider, ProviderSkip, RateLimitError

logger = logging.getLogger("toolbox.providers.deepseek")

DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')

_client = None

def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        key = os.getenv('DEEPSEEK_API_KEY')
        if not key:
            # Try config/secrets.env (handled by LLMGateway)
            pass
        if not key:
            raise ValueError("DEEPSEEK_API_KEY not found")
        _client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
    return _client

class DeepSeekProvider(AIProvider):
    name = "DeepSeek"

    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name or DEEPSEEK_MODEL
        self.api_key = api_key

    def supports(self, mime_type: str) -> bool:
        # DeepSeek handles text only
        return mime_type == 'text/plain'

    def analyze(self, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, int]:
        text_content = content_bytes.decode('utf-8', errors='ignore')
        full_prompt = f"{prompt}\n\nCONTENT TO ANALYZE:\n{text_content}"

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
            resp = client.chat.completions.create(
                model=self.model_name,
                messages=[{'role': 'user', 'content': full_prompt}],
                max_tokens=2000,
            )
            text = resp.choices[0].message.content.strip()
            tokens = resp.usage.total_tokens if resp.usage else 0
            logger.info(f"  [DeepSeek/{self.model_name}] tokens={tokens}")
            return text, tokens
        except Exception as e:
            msg = str(e)
            if '429' in msg or 'rate_limit' in msg.lower():
                raise RateLimitError(f"DeepSeek rate limited: {e}")
            raise
