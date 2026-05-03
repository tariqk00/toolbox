"""
Unified LLM interface wrapper.
Now redirects to lib/ai_engine.py for centralized provider management.
"""
import logging
from . import ai_engine

logger = logging.getLogger('toolbox.llm')

def call(prompt: str, max_tokens: int = 500) -> str:
    """Redirect to ai_engine.call"""
    return ai_engine.call(prompt, max_tokens=max_tokens)

def call_json(prompt: str, max_tokens: int = 500) -> dict:
    """Redirect to ai_engine.call_json"""
    return ai_engine.call_json(prompt)
