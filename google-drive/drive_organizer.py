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
from google import genai
from google.genai import types

__version__ = "0.4.0"

# --- CONFIG ---
TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'token_full_drive.json')
SECRET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gemini_secret')
SCOPES = ['https://www.googleapis.com/auth/drive']

# Folder Mapping constants
INBOX_ID = '1c-7Wv9J-FPpc3tph7Ax1xx5bMI-5jcaG'
FOLDER_MAP = {
    'Finance': '1tKdysRukqbkzDuI1fomvSrYDhA3cr2mx', # 03 - Finance
    'Health': '1yruR1fC4TAR4U-Irb48p7tIERCDgg_PI',  # 04 - Health
    'Library': '1SHzgwpYJ8K1d9wGNHQPGP68zVIz13ymI', # 06 - Library
    'House': '1Ob6M7x7-D1jmTNAVu0zd7fE3h5dgFsBX',    # 02 - Personal
    'Personal': '1Ob6M7x7-D1jmTNAVu0zd7fE3h5dgFsBX', # 02 - Personal
    'Auto': '1Ob6M7x7-D1jmTNAVu0zd7fE3h5dgFsBX',     # 02 - Personal
    'Education': '1Ob6M7x7-D1jmTNAVu0zd7fE3h5dgFsBX', # 02 - Personal
    'PKM': '1HNKo72TkLeurAi6g7X0C90OzqF2z3YB7',      # 01 - Second Brain/Inbox
    'Source_Material': '1BNwYqECrR9oPDC5os5uZcxKbaL7lRCoe', # Archive (AI Sources)
    'Work': '1zX-rciEeZnHsRrAwuxM8H8YC9bdnMVCa'      # 01 - Second Brain/Work
}

METADATA_FOLDER_ID = '1kwJ59bxRgYJgtv1c3sO-hhrvfIeD0JW0'

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
  "category": "One of [Finance, Health, Personal, House, Auto, Education, Tech, Work, PKM, Source_Material, Other]",
  "summary": "Very short 3-5 word description",
  "confidence": "High/Medium/Low"
}}

