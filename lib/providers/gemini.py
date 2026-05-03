"""
Gemini provider — remote inference, supports all MIME types.
"""
import os
import logging
import time
from .base import AIProvider, ProviderSkip
from google import genai
from google.genai import types

logger = logging.getLogger("toolbox.providers.gemini")

class GeminiProvider(AIProvider):
    name = "Gemini"

    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)

    def supports(self, mime_type: str) -> bool:
        return True # Gemini supports most types

    def analyze(self, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, int]:
        try:
            start = time.time()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=content_bytes, mime_type=mime_type)
                ],
                config=types.GenerateContentConfig(max_output_tokens=1024)
            )
            duration = time.time() - start
            text = response.text.strip()
            
            usage = response.usage_metadata
            tokens = usage.total_token_count if usage else 0
            
            logger.info(f"  [Gemini/{self.model_name}] tokens={tokens} ({round(duration, 1)}s)")
            return text, tokens
        except Exception as e:
            msg = str(e).upper()
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise ProviderSkip(f"Gemini rate limited: {e}")
            raise
