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
# Going up 3 levels: drive_organizer -> services -> toolbox -> tariqk00
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.lib.ai_engine import analyze_with_gemini
from toolbox.lib.telegram import send_message
from toolbox.lib.drive_utils import (
    get_drive_service, get_sheets_service,
    download_file_content, move_file,
    get_folder_path, resolve_folder_id,
    get_category_prompt_str,
    INBOX_ID, METADATA_FOLDER_ID, HISTORY_SHEET_ID
)

# --- CONFIG ---
# LOGGING
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'sorter.log')

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

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

    person = analysis.get('person')
    known_persons = {'Dawn', 'Thomas', 'Sofia'}
    if person and str(person).strip().capitalize() in known_persons:
        safe_person = str(person).strip().capitalize()
        return f"{date} - {safe_entity} - {safe_person} - {safe_summary}{ext}"

    return f"{date} - {safe_entity} - {safe_summary}{ext}"

def scan_folder(folder_id, dry_run=True, csv_path='sorter_dry_run.csv', limit=None, mode='scan', folder_name="Inbox", service=None, recursive=True):
    if not service:
        service = get_drive_service()
    
    # Init Logger to file
    if not dry_run:
        fh = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
    
    print(f"Scanning folder {folder_name} ({folder_id})...")
    
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, createdTime)"
    ).execute()
    files = results.get('files', [])
    
    print(f"Found {len(files)} files in {folder_name}. Processing...")

    folder_paths_str = get_category_prompt_str()

    for f in files:
        if limit and stats.processed >= limit:
            break

        name = f['name']
        fid = f['id']
        mime = f['mimeType']

        # Recursion
        if mime == 'application/vnd.google-apps.folder':
            if recursive:
                scan_folder(fid, dry_run, csv_path, limit, mode, folder_name=f"{folder_name}/{name}", service=service, recursive=recursive)
            continue

        # Validation: check if file is already processed
        is_valid_name = re.match(r'^\d{4}-\d{2}-\d{2} - .* - .*\.\w+$', name)
        if is_valid_name and not name.startswith("0000-00-00"):
            if mode != 'inbox':
                continue

        try:
            content = download_file_content(service, fid, mime)
            if not content: continue

            context_hint = f"File located in folder: {folder_name}. Created: {f.get('createdTime')}"

            # --- AI ANALYSIS ---
            analysis = analyze_with_gemini(content, mime, name, folder_paths_str, context_hint, file_id=fid)

            new_name = generate_new_name(analysis, name, f.get('createdTime'))
            confidence = analysis.get('confidence', 'Low')
            reasoning = analysis.get('reasoning', 'No reasoning provided.')
            folder_path = analysis.get('folder_path')

            print(f"  [AI] {name} -> {new_name} ({confidence})")
            logger.info(f"Analysis for {name}: FolderPath={folder_path}, Entity={analysis.get('entity')}, Reasoning={reasoning}")

            # --- ACTION LOGIC ---
            if not dry_run:
                # Rename if High or Medium (Rename-only fallback for Medium)
                if new_name != name and confidence in ['High', 'Medium']:
                    service.files().update(fileId=fid, body={'name': new_name}).execute()
                    stats.renamed += 1
                    logger.info(f"  [Renamed] {new_name}")

                    # Log rename
                    target_id = resolve_folder_id(folder_path) or 'Unknown'
                    target_path = get_folder_path(service, target_id)
                    log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, target_id, target_path, f'Auto-Rename ({confidence})')

                # Move ONLY if High confidence and we have a target
                target_id = resolve_folder_id(folder_path)
                if confidence == 'High' and target_id and target_id != folder_id:
                    if move_file(service, fid, target_id, new_name):
                        stats.moved += 1
                        full_path = get_folder_path(service, target_id)
                        logger.info(f"  [Moved] -> {full_path}")
                        # Log move (if not already logged via Rename)
                        if new_name == name:
                            log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, target_id, full_path, 'Auto-Move')
                elif confidence == 'Medium':
                    logger.info(f"  [Skip Move] Medium confidence for {name}")

            stats.processed += 1
                
        except Exception as e:
            logger.error(f"  [Error] {name}: {e}")
            stats.errors += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Drive Sorter (Modular v0.6)")
    parser.add_argument('--scan', action='store_true', help="Scan mode")
    parser.add_argument('--inbox', action='store_true', help="Inbox mode (Default)")
    parser.add_argument('--execute', action='store_true', help="Execute changes")
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--folder_id', type=str, help="Specify folder ID to process")
    parser.add_argument('--folder_name', type=str, help="Friendly name for specified folder")
    parser.add_argument('--no-recurse', action='store_false', dest='recursive', default=True, help="Disable recursive scanning")
    
    args = parser.parse_args()
    
    target_id = args.folder_id or INBOX_ID
    target_name = args.folder_name or ("Inbox" if target_id == INBOX_ID else "Custom Folder")
    
    try:
        if args.execute:
            logger.info(f"Mode: Execute (Target: {target_name})")
            scan_folder(target_id, dry_run=False, limit=args.limit, mode='inbox' if target_id == INBOX_ID else 'scan', folder_name=target_name, recursive=args.recursive)
        else:
            logger.info(f"Mode: Dry-Run/Scan (Target: {target_name})")
            scan_folder(target_id, dry_run=True, limit=args.limit, folder_name=target_name, recursive=args.recursive)
            
    finally:
        summary = stats.get_summary()
        logger.info(summary)
        if stats.moved > 0 or stats.renamed > 0 or stats.errors > 0:
            send_message(summary, service="ai-sorter")
