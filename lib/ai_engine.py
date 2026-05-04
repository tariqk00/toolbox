"""
AI Abstraction Layer.
DEPRECATED: Use toolbox.lib.llm_gateway instead.
This module is now a shim for LLMGateway to ensure zero production bypasses.
"""
import logging
import warnings
from .llm_gateway import call_llm, call_json_llm, _parse_json

logger = logging.getLogger("toolbox.ai_engine")

def analyze_file(filename: str, content_bytes: bytes, mime_type: str, prompt: str) -> tuple[dict, str, int]:
    """Redirect to LLMGateway.call_json_llm"""
    warnings.warn("toolbox.lib.ai_engine.analyze_file is deprecated.", DeprecationWarning, stacklevel=2)
    logger.warning(f"Legacy analyze_file detected for {filename} (redirecting to gateway)")
    return call_json_llm(
        task_type='automation',
        prompt=prompt,
        content_bytes=content_bytes,
        mime_type=mime_type,
        filename=filename
    )

def analyze_with_gemini(content_bytes: bytes, mime_type: str, filename: str, folder_paths_str: str, context_hint: str = "", file_id: str = ""):
    """Old signature used by backfill.py"""
    warnings.warn("toolbox.lib.ai_engine.analyze_with_gemini is deprecated.", DeprecationWarning, stacklevel=2)
    full_prompt = f"{folder_paths_str}\n\nCONTEXT: {context_hint}\nFILENAME: {filename}"
    data, reasoning, tokens = analyze_file(filename, content_bytes, mime_type, full_prompt)
    return data, tokens

def call(prompt: str, mime_type: str = 'text/plain', max_tokens: int = 500) -> str:
    """Simple text-in, text-out interface."""
    from .llm import call as legacy_call
    return legacy_call(prompt, max_tokens=max_tokens)

def call_json(prompt: str, mime_type: str = 'text/plain') -> dict:
    """Simple text-in, dict-out interface."""
    from .llm import call_json as legacy_call_json
    return legacy_call_json(prompt)

def get_ai_supported_mime(mime_type, filename=None):
    """Moved to drive_utils, provided here as a shim."""
    from .drive_utils import get_ai_supported_mime as drive_mime
    return drive_mime(mime_type, filename)
