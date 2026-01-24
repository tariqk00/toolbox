"""
Main entry point for the Drive Organizer service.
Orchestrates scanning, AI categorization, and file movement based on `folder_config.json`.
"""
import os
import time
import argparse
import sys
import logging
from logging.handlers import RotatingFileHandler
import re

# Import Core Modules
# Ensure toolbox package is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(current_dir))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.core.ai import analyze_with_gemini
from toolbox.core.drive import (
    get_drive_service, get_sheets_service, 
    download_file_content, move_file, 
    get_folder_path, resolve_folder_id,
    get_category_prompt_str, FOLDER_CONFIG,
    load_folder_config
)

__version__ = "0.5.0"

# --- CONFIG ---
# LOGGING
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'sorter.log')

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

INBOX_ID = '1c-7Wv9J-FPpc3tph7Ax1xx5bMI-5jcaG'
METADATA_FOLDER_ID = '1kwJ59bxRgYJgtv1c3sO-hhrvfIeD0JW0'
HISTORY_SHEET_ID = '1N8xlrcCnj97uGPssXnGg_-1t2SvGZlnocc_7BNO28dY'

stats = None # Global stats placeholder

class RunStats:
    def __init__(self):
        self.processed = 0
        self.moved = 0
        self.renamed = 0
        self.errors = 0
        self.start_time = time.time()

    def get_summary(self):
        duration = int(time.time() - self.start_time)
        return f"Run completed in {duration}s. Processed: {self.processed}, Moved: {self.moved}, Renamed: {self.renamed}, Errors: {self.errors}."

stats = RunStats()
logger = logging.getLogger("DriveSorter")
logger.setLevel(logging.INFO)

# Console & File Handlers
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(ch)

fh = RotatingFileHandler(LOG_FILE, maxBytes=1*1024*1024, backupCount=5)
fh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
logger.addHandler(fh)

