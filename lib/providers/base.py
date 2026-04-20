"""
Abstract base class for AI classification providers.
"""
from abc import ABC, abstractmethod


class ProviderSkip(Exception):
    """Raised when a provider is temporarily unavailable (rate limit, quota)."""


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
