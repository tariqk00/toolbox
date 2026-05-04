"""
Gemini interface wrapper.
DEPRECATED: Use toolbox.lib.llm_gateway instead.
This module is now a shim for LLMGateway.
"""
import logging
import warnings
from .llm_gateway import call_llm

logger = logging.getLogger('toolbox.gemini')

def call_gemini(prompt: str) -> str:
    """Redirect to LLMGateway.call with 'automation' task type."""
    warnings.warn("toolbox.lib.gemini.call_gemini is deprecated. Use toolbox.lib.llm_gateway.call_llm instead.", DeprecationWarning, stacklevel=2)
    logger.warning("Legacy Gemini call detected (redirecting to gateway)")
    res = call_llm(task_type='automation', prompt=prompt)
    return res.get('text', '')

