import os
import time
import json
import csv
import argparse
import sys
import re
import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io
import logging
from logging.handlers import RotatingFileHandler
from google import genai
from google.genai import types

__version__ = "0.4.2"

# --- CONFIG ---
TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token_full_drive.json')
SECRET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gemini_secret')
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

# --- CONFIG & MAPPINGS ---
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'folder_config.json')
RECOMMENDATIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'category_recommendations.json')

def load_folder_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading folder_config.json: {e}")
    return {"mappings": {}}

FOLDER_CONFIG = load_folder_config()

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
        print(f"Error saving recommendation: {e}")

def get_category_list():
    """Builds a flat list of categories and sub-categories for the AI prompt."""
    categories = []
    mappings = FOLDER_CONFIG.get('mappings', {})
    for parent, data in mappings.items():
        categories.append(parent)
        subcats = data.get('subcategories', {})
        for sub in subcats.keys():
            categories.append(f"{parent}/{sub}")
    return sorted(list(set(categories + ["Other"])))

def get_category_prompt_str():
    """Returns categories as a clean comma-separated string."""
    return ", ".join(get_category_list())

def resolve_folder_id(category_str):
    """Resolves a category string (e.g. 'Finance/Receipts') to a folder ID."""
    mappings = FOLDER_CONFIG.get('mappings', {})
    
    # Handle Finance/Receipts format
    parts = [p.strip() for p in category_str.split('/')]
    parent_name = parts[0]
    sub_name = parts[1] if len(parts) > 1 else None
    
    parent_data = mappings.get(parent_name)
    if not parent_data:
        # Check for legacy flat mapping if logic evolved
        return None
    
    parent_id = parent_data.get('id')
    
    if sub_name:
        sub_id = parent_data.get('subcategories', {}).get(sub_name)
        if sub_id:
            return sub_id
        else:
            # Subcategory not found, log recommendation and fallback to parent
            full_path = f"{parent_name}/{sub_name}"
            save_recommendation(full_path)
            return parent_id
            
    return parent_id

INBOX_ID = '1c-7Wv9J-FPpc3tph7Ax1xx5bMI-5jcaG'

METADATA_FOLDER_ID = '1kwJ59bxRgYJgtv1c3sO-hhrvfIeD0JW0'
HISTORY_SHEET_ID = '1N8xlrcCnj97uGPssXnGg_-1t2SvGZlnocc_7BNO28dY'

# --- LOGGING SETUP ---
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'sorter.log')

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

class RunStats:
    def __init__(self):
        self.processed = 0
        self.moved = 0
        self.renamed = 0
        self.errors = 0
        self.start_time = time.time()

    def get_summary(self):
        duration = int(time.time() - self.start_time)
        if self.processed == 0 and self.errors == 0:
            return f"Run completed in {duration}s. No files found to process."
        return f"Run completed in {duration}s. Processed: {self.processed}, Moved: {self.moved}, Renamed: {self.renamed}, Errors: {self.errors}."

stats = RunStats()
logger = logging.getLogger("DriveSorter")
logger.setLevel(logging.INFO)

# Console Handler
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(ch)

# Rotating File Handler
fh = RotatingFileHandler(LOG_FILE, maxBytes=1*1024*1024, backupCount=5)
fh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
logger.addHandler(fh)