def log_to_sheet(timestamp, file_id, original_name, new_name, target_folder_id, target_folder_name, run_type):
    """Logs to Google Sheet."""
    if not HISTORY_SHEET_ID:
        return

    safe_new_name = new_name.replace('"', '""')
    link_file = f'=HYPERLINK("https://drive.google.com/open?id={file_id}", "{safe_new_name}")'
    
    safe_target_name = target_folder_name.replace('"', '""')
    if target_folder_id and target_folder_id not in ["None", "Unknown", "Inbox/Unknown"]:
         link_folder = f'=HYPERLINK("https://drive.google.com/drive/u/0/folders/{target_folder_id}", "{safe_target_name}")'
    else:
         link_folder = target_folder_name

    row_data = [timestamp, file_id, original_name, link_file, link_folder, run_type]

    try:
        service = get_sheets_service()
        body = {'values': [row_data]}
        service.spreadsheets().values().append(
            spreadsheetId=HISTORY_SHEET_ID, range="Log!A:A",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
    except Exception as e:
        logger.error(f"  [Log Error] Failed to write to Sheet: {e}")

def generate_new_name(analysis, original_name, created_time_str):
    ext = os.path.splitext(original_name)[1]
    name_no_ext = os.path.splitext(original_name)[0]
    
    date = analysis.get('doc_date', '0000-00-00')
    if date == '0000-00-00':
        match = re.search(r'(\d{4}-\d{2}-\d{2})', original_name)
        if match:
            date = match.group(1)
        elif created_time_str:
            date = created_time_str[:10]

    summary = analysis.get('summary', 'Doc')
    entity = analysis.get('entity', 'Unknown')
    
    str_entity = str(entity or "Unknown")
    str_summary = str(summary or "Doc")
    
    safe_entity = "".join([c for c in str_entity if c.isalnum() or c in [' ', '_', '-']]).strip().replace(" ", "_")
    safe_summary = "".join([c for c in str_summary if c.isalnum() or c in [' ', '_', '-']]).strip().replace(" ", "_")
    
    if date == "0000-00-00" or not date:
         safe_summary = f"{safe_summary}_(NoDate)"
    
    return f"{date} - {safe_entity} - {safe_summary}{ext}"

def scan_folder(folder_id, dry_run=True, csv_path='sorter_dry_run.csv', limit=None, mode='scan', parent_context="Inbox"):
    service = get_drive_service()
    
    # Get actual folder name
    folder_context = parent_context
    if folder_id == INBOX_ID:
        folder_context = "Inbox"
    
    print(f"Scanning folder {folder_context} ({folder_id})...")
    
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, createdTime)"
    ).execute()
    files = results.get('files', [])
    
    print(f"Found {len(files)} files in {folder_context}. Processing...")
    
    processed_count = 0
    for f in files:
        if limit and processed_count >= limit:
            break

        name = f['name']
        fid = f['id']
        mime = f['mimeType']
        
        # Validation: check if file is already processed
        is_valid_name = re.match(r'^\d{4}-\d{2}-\d{2} - .* - .*\.\w+$', name)
        if is_valid_name and not name.startswith("0000-00-00"):
            if mode == 'inbox':
                pass # Proceed to categorize/move
            else:
                continue

        # Recursion
        if mime == 'application/vnd.google-apps.folder':
            scan_folder(fid, dry_run, csv_path, limit, mode, parent_context=f"{folder_context}/{name}")
            continue
            
        try:
            content = download_file_content(service, fid, mime)
            if not content: continue

            context_hint = f"File located in folder: {folder_context}."
            
            # --- AI ANALYSIS (Moved to Core) ---
            category_str = get_category_prompt_str()
            analysis = analyze_with_gemini(content, mime, name, category_str, context_hint, file_id=fid)
            
            new_name = generate_new_name(analysis, name, f.get('createdTime'))
            
            print(f"  [AI] {name} -> {new_name}")
            
            # --- ACTION LOGIC ---
            if not dry_run:
                # INBOX MODE
                if mode == 'inbox':
                    # Rename
                    if new_name != name and analysis.get('confidence') == 'High':
                        service.files().update(fileId=fid, body={'name': new_name}).execute()
                        stats.renamed += 1
                        logger.info(f"  [Renamed] {new_name}")
                        
                        folder_category = analysis.get('category')
                        # Log rename
                        target_dummy = resolve_folder_id(folder_category) or 'Unknown'
                        target_dummy_name = get_folder_path(service, target_dummy)
                        log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, target_dummy, target_dummy_name, 'Auto-Rename')

                    # Move
                    category = analysis.get('category')
                    confidence = analysis.get('confidence')
                    target_id = resolve_folder_id(category)
                    
                    if confidence == 'High' and target_id:
                        if move_file(service, fid, target_id, new_name):
                             stats.moved += 1
                             full_path = get_folder_path(service, target_id)
                             logger.info(f"  [Moved] -> {full_path}")
                             # Log move
                             if name == new_name: # If renamed, we logged above. If same, log move here.
                                 log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, target_id, full_path, 'Auto-Move')
                    else:
                        if name != new_name:
                             logger.warning(f"  [Renamed Only] {new_name} (Low conf/No target)")

            stats.processed += 1
            processed_count += 1
                
        except Exception as e:
            logger.error(f"  [Error] {name}: {e}")
            stats.errors += 1

def sync_logs_to_drive():
    # Simplification: This logic kept from original but could be moved to drive.py if needed.
    # For now, keeping orchestration specific logic here is fine.
    pass 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Drive Sorter (Modular v0.5)")
    parser.add_argument('--scan', action='store_true', help="Scan mode")
    parser.add_argument('--inbox', action='store_true', help="Inbox mode")
    parser.add_argument('--execute', action='store_true', help="Execute changes")
    parser.add_argument('--limit', type=int, default=0)
    
    args = parser.parse_args()
    
    try:
        if args.inbox:
            logger.info("Mode: Inbox (Auto-Sort)")
            scan_folder(INBOX_ID, dry_run=not args.execute, limit=args.limit, mode='inbox')
        elif args.scan:
            logger.info("Mode: Scan")
            scan_folder(INBOX_ID, dry_run=True, limit=args.limit)
        else:
            parser.print_help()
            
    finally:
        logger.info(stats.get_summary())
