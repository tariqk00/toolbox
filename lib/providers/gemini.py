"""
Gemini provider — remote inference, supports text, PDF, and images.
Primary for multi-modal tasks, fallback for text tasks.
"""
import os
import logging
import time
from google import genai
from google.genai import types
from .base import AIProvider, ProviderSkip, RateLimitError, QuotaExhaustedError
from .. import quota_manager

logger = logging.getLogger("DriveSorter.AI.Gemini")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_DIR = os.path.join(_BASE_DIR, 'config')

FREE_SECRET_PATH = os.path.join(_CONFIG_DIR, 'gemini_ai_studio_secret')
PAID_SECRET_PATH = os.path.join(_CONFIG_DIR, 'gemini_secret')

FREE_MODEL = os.getenv('GEMINI_FREE_MODEL', 'gemini-2.0-flash-lite')
PAID_MODEL = os.getenv('GEMINI_PAID_MODEL', 'gemini-2.0-flash')

_free_client = None
_paid_client = None

def _get_client(is_paid=False):
    global _free_client, _paid_client
    if is_paid:
        if _paid_client is None:
            key = os.getenv('GEMINI_PAID_API_KEY')
            if not key and os.path.exists(PAID_SECRET_PATH):
                with open(PAID_SECRET_PATH) as f:
                    key = f.read().strip()
            if not key: return None
            _paid_client = genai.Client(api_key=key)
        return _paid_client
    else:
        if _free_client is None:
            key = os.getenv('GEMINI_FREE_API_KEY')
            if not key and os.path.exists(FREE_SECRET_PATH):
                with open(FREE_SECRET_PATH) as f:
                    key = f.read().strip()
            if not key: return None
            _free_client = genai.Client(api_key=key)
        return _free_client

class GeminiProvider(AIProvider):
    name = "Gemini"

    def __init__(self, model_name: str = None, api_key: str = None):
        self.model_name = model_name
        self.api_key = api_key
        self._gateway_client = genai.Client(api_key=api_key) if api_key else None

    def supports(self, mime_type: str) -> bool:
        # Gemini handles almost everything
        return True

    def analyze(self, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, int]:
        # If initialized by gateway with specific model/key
        if self._gateway_client and self.model_name:
            return self._analyze_gateway(content_bytes, mime_type, prompt)
        
        # Original backward-compatible path
        # Decide between Free (Lite) or Paid (Pro)
        use_paid = quota_manager.is_rpd_exhausted()
        client = _get_client(is_paid=use_paid)
        model = PAID_MODEL if use_paid else FREE_MODEL
        
        if client is None:
            # Fallback to other if possible
            if not use_paid:
                client = _get_client(is_paid=True)
                model = PAID_MODEL
            if client is None:
                raise ProviderSkip("Gemini client not configured")

        logger.info(f"  [Gemini/{model}] analyzing...")
        
        try:
            # Construct content based on type
            contents = [prompt]
            if mime_type == 'text/plain':
                contents.append(content_bytes.decode('utf-8', errors='ignore'))
            else:
                contents.append(types.Part.from_bytes(data=content_bytes, mime_type=mime_type))

            resp = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(max_output_tokens=1024)
            )
            
            text = resp.text.strip()
            tokens = resp.usage_metadata.total_token_count if resp.usage_metadata else 0
            
            if not use_paid:
                quota_manager.record_call()
            
            logger.info(f"  [Gemini/{model}] tokens={tokens}")
            return text, tokens
            
        except Exception as e:
            msg = str(e).upper()
            # Distinguish Billing/Monthly Cap from transient Rate Limits
            # Persistent errors (trip circuit breaker)
            if any(x in msg for x in ["YOU EXCEEDED YOUR CURRENT QUOTA", "BILLING DETAILS", "MONTHLY CAP", "LIMIT: 0"]):
                raise QuotaExhaustedError(f"Gemini billing quota exhausted: {e}")
            
            # Transient errors (retry with backoff)
            if any(x in msg for x in ["429", "RESOURCE_EXHAUSTED", "RATE_LIMIT", "REQUESTS PER MINUTE", "QUOTA EXCEEDED"]):
                # NOTE: RESOURCE_EXHAUSTED is used for transient RPM/TPM as well
                raise RateLimitError(f"Gemini {model} rate limited: {e}")
            raise

    def _analyze_gateway(self, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, int]:
        """Gateway-specific analyze path."""
        try:
            start = time.time()
            # Gateway handles payload wrapping
            response = self._gateway_client.models.generate_content(
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
            # Distinguish Billing/Monthly Cap from transient Rate Limits
            if any(x in msg for x in ["YOU EXCEEDED YOUR CURRENT QUOTA", "BILLING DETAILS", "MONTHLY CAP", "LIMIT: 0"]):
                raise QuotaExhaustedError(f"Gemini billing quota exhausted: {e}")
                
            if any(x in msg for x in ["429", "RESOURCE_EXHAUSTED", "RATE_LIMIT", "REQUESTS PER MINUTE", "QUOTA EXCEEDED"]):
                raise RateLimitError(f"Gemini rate limited: {e}")
            raise