Rules:
- If date is ambiguous, use the creation date or null.
- "entity" should be clean (e.g. "Home Depot", not "THE HOME DEPOT INC").
- "summary" should be specific (e.g. "Paint Supplies", not "Shopping").
- Use category "Source_Material" for raw transcripts or logs.
- Use category "PKM" for notes, journals, or summaries.
"""

def sync_history_to_drive():
    """Uploads the local renaming_history.csv to the Metadata Archive folder."""
    history_file = 'renaming_history.csv'
    if not os.path.exists(history_file):
        return

    try:
        service = get_drive_service()
        
        # Check if file exists in Metadata folder to update it, or create new
        query = f"'{METADATA_FOLDER_ID}' in parents and name = '{history_file}' and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])

        media = MediaFileUpload(history_file, mimetype='text/csv')

        if files:
            # Update existing
            file_id = files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
            print(f"  [Sync] Updated history log in Drive ({file_id})")
        else:
            # Create new
            file_metadata = {
                'name': history_file,
                'parents': [METADATA_FOLDER_ID]
            }
            service.files().create(body=file_metadata, media_body=media).execute()
            print(f"  [Sync] Uploaded new history log to Drive.")
            
    except Exception as e:
        print(f"  [Sync Error] Failed to upload history: {e}")

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
             # Spreadsheets are better as CSV for AI usually, or PDF
            request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
        else:
             # Default fallback for slides etc
            request = service.files().export_media(fileId=file_id, mimeType='text/plain')
    else:
        # Download Binary / Text
        request = service.files().get_media(fileId=file_id)
        
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    return fh.getvalue()

def analyze_with_gemini(content_bytes, mime_type, context_hint=""):
    """
    Sends content to Gemini-1.5-Flash for analysis using the new google.genai SDK.
    """
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key missing")
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    ai_mime = mime_type
    if 'pdf' in mime_type:
        ai_mime = 'application/pdf'
    elif 'image' in mime_type:
        ai_mime = 'image/jpeg' # Simplification
    elif mime_type == 'text/plain' or 'markdown' in mime_type or 'document' in mime_type:
        ai_mime = 'text/plain' # Treat text/md/gdoc-export as text
        
    print(f"  Sending to Gemini as {ai_mime} (Context: {context_hint})...")
    
    # Inject context into prompt
    prompt_with_context = SYSTEM_PROMPT.format(context_hint=context_hint)
    
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
        
        # Robust JSON extraction: Find first '{' and last '}'
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
        print(f"Gemini Error: {e}")
        return {
            "doc_date": "0000-00-00",
            "entity": "Unknown", 
            "category": "Uncategorized", 
            "summary": "AI_Error",
            "confidence": "Low"
        }

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
    
    # 1. Content Date (from AI) - Default
    date = analysis.get('doc_date', '0000-00-00')
    if date is None: 
        date = '0000-00-00'

    # 2. Filename Date (Regex) - Priority if AI failed or matched "0000-00-00"
    if date == '0000-00-00':
        match = re.search(r'(\d{4}-\d{2}-\d{2})', original_name)
        if match:
            date = match.group(1)
            # print(f"    [Date] Used Filename: {date}")

    # 3. Created Date (Metadata) - Fallback
    if date == '0000-00-00' and created_time_str:
        # created_time_str e.g. "2023-10-27T10:00:00Z"
        date = created_time_str[:10]
        # print(f"    [Date] Used CreatedTime: {date}")

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
                
            analysis = analyze_with_gemini(content, mime, context_hint)
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
                    # 1. Rename
                    if new_name != name:
                        print(f"  [EXECUTE] Renaming...")
                        service.files().update(fileId=fid, body={'name': new_name}).execute()
                        # Log Rename
                        with open('renaming_history.csv', 'a', newline='') as history_file:
                            writer = csv.writer(history_file)
                            # [Timestamp, ID, Original, New, Target_Folder, Run_Type]
                            target_id = FOLDER_MAP.get(analysis.get('category'), 'Inbox/Unknown')
                            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, target_id, 'Auto'])
                    else:
                        print(f"  [Same Name] Skipping rename.")

                    # 2. Move
                    category = analysis.get('category')
                    confidence = analysis.get('confidence')
                    target_id = FOLDER_MAP.get(category)
                    
                    if confidence == 'High' and target_id:
                        move_file(service, fid, target_id, new_name)
                    else:
                        print(f"  [Stay] Low Confidence ({confidence}) or Unmapped Category ({category})")
                
                # MAINTENANCE MODE: Rename Only (If necessary), Recommendation for Moves
                else:
                    # 1. Rename (Only if it was an invalid name to begin with)
                    if new_name != name and confidence == 'High':
                         print(f"  [MAINTENANCE] Renaming {name} -> {new_name}...")
                         service.files().update(fileId=fid, body={'name': new_name}).execute()
                         # Log
                         with open('renaming_history.csv', 'a', newline='') as history_file:
                             writer = csv.writer(history_file)
                             writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, 'None', 'Auto-Maintenance'])
                    
                    # 2. Audit / Recommend Move
                    category = analysis.get('category')
                    target_id = FOLDER_MAP.get(category)
                    
                    # We can't easily check 'current folder ID' vs 'target ID' without an extra API call or passing parent ID.
                    # Ideally, if target_id exists, we recommend it.
                    if target_id:
                        print(f"  [RECOMMENDATION] Move to Category: {category} (Target ID: {target_id})")
                    else:
                         print(f"  [Audit] Category: {category} (No specific target mapped)")
                
            processed_count += 1
                
        except Exception as e:
            print(f"  [Error] {name}: {e}")

def process_inbox(dry_run=True, csv_path='sorter_dry_run.csv', limit=None):
    """Specialized scan for Inbox that MOVES files on success"""
    scan_folder(INBOX_ID, dry_run, csv_path, limit, mode='inbox')

def move_file(service, file_id, target_folder_id, processed_name):
    """Moves a file from Inbox to Target Folder"""
    try:
        # Retrieve the existing parents to remove
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        
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
            
            # Log to History
            with open('renaming_history.csv', 'a', newline='') as history_file:
                writer = csv.writer(history_file)
                # Timestamp, ID, Original, New, Target_Folder, Run_Type
                target_id = FOLDER_MAP.get(row.get('category'), 'Unknown')
                writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), fid, original, new_name, target_id, 'Manual'])
                
        except Exception as e:
             print(f"  [Error] Failed to rename {fid}: {e}")

def migrate_history_schema():
    """Ensures renaming_history.csv has the latest columns."""
    history_file = 'renaming_history.csv'
    headers = ['Timestamp', 'ID', 'Original', 'New', 'Target_Folder', 'Run_Type']
    
    if not os.path.exists(history_file):
        with open(history_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        return

    # Read existing
    with open(history_file, 'r', newline='') as f:
        reader = csv.reader(f)
        data = list(reader)

    if not data:
        return

    # Check header
    if len(data[0]) < 6:
        print("  [Migration] Upgrading history file schema...")
        new_data = [headers]
        # Skip old header if it exists but is short, or treat first row as data if no header? 
        # Assuming no header in old version based on previous 'cat' output, wait.
        # The previous output showed: 2026-01-14 13:24:34,1X... 
        # It seems existing file HAS NO HEADER. It's just data.
        
        for row in data:
            # Check if row looks like a header
            if row[0] == 'Timestamp': 
                continue # Skip old header if present
            
            # Pad row to 6 columns
            # Old schema: [Timestamp, ID, Original, New] (4 cols)
            # New schema: + [Target_Folder, Run_Type]
            while len(row) < 4:
                row.append("Unknown")
            
            row = row[:4] + ["Unknown", "Legacy"]
            new_data.append(row)
            
        with open(history_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(new_data)

if __name__ == "__main__":
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
        print("\n--- Processing Inbox (Auto-Sort Mode) ---")
        scan_folder(INBOX_ID, dry_run=(not args.execute), csv_path=CSV_FILE, limit=args.limit, mode='inbox')
        
        if args.execute:
             sync_history_to_drive()
        
    elif args.scan:
        # Note: Appending to existing CSV if present
        
        for t in TARGETS:
            print(f"\n--- Scanning {t['name']} ---")
            scan_folder(t['id'], dry_run=True, csv_path=CSV_FILE, limit=args.limit)
            
    elif args.execute:
        execute_plan(CSV_FILE)
        sync_history_to_drive()
    else:
        print("Please specify --scan or --execute")
