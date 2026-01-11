import os
import time
import json
import csv
import argparse
import sys
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from google import genai
from google.genai import types

__version__ = "0.3.0"

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
    'Education': '1Ob6M7x7-D1jmTNAVu0zd7fE3h5dgFsBX' # 02 - Personal
}

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
Extract the following fields into a pure JSON object (no markdown formatting):
{
  "doc_date": "YYYY-MM-DD",
  "entity": "Name of Vendor/Person/Organization",
  "category": "One of [Finance, Health, Personal, House, Auto, Education, Tech, Other]",
  "summary": "Very short 3-5 word description",
  "confidence": "High/Medium/Low"
}

Rules:
- If date is ambiguous, use the creation date or null.
- "entity" should be clean (e.g. "Home Depot", not "THE HOME DEPOT INC").
- "summary" should be specific (e.g. "Paint Supplies", not "Shopping").
"""

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

def analyze_with_gemini(content_bytes, mime_type):
    """
    Sends content to Gemini-1.5-Flash for analysis using the new google.genai SDK.
    """
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key missing")
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Map Drive mime types to Generative AI mime types if needed, 
    # but 'application/pdf' and 'image/jpeg' usually work directly if passed as data.
    # For robust PDF handling with the API, we interpret bytes.
    
    ai_mime = mime_type
    if 'pdf' in mime_type:
        ai_mime = 'application/pdf'
    elif 'image' in mime_type:
        ai_mime = 'image/jpeg' # Simplification
    elif mime_type == 'text/plain' or 'markdown' in mime_type or 'document' in mime_type:
        ai_mime = 'text/plain' # Treat text/md/gdoc-export as text
        
    print(f"  Sending to Gemini as {ai_mime}...")
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[
                SYSTEM_PROMPT,
                types.Part.from_bytes(data=content_bytes, mime_type=ai_mime)
            ]
        )
        
        # Parse JSON from response
        text = response.text.strip()
        # Cleanup markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        
        return json.loads(text)
    except Exception as e:
        print(f"Gemini Error: {e}")
        return {
            "doc_date": "0000-00-00",
            "entity": "Unknown", 
            "category": "Uncategorized", 
            "summary": "AI_Error",
            "confidence": "Low"
        }

def generate_new_name(analysis, original_name):
    ext = os.path.splitext(original_name)[1]
    date = analysis.get('doc_date', '0000-00-00')
    if date is None:
        date = "0000-00-00"
        
    entity = analysis.get('entity', 'Unknown')
    summary = analysis.get('summary', 'Doc')
    
    # Cleanup strings
    safe_entity = "".join([c for c in entity if c.isalnum() or c in [' ', '_', '-']]).strip().replace(" ", "_")
    safe_summary = "".join([c for c in summary if c.isalnum() or c in [' ', '_', '-']]).strip().replace(" ", "_")
    
    if date == "0000-00-00" or not date:
         # Fallback to preserving original name if AI failed completely on date
         safe_summary = f"{safe_summary}_(NoDate)"
    
    return f"{date} - {safe_entity} - {safe_summary}{ext}"

def scan_folder(folder_id, dry_run=True, csv_path='sorter_dry_run.csv', limit=None, mode='scan'):
    service = get_drive_service()
    
    folder_name = "Inbox" if folder_id == INBOX_ID else folder_id
    print(f"Scanning folder {folder_name}...")
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType)"
    ).execute()
    files = results.get('files', [])
    
    # Initialize CSV if starting fresh
    if not os.path.exists(csv_path):
        with open(csv_path, 'w', newline='') as csvfile:
            fieldnames = ['id', 'original', 'proposed', 'category', 'confidence']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
    
    print(f"Found {len(files)} files. Processing...")
    
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
        if re.match(r'^\d{4}-\d{2}-\d{2} - .* - .*\.\w+$', name):
            print(f"  [Skip - Done] {name}")
            continue

        # Skip folders
        if mime == 'application/vnd.google-apps.folder':
            # print(f"  [Folder] Entering {name}...")
            # scan_folder(fid, dry_run, csv_path, limit, mode)
            print(f"  [Skip] Folder: {name}")
            continue
            
        # Download & Process (Images, PDFs, Text, Docs)
        try:
             # Now processing EVERYTHING that isn't a folder
            content = download_file_content(service, fid, mime)
            
            # If content is empty (e.g. empty Google Doc), skip
            if not content:
                 print(f"  [Skip] Empty Content: {name}")
                 continue

            analysis = analyze_with_gemini(content, mime)
            new_name = generate_new_name(analysis, name)
            
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
            if mode == 'inbox' and not dry_run:
                # 1. Rename File
                print(f"  [EXECUTE] Renaming...")
                service.files().update(fileId=fid, body={'name': new_name}).execute()
                
                # Log Rename
                with open('renaming_history.csv', 'a', newline='') as history_file:
                    writer = csv.writer(history_file)
                    writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name])

                # 2. Move File (if High Confidence)
                category = analysis.get('category')
                confidence = analysis.get('confidence')
                target_id = FOLDER_MAP.get(category)
                
                if confidence == 'High' and target_id:
                    move_file(service, fid, target_id, new_name)
                else:
                    print(f"  [Stay] Low Confidence ({confidence}) or Unmapped Category ({category})")
                
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
                # Timestamp, ID, Original, New
                writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), fid, original, new_name])
                
        except Exception as e:
             print(f"  [Error] Failed to rename {fid}: {e}")

if __name__ == "__main__":
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
        
    elif args.scan:
        # Note: Appending to existing CSV if present
        
        for t in TARGETS:
            print(f"\n--- Scanning {t['name']} ---")
            scan_folder(t['id'], dry_run=True, csv_path=CSV_FILE, limit=args.limit)
            
    elif args.execute:
        execute_plan(CSV_FILE)
    else:
        print("Please specify --scan or --execute")
