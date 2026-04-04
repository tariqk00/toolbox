"""
AI Abstraction Layer.
Handles interactions with Gemini via `google-genai` SDK, including Prompting, JSON parsing, and Caching.
"""
import os
import json
import logging
import io
import re
from google import genai
from google.genai import types

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

def load_api_key():
    # 1. Try environment variable
    env_key = os.getenv('GEMINI_API_KEY')
    if env_key:
        return env_key
        
    # 2. Try file fallback
    try:
        if os.path.exists(SECRET_PATH):
            with open(SECRET_PATH, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"Error reading {SECRET_PATH}: {e}")
        
    return None

GEMINI_API_KEY = load_api_key()

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
    if 'vnd.google-apps.spreadsheet' in mime_type: return 'application/pdf'
    
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

def analyze_with_gemini(content_bytes, mime_type, filename, folder_paths_str, context_hint="", file_id=None):
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
        }

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
        }

    # --- CACHE CHECK ---
    if file_id:
        cache_key = file_id
        if cache_key in GEMINI_CACHE:
            return GEMINI_CACHE[cache_key]

    # --- PLAUD / MM-DD HEURISTIC ---
    if re.match(r'^\d{2}-\d{2}\s', filename):
        logger.info(f"  [Rule] Detected Plaud/Journal pattern: {filename}")
        return {
            "doc_date": "2026-" + filename[:5],
            "entity": "Plaud_Note",
            "folder_path": "01 - Second Brain/Plaud",
            "summary": filename,
            "confidence": "High"
        }

    ai_mime = get_ai_supported_mime(mime_type, filename)
    
    if not ai_mime:
        logger.warning(f"  [Skip] Unsupported file type for AI: {filename} ({mime_type})")
        return {
            "doc_date": "0000-00-00",
            "entity": "Unknown",
            "folder_path": None,
            "summary": "Unsupported_Format",
            "confidence": "Low"
        }

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    logger.info(f"  Sending to Gemini as {ai_mime} (Original: {mime_type})...")
    
    # Size limit for text content
    if ai_mime == 'text/plain' and len(content_bytes) > 1024 * 100:
        logger.info(f"  [Info] Truncating large text file ({len(content_bytes)} bytes) to 100KB.")
        content_bytes = content_bytes[:1024 * 100]
    
    # Inject context
    prompt_with_context = SYSTEM_PROMPT.format(
        context_hint=context_hint,
        folder_paths=folder_paths_str
    )
    
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                prompt_with_context,
                types.Part.from_bytes(data=content_bytes, mime_type=ai_mime)
            ]
        )

        usage = response.usage_metadata
        if usage:
            logger.info(
                f"  [Tokens] in={usage.prompt_token_count} "
                f"out={usage.candidates_token_count} "
                f"total={usage.total_token_count}"
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
                
            return data

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
                    return data
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
        }
