"""
Abstract base class for AI classification providers.
"""
from abc import ABC, abstractmethod


class ProviderSkip(Exception):
    """Raised when a provider should be skipped entirely (disabled, missing key, unsupported mime)."""


class RateLimitError(Exception):
    """Raised on 429 / RPM / TPM limits — signals the gateway to retry with backoff."""


class QuotaExhaustedError(Exception):
    """Raised when a provider's billing/monthly quota is exhausted (e.g. RESOURCE_EXHAUSTED)."""


class AIProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """Return True if this provider can handle the given MIME type."""

    @abstractmethod
    def analyze(self, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[str, int]:
        """
        Call the provider. Returns (raw_text_response, token_count).
        Raises ProviderSkip on rate limit / quota exhaustion.
        Raises Exception on hard failure.
        """
