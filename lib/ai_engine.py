"""
AI Abstraction Layer.
Handles interactions with Gemini via `google-genai` SDK, including Prompting, JSON parsing, and Caching.
"""
import os
import json
import logging
import io
import re
import random
import time
import requests
from datetime import datetime
from google import genai
from google.genai import types
from toolbox.lib import telegram

try:
    from PIL import Image as _PILImage
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False

# --- LOGGING SETUP ---
logger = logging.getLogger("DriveSorter.AI")

# --- CONFIG ---
# This file is in toolbox/lib/ai_engine.py
# Root is toolbox/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
SECRET_PATH = os.path.join(CONFIG_DIR, 'gemini_secret')
CACHE_PATH = os.path.join(CONFIG_DIR, 'gemini_cache.json')

# Default model — use gemini-flash-latest to always track the current Flash release.
# Override via GEMINI_MODEL env var if needed.
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-flash-latest')

# --- SHADOW MODEL CONFIG ---
OLLAMA_URL = "http://localhost:11434/api/generate"
SHADOW_MODEL = "gemma4:e2b"
SHADOW_SAMPLE_RATE = 0.20 # 20%
COMPARISON_LOG_PATH = os.path.join(BASE_DIR, 'logs', 'model_comparison.jsonl')
# Free tier model — AI Studio project, 15 RPM / 1,000 RPD
GEMINI_FREE_MODEL = os.getenv('GEMINI_FREE_MODEL', 'gemini-2.5-flash-lite')

FREE_SECRET_PATH = os.path.join(CONFIG_DIR, 'gemini_ai_studio_secret')
# Min seconds between free-tier calls: 15 RPM = 1 per 4s
_FREE_TIER_MIN_INTERVAL = 4.0
_last_free_call_time: float = 0.0


def _load_key(env_var: str, file_path: str):
    val = os.getenv(env_var)
    if val:
        return val
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
    return None


GEMINI_API_KEY = _load_key('GEMINI_API_KEY', SECRET_PATH)
GEMINI_FREE_API_KEY = _load_key('GEMINI_FREE_API_KEY', FREE_SECRET_PATH)

# Lazy singletons
_client = None
_free_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _get_free_client():
    global _free_client
    if _free_client is None:
        if not GEMINI_FREE_API_KEY:
            raise ValueError("Free-tier Gemini API key missing (GEMINI_FREE_API_KEY or config/gemini_ai_studio_secret)")
        _free_client = genai.Client(api_key=GEMINI_FREE_API_KEY)
    return _free_client


def _rate_limit_free_tier():
    """Sleep if needed to stay under 15 RPM."""
    global _last_free_call_time
    elapsed = time.monotonic() - _last_free_call_time
    if elapsed < _FREE_TIER_MIN_INTERVAL:
        time.sleep(_FREE_TIER_MIN_INTERVAL - elapsed)
    _last_free_call_time = time.monotonic()


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).upper()
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg


def _is_daily_limit_error(e: Exception) -> bool:
    """Distinguish per-day quota exhaustion from per-minute rate limits."""
    msg = str(e).upper()
    return _is_rate_limit_error(e) and ("PER_DAY" in msg or "DAILY" in msg or "DAY" in msg)


def _is_invalid_pdf_error(e: Exception) -> bool:
    """Detect corrupt/empty PDFs (often caused by raw byte truncation)."""
    msg = str(e).upper()
    return "NO PAGES" in msg or ("INVALID_ARGUMENT" in msg and "400" in msg and "PAGES" in msg)

# --- CACHE LOGIC ---
GEMINI_CACHE = {}

def load_cache():
    global GEMINI_CACHE
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r') as f:
                GEMINI_CACHE = json.load(f)
            logger.info(f"Loaded {len(GEMINI_CACHE)} entries from cache.")
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            GEMINI_CACHE = {}

