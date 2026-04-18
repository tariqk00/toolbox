"""
Shared Gemini helper for the email extraction pipeline.

Tries the free tier (gemini-2.5-flash-lite) first; falls back to paid
(gemini-2.0-flash) if the daily RPD quota is exhausted.

Usage:
    from toolbox.lib.gemini import call_gemini
    text = call_gemini(prompt)   # returns raw text, or '' on failure
"""
import logging
import os

logger = logging.getLogger('toolbox.gemini')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')

FREE_SECRET_PATH = os.path.join(CONFIG_DIR, 'gemini_ai_studio_secret')
PAID_SECRET_PATH = os.path.join(CONFIG_DIR, 'gemini_secret')

FREE_MODEL = os.getenv('GEMINI_FREE_MODEL', 'gemini-2.5-flash-lite')
PAID_MODEL = os.getenv('GEMINI_PAID_MODEL', 'gemini-2.0-flash')

# Lazy singletons
_free_client = None
_paid_client = None


def _load_key(path: str) -> str | None:
    try:
        if os.path.exists(path):
            return open(path).read().strip() or None
    except Exception:
        pass
    return None


def _get_free_client():
    global _free_client
    if _free_client is None:
        key = _load_key(FREE_SECRET_PATH)
        if not key:
            raise ValueError(f'Free-tier Gemini key not found at {FREE_SECRET_PATH}')
        from google import genai
        _free_client = genai.Client(api_key=key)
    return _free_client


def _get_paid_client():
    global _paid_client
    if _paid_client is None:
        key = _load_key(PAID_SECRET_PATH)
        if not key:
            raise ValueError(f'Paid Gemini key not found at {PAID_SECRET_PATH}')
        from google import genai
        _paid_client = genai.Client(api_key=key)
    return _paid_client


def call_gemini(prompt: str) -> str:
    """
    Call Gemini with prompt. Tries free tier first; falls back to paid if
    free-tier RPD is exhausted. Returns raw response text, or '' on failure.
    """
    from toolbox.lib import quota_manager

    if not quota_manager.is_rpd_exhausted():
        try:
            client = _get_free_client()
            response = client.models.generate_content(
                model=FREE_MODEL,
                contents=prompt,
            )
            quota_manager.record_call()
            logger.debug(f'Gemini call: free/{FREE_MODEL}')
            return response.text.strip()
        except Exception as e:
            err = str(e).upper()
            if 'RESOURCE_EXHAUSTED' in err or '429' in err:
                logger.warning(f'Free-tier quota hit mid-run; falling back to paid tier')
                quota_manager.record_call()  # mark exhausted so future calls skip free
            else:
                logger.error(f'Free-tier Gemini call failed: {e}')
                return ''

    # Paid fallback
    try:
        client = _get_paid_client()
        response = client.models.generate_content(
            model=PAID_MODEL,
            contents=prompt,
        )
        logger.debug(f'Gemini call: paid/{PAID_MODEL}')
        return response.text.strip()
    except ValueError as e:
        # Key not configured yet
        logger.warning(f'Paid Gemini key not available, skipping: {e}')
        return ''
    except Exception as e:
        logger.error(f'Paid-tier Gemini call failed: {e}')
        return ''