def sync_logs_to_drive():
    """Uploads the local sorter.log to the Metadata/Logs folder on Drive."""
    try:
        service = get_drive_service()
        
        # 1. Find/Create 'Logs' folder in Metadata folder
        query = f"name = 'Logs' and '{METADATA_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])
        
        if files:
            logs_folder_id = files[0]['id']
        else:
            file_metadata = {
                'name': 'Logs',
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [METADATA_FOLDER_ID]
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            logs_folder_id = folder.get('id')
            logger.info(f"Created 'Logs' folder in Metadata (ID: {logs_folder_id})")

        # 2. Find/Update 'sorter.log' in Logs folder
        log_query = f"name = 'sorter.log' and '{logs_folder_id}' in parents and trashed = false"
        log_results = service.files().list(q=log_query, fields="files(id)").execute()
        log_files = log_results.get('files', [])
        
        media = MediaFileUpload(LOG_FILE, mimetype='text/plain', resumable=True)
        
        if log_files:
            file_id = log_files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {
                'name': 'sorter.log',
                'parents': [logs_folder_id]
            }
            service.files().create(body=file_metadata, media_body=media).execute()
            
        logger.info("Successfully synced sorter.log to Google Drive.")
        
    except Exception as e:
        logger.error(f"Failed to sync logs to Drive: {e}")

def update_manifest():
    """Generates/Updates folder_manifest.md with current mappings and paths."""
    manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'folder_manifest.md')
    service = get_drive_service()
    
    lines = [
        "# Folder Manifest - AI Drive Sorter",
        "",
        "This manifest documents the current organization structure. It is used to refine the AI's filing logic and provides a clear view of where files will be placed.",
        "",
        "| Category | Type | Sub-Category | Full Drive Path | Folder ID |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]
    
    mappings = FOLDER_CONFIG.get('mappings', {})
    for parent, data in sorted(mappings.items()):
        parent_id = data.get('id')
        parent_path = get_folder_path(service, parent_id)
        lines.append(f"| **{parent}** | Parent | - | {parent_path} | `{parent_id}` |")
        
        subcats = data.get('subcategories', {})
        for sub, sub_id in sorted(subcats.items()):
            sub_path = get_folder_path(service, sub_id)
            lines.append(f"| | Child | {sub} | {sub_path} | `{sub_id}` |")
            
    lines.append("\n---\n*Last Updated: " + time.strftime("%Y-%m-%d %H:%M:%S") + "*")
    
    try:
        with open(manifest_path, 'w') as f:
            f.write("\n".join(lines))
        logger.info("Successfully updated folder_manifest.md.")
    except Exception as e:
        logger.error(f"Failed to update manifest: {e}")


def load_api_key():
    try:
        with open(SECRET_PATH, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Error: Gemini API Key not found in gemini_secret")
        return None

GEMINI_API_KEY = load_api_key()

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
- If date is ambiguous, use the creation date or null.
- "entity" should be clean (e.g. "Home Depot", not "THE HOME DEPOT INC").
- "summary" should be specific (e.g. "Paint Supplies", not "Shopping").
- Use category "Source_Material" for raw transcripts or logs.
- Use category "PKM" for notes, journals, or summaries.
"""

def get_folder_path(service, folder_id):
    """Resolve full path from ID using FOLDER_MAP and API. Returns 'Folder / Subfolder'."""
    
    # Check Static Map first (Fastest) for Top-Level
    # REMOVED: We want the REAL folder name (e.g. "03 - Finance"), not the Map Key ("Finance")
    # for name, fid in FOLDER_MAP.items():
    #     if fid == folder_id:
    #          return name
             
    if not folder_id or folder_id in ["None", "Unknown", "Inbox/Unknown"]:
        return "Unknown"

    path_parts = []
    current_id = folder_id
    
    # Walk up the tree (Max depth 3 to be safe)
    for _ in range(5): 
        if not current_id: break
        
        # Check cache/map at this level
        # REMOVED: Force API Name
        # found_in_map = False
        # for name, fid in FOLDER_MAP.items():
        #     if fid == current_id:
        #         path_parts.insert(0, name)
        #         # Map entries are usually top-level anchors, so we can stop? 
        #         # Or continue if user wants "My Drive / Finance"? 
        #         # Assuming Map keys are sufficient "Roots".
        #         found_in_map = True
        #         break
        
        # if found_in_map:
        #     break
            
        try:
             res = service.files().get(fileId=current_id, fields="name, parents").execute()
             name = res.get('name', 'Unknown')
             path_parts.insert(0, name)
             
             parents = res.get('parents')
             current_id = parents[0] if parents else None
        except Exception as e:
             # print(f"Warning resolving path for {current_id}: {e}")
             break
             
    if not path_parts:
        return "Unknown Folder"
        
    return " / ".join(path_parts)

def log_to_sheet(timestamp, file_id, original_name, new_name, target_folder_id, target_folder_name, run_type):
    """Logs a single row to the History Google Sheet using HYPERLINK formulas."""
    
    if not HISTORY_SHEET_ID:
        print("  [Log Warning] No HISTORY_SHEET_ID configured.")
        return

    # Construct Hyperlinks
    # Escape quotes for formula safety (Excel/Sheets uses double quotes to escape quotes)
    safe_new_name = new_name.replace('"', '""')
    
    # New Name -> File Link
    link_file = f'=HYPERLINK("https://drive.google.com/open?id={file_id}", "{safe_new_name}")'
    
    # Target Folder -> Folder Link
    # Only link if we have a valid-looking ID (non-empty, not "None" or "Unknown")
    ignore_ids = ["None", "Unknown", "Inbox/Unknown"]
    
    safe_target_name = target_folder_name.replace('"', '""')

    if target_folder_id in ignore_ids or not target_folder_id:
         link_folder = target_folder_name
    else:
         link_folder = f'=HYPERLINK("https://drive.google.com/drive/u/0/folders/{target_folder_id}", "{safe_target_name}")'

    row_data = [timestamp, file_id, original_name, link_file, link_folder, run_type]

    try:
        service = get_sheets_service()
        body = {'values': [row_data]}
        service.spreadsheets().values().append(
            spreadsheetId=HISTORY_SHEET_ID, range="Log!A:A",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        # print(f"  [Log] Saved to History Sheet.")
    except Exception as e:
        print(f"  [Log Error] Failed to write to Sheet: {e}")
        # Fallback to local CSV if Sheet fails (plain text)
        with open('renaming_history_fallback.csv', 'a', newline='') as f:
             writer = csv.writer(f)
             writer.writerow([timestamp, file_id, original_name, new_name, target_folder_id, run_type])

def get_sheets_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return build('sheets', 'v4', credentials=creds)

def get_drive_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return build('drive', 'v3', credentials=creds)

def download_file_content(service, file_id, mime_type):
    """Downloads file content to memory for AI analysis"""
    print(f"  Downloading content for {file_id} ({mime_type})...")
    
    if mime_type.startswith('application/vnd.google-apps.'):
        # Export Google Docs/Sheets to text/PDF
        if 'document' in mime_type:
            request = service.files().export_media(fileId=file_id, mimeType='text/plain')
        elif 'spreadsheet' in mime_type:
            request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
        else:
            request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
    elif mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        # Attempt to export XLSX to PDF if Drive supports it (service-side)
        try:
            request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
        except:
            request = service.files().get_media(fileId=file_id)
    elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        try:
            request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
        except:
            request = service.files().get_media(fileId=file_id)
    else:
        # Download Binary / Text
        request = service.files().get_media(fileId=file_id)
        
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    return fh.getvalue()

def analyze_with_gemini(content_bytes, mime_type, filename, context_hint=""):
    """
    Sends content to Gemini-1.5-Flash for analysis using the new google.genai SDK.
    """
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key missing")
        
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
    
    # Inject context into prompt
    categories_str = get_category_prompt_str()
    prompt_with_context = SYSTEM_PROMPT.format(
        context_hint=context_hint,
        categories=categories_str
    )
    
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[
                prompt_with_context,
                types.Part.from_bytes(data=content_bytes, mime_type=ai_mime)
            ]
        )
        
        # Parse JSON from response
        text = response.text.strip()
        
        # Robust JSON extraction
        try:
             # Case 1: Wrapped in markdown code block
             if "```json" in text:
                 text = text.split("```json")[1].split("```")[0].strip()
             elif "```" in text:
                 text = text.split("```")[1].split("```")[0].strip()

             data = json.loads(text)
             
             # Handle List response (take first item)
             if isinstance(data, list):
                 if len(data) > 0:
                     return data[0]
                 else:
                     raise ValueError("Empty JSON list returned")
             return data

        except json.JSONDecodeError:
             # Fallback: legacy regex extraction
             start_idx = text.find('{')
             end_idx = text.rfind('}')
             
             if start_idx != -1 and end_idx != -1:
                json_text = text[start_idx:end_idx+1]
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError as je:
                     print(f"    [JSON Error] Raw text: {text}")
                     raise je
             else:
                  print(f"    [No JSON] Raw text: {text}")
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

def get_ai_supported_mime(mime_type, filename=None):
    """Returns a Gemini-supported MIME type or None if unsupported."""
    
    # 1. Direct PDF/Image support
    if 'pdf' in mime_type: return 'application/pdf'
    if 'image' in mime_type: return 'image/jpeg' # Gemini handles most common images as jpeg/png
    
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

def get_time_context(created_time_str):
    """
    Analyzes creation time (UTC string) to determine if it's likely Work or Personal.
    Rule: Work = Mon-Fri, 08:00 - 18:00 Local Time (Assuming UTC-5/EST roughly for now)
    """
    if not created_time_str:
        return ""
        
    try:
        # Parse RFC 3339 format e.g., 2023-10-27T10:00:00.000Z
        # We'll use a simple offset for EST (UTC-5) since standard libraries on NUC might vary
        # Ideally use pytz but sticking to stdlib if possible
        dt_utc = datetime.datetime.strptime(created_time_str[:19], "%Y-%m-%dT%H:%M:%S")
        
        # Adjust for EST (UTC-5) - Simplification without pytz
        dt_local = dt_utc - datetime.timedelta(hours=5)
        
        day_of_week = dt_local.weekday() # 0=Mon, 6=Sun
        hour = dt_local.hour
        
        is_weekday = 0 <= day_of_week <= 4
        is_work_hours = 8 <= hour < 18
        
        day_str = dt_local.strftime("%A")
        time_str = dt_local.strftime("%I:%M %p")
        
        if is_weekday and is_work_hours:
            return f"Time: {day_str} {time_str} (Work Hours)."
        else:
            return f"Time: {day_str} {time_str} (Likely Personal/After Hours)."
            
    except Exception as e:
        return ""

def generate_new_name(analysis, original_name, created_time_str):
    ext = os.path.splitext(original_name)[1]
    name_no_ext = os.path.splitext(original_name)[0]
    
    # 1. Content Date (from AI) - Default
    date = analysis.get('doc_date', '0000-00-00')
    if date is None: 
        date = '0000-00-00'

    # 2. Filename Date (Regex) - Priority if AI failed or matched "0000-00-00"
    if date == '0000-00-00':
        match = re.search(r'(\d{4}-\d{2}-\d{2})', original_name)
        if match:
            date = match.group(1)

    # 3. Created Date (Metadata) - Fallback
    if date == '0000-00-00' and created_time_str:
        date = created_time_str[:10]

    # SPECIAL HANDLING FOR AI ERRORS / UNSUPPORTED
    # Preserves history by keeping the original filename if AI fails
    summary = analysis.get('summary', 'Doc')
    if summary in ['AI_Error', 'Unsupported_Format']:
        # Strip existing date prefix if present to avoid "2024-01-01 - 2024-01-01 - filename"
        clean_oname = re.sub(r'^\d{4}-\d{2}-\d{2}\s*-\s*', '', name_no_ext).strip()
        # Strip any previously inserted error tags
        clean_oname = clean_oname.replace("Unknown - AI_Error", "").replace("Unknown - Unsupported_Format", "").strip("- ").strip()
        
        # If the original name was JUST the error name, we can't recover much, 
        # but for future runs this prevents truncation.
        if not clean_oname:
            clean_oname = "Unknown_File"
            
        return f"{date} - {clean_oname}{ext}"

    entity = analysis.get('entity', 'Unknown')
    summary = analysis.get('summary', 'Doc')
    
    # Cleanup strings
    safe_entity = "".join([c for c in entity if c.isalnum() or c in [' ', '_', '-']]).strip().replace(" ", "_")
    safe_summary = "".join([c for c in summary if c.isalnum() or c in [' ', '_', '-']]).strip().replace(" ", "_")
    
    # Last resort fallback not needed as created_time is robust
    if date == "0000-00-00" or not date:
         safe_summary = f"{safe_summary}_(NoDate)"
    
    return f"{date} - {safe_entity} - {safe_summary}{ext}"

def scan_folder(folder_id, dry_run=True, csv_path='sorter_dry_run.csv', limit=None, mode='scan', parent_context="Inbox"):
    service = get_drive_service()
    
    # Get actual folder name if just ID passed (rudimentary check)
    folder_context = parent_context
    if folder_id == INBOX_ID:
        folder_context = "Inbox"
    
    print(f"Scanning folder {folder_context} ({folder_id})...")
    
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, createdTime)"
    ).execute()
    files = results.get('files', [])
    
    # Initialize CSV if starting fresh
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='') as csvfile:
            fieldnames = ['id', 'original', 'proposed', 'category', 'confidence']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
    
    print(f"Found {len(files)} files in {folder_context}. Processing...")
    
    processed_count = 0
    for f in files:
        if limit and processed_count >= limit:
            print(f"Limit of {limit} reached. Stopping batch.")
            break

        name = f['name']
        fid = f['id']
        mime = f['mimeType']
        
        # Check if already processed (Regex: YYYY-MM-DD - Entity - Summary)
        # Matches: 2024-01-01 - Vendor - Desc.pdf
        # BUT: Do not skip if the date is 0000-00-00 (Failed Date)
        # UPDATE v0.3.3: Do not continue; falling through allows AI to categorize and MOVE the file.
        # Check if already processed (Regex: YYYY-MM-DD - Entity - Summary)
        # Matches: 2024-01-01 - Vendor - Desc.pdf
        is_valid_name = re.match(r'^\d{4}-\d{2}-\d{2} - .* - .*\.\w+$', name)
        
        if is_valid_name and not name.startswith("0000-00-00"):
            # MODE SPLIT:
            if mode == 'inbox':
                # Inbox Mode: Fall through to check if we can MOVE it (Cleanup)
                print(f"  [chk] Valid Name: {name} (Proceeding to Categorize/Move)")
            else:
                # Maintenance Mode: STRICT IDEMPOTENCY. Leave valid files alone.
                print(f"  [Skip - Valid] {name} (Maintenance Mode)")
                continue


        # Recursively Scan Subfolders
        if mime == 'application/vnd.google-apps.folder':
            print(f"  [Folder] Recursing into {name}...")
            # Recursive call with updated context
            scan_folder(fid, dry_run, csv_path, limit, mode, parent_context=f"{folder_context}/{name}")
            continue
            
        # Download & Process (Images, PDFs, Text, Docs)
        try:
             # Now processing EVERYTHING that isn't a folder
            content = download_file_content(service, fid, mime)
            
            # If content is empty (e.g. empty Google Doc), skip
            if not content:
                 print(f"  [Skip] Empty Content: {name}")
                 continue

            # Pass Folder Context as Hint
            context_hint = f"File located in folder: {folder_context}."
            if "Plaud" in folder_context:
                context_hint += " Source: Plaud.ai (Voice Recorder/Transcript)."
            elif "Gemini" in folder_context:
                context_hint += " Source: Gemini (AI Session Summary)."
            
            # Append Time Context
            time_context = get_time_context(f.get('createdTime'))
            if time_context:
                 context_hint += f" {time_context}"
                
            analysis = analyze_with_gemini(content, mime, name, context_hint)
            new_name = generate_new_name(analysis, name, f.get('createdTime'))
            
            print(f"  [AI] {name} -> {new_name}")
            
            # Write IMMEDIATE to CSV (Append)
            with open(csv_path, 'a', newline='') as csvfile:
                fieldnames = ['id', 'original', 'proposed', 'category', 'confidence']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerow({
                    'id': fid,
                    'original': name,
                    'proposed': new_name,
                    'category': analysis.get('category'),
                    'confidence': analysis.get('confidence')
                })
            
            # INBOX AUTO-EXECUTE LOGIC
            # AUTO-EXECUTE LOGIC
            if not dry_run:
                # INBOX MODE: Rename & Move
                if mode == 'inbox':
                    if new_name != name:
                        logger.info(f"  [Auto] Rename: {name} -> {new_name}")
                        stats.renamed += 1
                        
                        folder_category = analysis.get('category')
                        target_fid = resolve_folder_id(folder_category) or 'Inbox/Unknown'
                        target_fname = get_folder_path(service, target_fid)

                        log_to_sheet(
                            time.strftime("%Y-%m-%d %H:%M:%S"), 
                            fid, name, new_name, 
                            target_fid, target_fname,
                            'Auto'
                        )
                    else:
                        print(f"  [Same Name] Skipping rename.")

                    # 2. Move
                    category = analysis.get('category')
                    confidence = analysis.get('confidence')
                    target_id = resolve_folder_id(category)
                    
                    if confidence == 'High' and target_id:
                        if move_file(service, fid, target_id, new_name):
                             stats.moved += 1
                             full_path = get_folder_path(service, target_id)
                             logger.info(f"  [Auto] Move: {new_name} -> {full_path}")
                             # Log only if we didn't log a rename (or log as "Move")
                             if name == new_name:
                                 target_name = get_folder_path(service, target_id)
                                 log_to_sheet(
                                     time.strftime("%Y-%m-%d %H:%M:%S"),
                                     fid, name, new_name,
                                     target_id, target_name,
                                     'Auto-Move'
                                 )
                    else:
                        if name != new_name:
                             reason = "low confidence" if confidence != 'High' else "missing target folder"
                             logger.warning(f"  [Auto] Renamed but not moved ({reason}): {new_name}")
                        else:
                             print(f"  [Stay] Low Confidence ({confidence}) or Unmapped Category ({category})")
                
                # MAINTENANCE MODE: Rename Only (If necessary), Recommendation for Moves
                else:
                    # 1. Rename (Only if it was an invalid name to begin with)
                    if new_name != name and confidence == 'High':
                         logger.info(f"  [MAINTENANCE] Rename: {name} -> {new_name}")
                         stats.renamed += 1
                         service.files().update(fileId=fid, body={'name': new_name}).execute()
                         # Log
                         log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, 'None', 'None', 'Auto-Maintenance')
                    
                    # 2. Audit / Recommend Move
                    category = analysis.get('category')
                    target_id = resolve_folder_id(category)
                    
                    if target_id:
                        print(f"  [RECOMMENDATION] Move to Category: {category} (Target ID: {target_id})")
                    else:
                         print(f"  [Audit] Category: {category} (No specific target mapped)")
                
            stats.processed += 1
            processed_count += 1
                
        except Exception as e:
            logger.error(f"  [Error] {name}: {e}")
            stats.errors += 1

def process_inbox(dry_run=True, csv_path='sorter_dry_run.csv', limit=None):
    """Specialized scan for Inbox that MOVES files on success"""
    scan_folder(INBOX_ID, dry_run, csv_path, limit, mode='inbox')

def move_file(service, file_id, target_folder_id, processed_name):
    """Moves a file from Inbox to Target Folder"""
    try:
        # Retrieve the existing parents to remove
        file = service.files().get(fileId=file_id, fields='parents').execute()
        parents = file.get('parents', [])
        previous_parents = ",".join(parents) if parents else ""
        
        # Move the file by adding the new parent and removing the old one
        service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        print(f"  [MOVE] {processed_name} -> {target_folder_id}")
        return True
    except Exception as e:
        print(f"  [Move Error] {e}")
        return False

def execute_plan(csv_path):
    """Reads the CSV and applies renames"""
    service = get_drive_service()
    
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print("No plan found. Run --scan first.")
        return

    print(f"\n--- EXECUTING PLAN: {len(rows)} files ---")
    print("Press Ctrl+C to cancel within 5 seconds...")
    time.sleep(5)
    
    for row in rows:
        fid = row['id']
        original = row['original']
        new_name = row['proposed']
        
        if original == new_name:
            continue
            
        print(f"Renaming: {original} -> {new_name}")
        try:
            # Execute Rename
            body = {'name': new_name}
            service.files().update(fileId=fid, body=body).execute()
            logger.info(f"  [Manual] Rename: {original} -> {new_name}")
            stats.renamed += 1
            
            # Log to History
            # Log to History
            # Log to History
            target_id = resolve_folder_id(row.get('category')) or 'Unknown'
            target_name = get_folder_path(service, target_id)
            log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, original, new_name, target_id, target_name, 'Manual')
                
        except Exception as e:
             logger.error(f"  [Error] Failed to rename {fid}: {e}")
             stats.errors += 1
        
        stats.processed += 1

def migrate_history_schema():
    """Ensures renaming_history.csv has the latest columns."""
    # history_file = 'renaming_history.csv'
    # headers = ['Timestamp', 'ID', 'Original', 'New', 'Target_Folder', 'Run_Type']
    # Legacy migration removed as we use Google Sheets now
    pass

if __name__ == "__main__":
    logger.info(f"--- Run Started: {time.strftime('%Y-%m-%d %H:%M:%S')} (v{__version__}) ---")
    
    try:
        migrate_history_schema()

        parser = argparse.ArgumentParser(description="AI Drive Sorter")
        parser.add_argument('--scan', action='store_true', help="Scan folders and generate CSV plan")
        parser.add_argument('--execute', action='store_true', help="Execute renames from CSV plan")
        parser.add_argument('--inbox', action='store_true', help="Process Inbox: Auto-Rename and Move High Confidence files")
        parser.add_argument('--limit', type=int, default=None, help="Limit number of files to process per folder")
        args = parser.parse_args()

        CSV_FILE = 'sorter_dry_run.csv'

        # Target Folders
        TARGETS = [
            {'id': '1tKdysRukqbkzDuI1fomvSrYDhA3cr2mx', 'name': '03 - Finance'},
            {'id': '1Ob6M7x7-D1jmTNAVu0zd7fE3h5dgFsBX', 'name': '02 - Personal'},
            {'id': '1yruR1fC4TAR4U-Irb48p7tIERCDgg_PI', 'name': '04 - Health'},
            {'id': '1SHzgwpYJ8K1d9wGNHQPGP68zVIz13ymI', 'name': '06 - Library'}
        ]
        
        if args.inbox:
            logger.info("Mode: Inbox (Auto-Sort)")
            scan_folder(INBOX_ID, dry_run=(not args.execute), csv_path=CSV_FILE, limit=args.limit, mode='inbox')
            
        elif args.scan:
            logger.info("Mode: Scan (Planning)")
            for t in TARGETS:
                print(f"\n--- Scanning {t['name']} ---")
                scan_folder(t['id'], dry_run=True, csv_path=CSV_FILE, limit=args.limit)
                
        elif args.execute:
            logger.info("Mode: Execute (Manual Plan)")
            execute_plan(CSV_FILE)
        else:
            parser.print_help()
            sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal Error: {e}")
    finally:
        logger.info(stats.get_summary())
        sync_logs_to_drive()
        update_manifest()