def save_cache():
    try:
        with open(CACHE_PATH, 'w') as f:
            json.dump(GEMINI_CACHE, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving cache: {e}")

# Load cache on module import
load_cache()


# --- PROMPT ---
SYSTEM_PROMPT = """
You are a highly capable Personal Document Assistant. Your goal is to analyze the provided content (image or text) and categorize it for a long-term digital archive.

CONTEXT: {context_hint}

EXTRACT the following fields into a pure JSON object:
- "doc_date": Use YYYY-MM-DD format. For travel documents (flights, hotels, car rentals, reservations), use the trip/travel/check-in date, NOT the booking or email date. For all other documents, use the actual document date. If not found, use the creation date provided in context or '0000-00-00'.
- "entity": The primary organization, person, or vendor.
    - CRITICAL: For bank statements or transaction lists, the entity MUST be the Institution (e.g., "Chase", "Verizon").
    - CRITICAL: Do NOT pick a merchant from a random row in a spreadsheet as the entity.
- "folder_path": Choose the most appropriate destination from this folder list:
{folder_paths}
Return the exact path string. Use the most specific subfolder that fits.
- "summary": A concise 3-5 word description (e.g., "Monthly Internet Bill", "Property Tax Assessment").
- "reasoning": A brief 1-sentence explanation of why you chose this folder/entity.
- "confidence": "High", "Medium", or "Low".

- "person": If this document is specifically for Dawn, Thomas, or Sofia, return their first name. Otherwise return null.

RULES:
1. Pure JSON only. No markdown formatting.
2. If "confidence" is Medium or Low, explain why in "reasoning".
3. For medical docs, choose the Health folder.
4. For ID cards/passports, choose the Personal ID folder.
5. For generic transcripts/logs not matching other rules, choose the Archive Source_Dumps folder.
"""

def get_ai_supported_mime(mime_type, filename=None):
    """Returns a Gemini-supported MIME type or None if unsupported."""
    
    # 1. Direct PDF/Image support
    if 'pdf' in mime_type: return 'application/pdf'
    if 'image' in mime_type: return 'image/jpeg' 
    
    # 2. Google Apps (exported by drive_utils)
    if 'vnd.google-apps.document' in mime_type: return 'text/plain'
    if 'vnd.google-apps.spreadsheet' in mime_type: return 'text/plain'
    
    # 3. Known Text types
    supported_text = ['text/plain', 'text/csv', 'text/markdown', 'text/html', 'application/json']
    if any(st in mime_type for st in supported_text):
        return 'text/plain'
        
    # 4. Handle octet-stream/unknown via extension
    if mime_type == 'application/octet-stream' or '/' not in mime_type:
        ext = os.path.splitext(filename or "")[1].lower()
        if ext in ['.txt', '.csv', '.md', '.log']:
            return 'text/plain'
            
    return None

def call_ollama(prompt, content_bytes=None, mime_type=None):
    """Calls the local Ollama instance on the NUC."""
    payload = {
        "model": SHADOW_MODEL,
        "prompt": prompt,
        "stream": False
    }
    
    # If we have text content, append it to the prompt
    if content_bytes and mime_type == 'text/plain':
        try:
           text_content = content_bytes.decode('utf-8', errors='ignore')
           payload["prompt"] = f"{prompt}\n\nCONTENT TO ANALYZE:\n{text_content}"
        except Exception:
            pass

    try:
        start = time.time()
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        duration = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            return data.get("response", "").strip(), duration
        return f"Error: Ollama status {response.status_code}", duration
    except Exception as e:
        return f"Error: {str(e)}", 0

def log_comparison(filename, gemini_data, gemma_text, gemini_duration, gemma_duration):
    """Logs the comparison between Gemini and Gemma."""
    os.makedirs(os.path.dirname(COMPARISON_LOG_PATH), exist_ok=True)
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "filename": filename,
        "gemini": {
            "result": gemini_data,
            "latency": round(gemini_duration, 2)
        },
        "gemma": {
            "result": gemma_text,
            "latency": round(gemma_duration, 2)
        }
    }
    
    try:
        with open(COMPARISON_LOG_PATH, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")
            
        # Send Telegram notification
        summary = gemini_data.get('summary', 'No summary')
        gemini_conf = gemini_data.get('confidence', 'N/A')
        
        msg = (
            f"🤖 *Shadow AI Comparison*\n"
            f"📄 `{filename}`\n\n"
            f"🔹 *Gemini (Flash):* {gemini_conf} - {summary}\n"
            f"🔸 *Gemma (2B):* {gemma_text[:150]}...\n\n"
            f"⏱ Gemini: {round(gemini_duration,1)}s | Gemma: {round(gemma_duration,1)}s"
        )
        telegram.send_message(msg, service="shadow-ai", parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Failed to log comparison: {e}")

def analyze_with_gemini(content_bytes, mime_type, filename, folder_paths_str, context_hint="", file_id=None, use_free_tier=False):
    """
    Sends content to Gemini for analysis using the google.genai SDK.
    """
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key missing")

    # --- GENERIC PLAUD EXPORTS ---
    if filename.lower().endswith('summary.txt') or filename.lower().endswith('transcript.txt'):
        logger.info(f"  [Rule] Detected Generic Plaud Export: {filename}")
        base_name = os.path.splitext(filename)[0]
        folder = "01 - Second Brain/Plaud/Transcripts" if filename.lower().endswith('transcript.txt') else "01 - Second Brain/Plaud"
        return {
            "doc_date": "2026-01-01",
            "entity": "Plaud_Export",
            "folder_path": folder,
            "summary": base_name,
            "confidence": "High"
        }, 0

    # --- GEMINI JOURNAL RULE ---
    if " - Journal - " in filename:
        logger.info(f"  [Rule] Detected Gemini Journal: {filename}")
        parts = filename.split(" - ")
        if len(parts) >= 3:
            doc_date = parts[0]
            summary = os.path.splitext(parts[2])[0]
        else:
            doc_date = "0000-00-00"
            summary = filename

        return {
            "doc_date": doc_date,
            "entity": "Journal",
            "folder_path": "01 - Second Brain/Gemini",
            "summary": summary,
            "confidence": "High"
        }, 0

    # --- CACHE CHECK ---
    if file_id:
        cache_key = file_id
        if cache_key in GEMINI_CACHE:
            return GEMINI_CACHE[cache_key], 0

    # --- PLAUD / MM-DD HEURISTIC ---
    if re.match(r'^\d{2}-\d{2}\s', filename):
        logger.info(f"  [Rule] Detected Plaud/Journal pattern: {filename}")
        return {
            "doc_date": "2026-" + filename[:5],
            "entity": "Plaud_Note",
            "folder_path": "01 - Second Brain/Plaud",
            "summary": filename,
            "confidence": "High"
        }, 0

    ai_mime = get_ai_supported_mime(mime_type, filename)
    
    if not ai_mime:
        logger.warning(f"  [Skip] Unsupported file type for AI: {filename} ({mime_type})")
        return {
            "doc_date": "0000-00-00",
            "entity": "Unknown",
            "folder_path": None,
            "summary": "Unsupported_Format",
            "confidence": "Low"
        }, 0

    if use_free_tier:
        from toolbox.lib import quota_manager as _qm
        if _qm.is_rpd_exhausted():
            logger.warning(f"  [RPD] Daily free-tier request limit reached. Skipping {filename}.")
            return {"doc_date": "0000-00-00", "entity": "Unknown", "folder_path": None,
                    "summary": "RPD_Exhausted", "confidence": "Low"}, 0

    # Size limits before sending
    if ai_mime == 'text/plain' and len(content_bytes) > 1024 * 10:
        logger.info(f"  [Info] Truncating text ({len(content_bytes):,} bytes) to 10KB.")
        content_bytes = content_bytes[:1024 * 10]
    original_pdf_bytes = None
    if ai_mime == 'application/pdf' and len(content_bytes) > 200 * 1024:
        logger.info(f"  [Info] Truncating PDF ({len(content_bytes):,} bytes) to 200KB.")
        original_pdf_bytes = content_bytes
        content_bytes = content_bytes[:200 * 1024]
    if ai_mime == 'image/jpeg':
        if _PILLOW_AVAILABLE:
            try:
                orig_size = len(content_bytes)
                img = _PILImage.open(io.BytesIO(content_bytes))
                img.thumbnail((1024, 1024))
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=75)
                content_bytes = buf.getvalue()
                logger.info(f"  [Resize] Image {orig_size:,} → {len(content_bytes):,} bytes")
            except Exception as e:
                logger.warning(f"  [Resize] Failed ({e}); sending original")
        else:
            logger.debug("  [Resize] Pillow not available; sending image at original size")

    if use_free_tier:
        model_name = GEMINI_FREE_MODEL
        logger.info(f"  Sending to Gemini (free/{model_name}) as {ai_mime} ({len(content_bytes):,} bytes)...")
    else:
        model_name = GEMINI_MODEL
        logger.info(f"  Sending to Gemini (paid/{model_name}) as {ai_mime} ({len(content_bytes):,} bytes)...")

    # Inject context
    prompt_with_context = SYSTEM_PROMPT.format(
        context_hint=context_hint,
        folder_paths=folder_paths_str
    )

    _RETRY_DELAYS = [4, 16, 64]

    def _call_api():
        if use_free_tier:
            _rate_limit_free_tier()
            client = _get_free_client()
        else:
            client = _get_client()
        return client.models.generate_content(
            model=model_name,
            contents=[
                prompt_with_context,
                types.Part.from_bytes(data=content_bytes, mime_type=ai_mime)
            ],
            config=types.GenerateContentConfig(max_output_tokens=512)
        )

    try:
        start_gemini = time.time()
        response = None
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                logger.warning(f"  [429] Rate limited. Retrying in {delay}s (attempt {attempt+1}/3)...")
                time.sleep(delay)
            try:
                response = _call_api()
                if use_free_tier:
                    from toolbox.lib import quota_manager as _qm
                    _qm.record_call()
                break
            except Exception as api_err:
                if _is_daily_limit_error(api_err):
                    logger.error(f"  [RPD] Daily free-tier quota exhausted by API. Skipping.")
                    return {"doc_date": "0000-00-00", "entity": "Unknown", "folder_path": None,
                            "summary": "RPD_Exhausted", "confidence": "Low"}, 0
                if _is_invalid_pdf_error(api_err):
                    if original_pdf_bytes is not None:
                        logger.warning(f"  [PDF] Truncated PDF invalid (no pages); retrying with full file ({len(original_pdf_bytes):,} bytes)...")
                        content_bytes = original_pdf_bytes
                        original_pdf_bytes = None
                        try:
                            response = _call_api()
                            if use_free_tier:
                                from toolbox.lib import quota_manager as _qm
                                _qm.record_call()
                            break
                        except Exception:
                            pass
                    logger.warning(f"  [PDF] Invalid/empty PDF: {filename}. Caching to skip future retries.")
                    result = {"doc_date": "0000-00-00", "entity": "Unknown", "folder_path": None,
                              "summary": "Invalid_PDF", "confidence": "Low"}
                    if file_id:
                        GEMINI_CACHE[file_id] = result
                        save_cache()
                    return result, 0
                if _is_rate_limit_error(api_err) and attempt < len(_RETRY_DELAYS):
                    continue
                raise

        if response is None:
            raise RuntimeError("All retry attempts exhausted (429)")
        
        gemini_duration = time.time() - start_gemini

        usage = response.usage_metadata
        token_count = 0
        if usage:
            token_count = usage.total_token_count or 0
            logger.info(
                f"  [Tokens] in={usage.prompt_token_count} "
                f"out={usage.candidates_token_count} "
                f"total={token_count} "
                f"bytes_sent={len(content_bytes):,}"
            )

        text = response.text.strip()
        
        # Robust JSON extraction
        try:
            start_idx = text.find('{')
            if start_idx == -1:
                raise ValueError("No JSON-like structure found")
            
            json_snippet = text[start_idx:]
            decoder = json.JSONDecoder()
            data, end_pos = decoder.raw_decode(json_snippet)
            
            if isinstance(data, str) and "```json" in data:
                 json_text = data.split("```json")[-1].split("```")[0].strip()
                 data = json.loads(json_text)

            if isinstance(data, list):
                if len(data) > 0:
                    data = data[0]
                else:
                    raise ValueError("Empty JSON list returned")
            
            # --- SAVE TO CACHE ---
            if file_id:
                GEMINI_CACHE[file_id] = data
                save_cache()
            
            # --- SHADOW AI PARALLEL CALL ---
            if random.random() < SHADOW_SAMPLE_RATE:
                logger.info(f"  [Shadow] Running parallel check for {filename}...")
                gemma_text, gemma_duration = call_ollama(prompt_with_context, content_bytes, ai_mime)
                log_comparison(filename, data, gemma_text, gemini_duration, gemma_duration)

            return data, token_count

        except json.JSONDecodeError:
             # Fallback: legacy regex extraction
             start_idx = text.find('{')
             end_idx = text.rfind('}')

             if start_idx != -1 and end_idx != -1:
                json_text = text[start_idx:end_idx+1]
                try:
                    data = json.loads(json_text)
                    if file_id:
                         GEMINI_CACHE[file_id] = data
                         save_cache()
                    return data, token_count
                except json.JSONDecodeError as je:
                     logger.error(f"    [JSON Error] Raw text: {text}")
                     raise je
             else:
                  logger.error(f"    [No JSON] Raw text: {text}")
                  raise ValueError("No JSON found in response")

    except Exception as e:
        logger.error(f"Gemini Error during analysis: {e}", exc_info=True)
        return {
            "doc_date": "0000-00-00",
            "entity": "Unknown",
            "folder_path": None,
            "summary": "AI_Error",
            "confidence": "Low"
        }, 0
