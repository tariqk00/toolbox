"""
Unified LLM interface for all toolbox services.
Provider: Groq (llama-3.3-70b-versatile) — text only.
For vision/PDF tasks, use lib/ai_engine.py directly.

Usage:
    from toolbox.lib.llm import call, call_json

    text = call(prompt)
    data = call_json(prompt)   # returns {} on parse failure
"""
import json
import logging
import re

logger = logging.getLogger('toolbox.llm')


def call(prompt: str, max_tokens: int = 500) -> str:
    """Send a prompt to Groq and return the raw text response, or '' on failure."""
    try:
        from toolbox.lib.providers.groq import _get_client, GROQ_MODEL
        client = _get_client()
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or '').strip()
        tokens = resp.usage.total_tokens if resp.usage else 0
        logger.debug(f'[Groq/{GROQ_MODEL}] tokens={tokens}')
        return text
    except Exception as e:
        logger.error(f'Groq call failed: {e}')
        return ''


def call_json(prompt: str, max_tokens: int = 500) -> dict:
    """Send a prompt to Groq and parse the JSON response. Returns {} on any failure."""
    raw = call(prompt, max_tokens=max_tokens)
    if not raw:
        return {}
    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        logger.error(f'Groq JSON parse failed: {e} — raw: {raw[:200]}')
        return {}
