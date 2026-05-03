"""
AI Abstraction Layer.
Provider chain: Ollama (local) → Groq (remote, text) → Gemini (remote, all types).
"""
import os
import json
import logging
import re
from typing import Any
from .providers.ollama import OllamaProvider
from .providers.groq import GroqProvider
from .providers.gemini import GeminiProvider
from .providers.base import ProviderSkip
from . import quota_manager

logger = logging.getLogger("toolbox.ai_engine")

# Initialize providers in priority order
_PROVIDERS = [
    OllamaProvider(),
    GroqProvider(),
    GeminiProvider(),
]

def analyze_file(filename: str, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[dict, str, int]:
    """
    Core entry point for file analysis.
    Tries each provider in the chain until one succeeds.
    Returns (json_data, reasoning, tokens_used).
    """
    full_prompt = f"{prompt}\n\nFILENAME: {filename}"
    
    for provider in _PROVIDERS:
        if not provider.supports(mime_type):
            continue
            
        try:
            raw_text, tokens = provider.analyze(content_bytes, mime_type, full_prompt)
            # Parse JSON from response
            try:
                data = _parse_json(raw_text)
                reasoning = data.get('reasoning', '') or raw_text[:200]
                quota_manager.record_tokens(tokens)
                return data, reasoning, tokens
            except Exception as e:
                logger.warning(f"  [{provider.name}] JSON parse failed: {e}")
                # If JSON fails but we got text, maybe try next provider or fallback
                continue
                
        except ProviderSkip as e:
            logger.info(f"  [{provider.name}] skipped: {e}")
            continue
        except Exception as e:
            logger.error(f"  [{provider.name}] error: {e}")
            continue
            
    return {}, "All providers failed", 0

def call(prompt: str, mime_type: str = 'text/plain', max_tokens: int = 500) -> str:
    """Simple text-in, text-out interface."""
    content = prompt.encode('utf-8')
    for provider in _PROVIDERS:
        if not provider.supports(mime_type):
            continue
        try:
            text, tokens = provider.analyze(content, mime_type, "") # Provider handles prompt wrap
            quota_manager.record_tokens(tokens)
            return text
        except (ProviderSkip, Exception):
            continue
    return ""

def call_json(prompt: str, mime_type: str = 'text/plain') -> dict:
    """Simple text-in, dict-out interface."""
    res = call(prompt, mime_type)
    if not res:
        return {}
    return _parse_json(res)

def _parse_json(text: str) -> dict:
    """Robustly extract JSON from LLM markdown-wrapped text."""
    try:
        # Try direct parse
        return json.loads(text)
    except:
        # Try stripping markdown fences
        clean = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
        clean = re.sub(r'\s*```$', '', clean, flags=re.MULTILINE)
        try:
            return json.loads(clean)
        except:
            # Last ditch: search for first { and last }
            match = re.search(r'(\{.*\})', clean, re.DOTALL)
            if match:
                return json.loads(match.group(1))
    raise ValueError("No valid JSON found in response")
