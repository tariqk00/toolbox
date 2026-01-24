"""
AI Abstraction Layer.
Handles interactions with Gemini (1.5 Flash) via `google-genai` SDK, including Prompting, JSON parsing, and Caching.
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
# --- CONFIG ---
# This file is in toolbox/core/ai.py
# Root is toolbox/ 
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
CONFIG_DIR = os.path.join(BASE_DIR, 'config') 
SECRET_PATH = os.path.join(CONFIG_DIR, 'gemini_secret')
CACHE_PATH = os.path.join(CONFIG_DIR, 'gemini_cache.json')
RECOMMENDATIONS_PATH = os.path.join(CONFIG_DIR, 'category_recommendations.json')

def load_api_key():
    try:
        with open(SECRET_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error(f"Error: Gemini API Key not found in {SECRET_PATH}")
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

def save_recommendation(category_path):
    """Logs a recommended category path that doesn't have a specific folder yet."""
    try:
        recommendations = {}
        if os.path.exists(RECOMMENDATIONS_PATH):
            with open(RECOMMENDATIONS_PATH, 'r') as f:
                recommendations = json.load(f)
        
        recommendations[category_path] = recommendations.get(category_path, 0) + 1
        
        with open(RECOMMENDATIONS_PATH, 'w') as f:
            json.dump(recommendations, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving recommendation: {e}")

# --- PROMPT ---
SYSTEM_PROMPT = """
You are a personal file assistant. Analyze the image or document provided.
CONTEXT: {context_hint}

Extract the following fields into a pure JSON object (no markdown formatting):
{{
  "doc_date": "YYYY-MM-DD",
  "entity": "Name of Vendor/Person/Organization",
  "category": "One of {categories}",
  "summary": "Very short 3-5 word description",
  "confidence": "High/Medium/Low"
}}

Rules:
- Be as specific as possible with the category (e.g. use 'Finance/Receipts' instead of just 'Finance' if appropriate).
- If the file is a bank activity CSV, credit card statement, or multi-transaction spreadsheet, the "entity" MUST be the Bank or Institution name (e.g., "Chase", "Amex", "Capital One"). Do NOT pick a merchant from a random row as the entity.
- Categorize bank activity/statements as "Finance/Statements".
- If date is ambiguous, use the creation date or null.
- "entity" should be clean (e.g. "Home Depot", not "THE HOME DEPOT INC").
- "summary" should be specific (e.g. "Paint Supplies", not "Shopping").
- Use category "Source_Material" for raw transcripts or logs.
- Use category "PKM" for notes, journals, or summaries.
"""

def get_ai_supported_mime(mime_type, filename=None):
    """Returns a Gemini-supported MIME type or None if unsupported."""
    
    # 1. Direct PDF/Image support
    if 'pdf' in mime_type: return 'application/pdf'
    if 'image' in mime_type: return 'image/jpeg' 
    
    # 2. Known Text types
    supported_text = ['text/plain', 'text/csv', 'text/markdown', 'text/html', 'application/json']
    if any(st in mime_type for st in supported_text):
        return 'text/plain'
        
    # 3. Handle octet-stream/unknown via extension
    if mime_type == 'application/octet-stream' or '/' not in mime_type:
        ext = os.path.splitext(filename or "")[1].lower()
        if ext in ['.txt', '.csv', '.md', '.log']:
            return 'text/plain'
            
    return None

def analyze_with_gemini(content_bytes, mime_type, filename, category_list_str, context_hint="", file_id=None):
    """
    Sends content to Gemini-1.5-Flash for analysis using the new google.genai SDK.
    """
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key missing")

    # --- GENERIC PLAUD EXPORTS ---
    if filename.lower().endswith('summary.txt') or filename.lower().endswith('transcript.txt'):
        logger.info(f"  [Rule] Detected Generic Plaud Export: {filename}")
        target_category = "PKM/Plaud"
        if filename.lower().endswith('transcript.txt'):
            target_category = "PKM/Plaud/Transcripts"
        base_name = os.path.splitext(filename)[0]
        return {
            "doc_date": "2026-01-01", 
            "entity": "Plaud_Export",
            "category": target_category, 
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
            "category": "PKM/Gemini",
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
            "category": "PKM/Plaud",
            "summary": filename,
            "confidence": "High"
        }

    ai_mime = get_ai_supported_mime(mime_type, filename)
    
    if not ai_mime:
        logger.warning(f"  [Skip] Unsupported file type for AI: {filename} ({mime_type})")
        return {
            "doc_date": "0000-00-00",
            "entity": "Unknown", 
            "category": "Other", 
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
        categories=category_list_str
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[
                prompt_with_context,
                types.Part.from_bytes(data=content_bytes, mime_type=ai_mime)
            ]
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
            "category": "Uncategorized", 
            "summary": "AI_Error",
            "confidence": "Low"
        }
