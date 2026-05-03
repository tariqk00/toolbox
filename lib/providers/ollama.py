"""
Ollama provider — local inference, text-only.
"""
import os
import time
import logging
import requests
from .base import AIProvider, ProviderSkip

logger = logging.getLogger("DriveSorter.AI.Ollama")

OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'gemma4:e2b')

class OllamaProvider(AIProvider):
    name = "Ollama"

    def __init__(self, model_name: str = None):
        self.model_name = model_name or OLLAMA_MODEL

    def supports(self, mime_type: str) -> bool:
        return mime_type == 'text/plain'

    def analyze(self, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, int]:
        text_content = content_bytes.decode('utf-8', errors='ignore')
        payload = {
            "model": self.model_name,
            "prompt": f"{prompt}\n\nCONTENT TO ANALYZE:\n{text_content}",
            "stream": False,
        }
        try:
            start = time.time()
            response = requests.post(OLLAMA_URL, json=payload, timeout=30)
            duration = time.time() - start
            
            if response.status_code == 200:
                data = response.json()
                text = data.get('response', '').strip()
                # Ollama doesn't give precise tokens in same way, but 'prompt_eval_count' + 'eval_count'
                tokens = data.get('prompt_eval_count', 0) + data.get('eval_count', 0)
                logger.info(f"  [Ollama/{self.model_name}] tokens={tokens} in {round(duration, 1)}s")
                return text, tokens
            raise RuntimeError(f"Ollama HTTP {response.status_code}")
        except requests.exceptions.ConnectionError:
            raise RuntimeError("Ollama not reachable")
