"""
Unified LLM interface wrapper.
DEPRECATED: Use toolbox.lib.llm_gateway instead.
This module is now a shim for LLMGateway.
"""
import logging
import warnings
from .llm_gateway import call_llm, _parse_json

logger = logging.getLogger('toolbox.llm')

def call(prompt: str, max_tokens: int = 500) -> str:
    """Redirect to LLMGateway.call with 'automation' task type."""
    warnings.warn("toolbox.lib.llm.call is deprecated. Use toolbox.lib.llm_gateway.call_llm instead.", DeprecationWarning, stacklevel=2)
    logger.warning("Legacy LLM call detected (redirecting to gateway)")
    res = call_llm(task_type='automation', prompt=prompt)
    return res.get('text', '')

def call_json(prompt: str, max_tokens: int = 500) -> dict:
    """Redirect to LLMGateway.call with 'automation' task type and parse JSON."""
    warnings.warn("toolbox.lib.llm.call_json is deprecated. Use toolbox.lib.llm_gateway.call_llm instead.", DeprecationWarning, stacklevel=2)
    logger.warning("Legacy LLM JSON call detected (redirecting to gateway)")
    raw = call(prompt, max_tokens=max_tokens)
    if not raw:
        return {}
    return _parse_json(raw)
