"""
Gemini interface wrapper.
Now redirects to lib/ai_engine.py for centralized provider management.
"""
import logging
from . import ai_engine

logger = logging.getLogger('toolbox.gemini')

def call_gemini(prompt: str) -> str:
    """Redirect to ai_engine.call specifically requesting Gemini if needed, 
    but currently uses the standard provider chain."""
    return ai_engine.call(prompt)
