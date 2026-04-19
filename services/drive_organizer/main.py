"""
Main entry point for the Drive Organizer service.
Orchestrates scanning, AI categorization, and file movement based on `folder_config.json`.
"""
import os
import time
import argparse
import sys
import logging
import json
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
from toolbox.lib.telegram import send_message, escape, drive_file_link, monit_link
from toolbox.lib import quota_manager
from toolbox.lib.drive_utils import (
    get_drive_service, get_sheets_service,
    download_file_content, move_file,
    resolve_folder_id, get_category_prompt_str,
    INBOX_ID, METADATA_FOLDER_ID, HISTORY_SHEET_ID, ID_TO_PATH
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
        self.swept = 0
        self.errors = 0
        self.start_time = time.time()
        self.move_details = []    # (original_name, new_name, folder_path, file_id)
        self.rename_details = []  # (original_name, new_name, file_id)
        self.error_details = []   # (name, error_str, file_id)
        self._moved_fids = set()  # track which files were moved (to avoid duplicate rename lines)

    def get_summary(self):
        duration = int(time.time() - self.start_time)
        return f"Run completed in {duration}s. Processed: {self.processed}, Moved: {self.moved}, Renamed: {self.renamed}, Errors: {self.errors}."

    def get_notification(self):
        duration = int(time.time() - self.start_time)
        parts = []
        summary_parts = []
        if self.moved:
            summary_parts.append(f"{self.moved} moved")
        if self.renamed:
            summary_parts.append(f"{self.renamed} renamed")
        if self.swept:
            summary_parts.append(f"{self.swept} swept")
        if self.errors:
            summary_parts.append(f"{self.errors} error{'s' if self.errors > 1 else ''}")
        header = ", ".join(summary_parts) + f" ({duration}s)"
        parts.append(f"<b>{escape(header)}</b>")

        MAX = 10
        all_lines = []
        for orig, new, folder, fid in self.move_details:
            label = drive_file_link(fid, new) if fid else f"<code>{escape(new)}</code>"
            if orig != new:
                all_lines.append(f"  Moved: <code>{escape(orig)}</code> → {label}\n    → {escape(folder)}")
            else:
                all_lines.append(f"  Moved: {label}\n    → {escape(folder)}")
        for orig, new, fid in self.rename_details:
            label = drive_file_link(fid, new) if fid else f"<code>{escape(new)}</code>"
            all_lines.append(f"  Renamed: <code>{escape(orig)}</code> → {label}")
        for name, err, fid in self.error_details:
            label = drive_file_link(fid, name) if fid else f"<code>{escape(name)}</code>"
            all_lines.append(f"  Error: {label}\n    {escape(str(err))}")
        if self.error_details:
            all_lines.append(f"  {monit_link('Check Monit')} · <code>journalctl --user -u ai-sorter -n 50</code>")
        if self.swept:
            all_lines.append(f"  Swept {self.swept} file{'s' if self.swept > 1 else ''} → Inbox")

        parts.extend(all_lines[:MAX])
        if len(all_lines) > MAX:
            parts.append(f"  ... and {len(all_lines) - MAX} more")

        return "\n".join(parts)

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

_NEW_TRIPS_STATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'config', 'new_trips_flagged.json'
)
_ACTIVE_TRIP_PREFIX = '08 - Travel/Active/'


def _load_flagged_trips() -> set:
    try:
        with open(_NEW_TRIPS_STATE) as f:
            return set(json.load(f).get('flagged', []))
    except Exception:
        return set()


def _save_flagged_trips(flagged: set) -> None:
    tmp = _NEW_TRIPS_STATE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'flagged': sorted(flagged)}, f, indent=2)
    os.replace(tmp, _NEW_TRIPS_STATE)


def _maybe_flag_new_trip(folder_path: str, file_name: str, file_id: str) -> None:
    """Send a one-time Telegram alert when AI suggests an unknown Active trip folder."""
    if not folder_path or not folder_path.startswith(_ACTIVE_TRIP_PREFIX):
        return
    trip_name = folder_path[len(_ACTIVE_TRIP_PREFIX):]
    flagged = _load_flagged_trips()
    if trip_name in flagged:
        return
    flagged.add(trip_name)
    _save_flagged_trips(flagged)
    label = drive_file_link(file_id, file_name) if file_id else f'<code>{escape(file_name)}</code>'
    msg = (
        f'<b>New trip detected: {escape(trip_name)}</b>\n'
        f'File: {label}\n'
        f'Create <code>08 - Travel/Active/{escape(trip_name)}</code> in Drive '
        f'and add it to drive_tree.json to enable auto-routing.'
    )
    send_message(msg, service='ai-sorter · takhan')
    logger.info(f'  [NewTrip] Flagged new trip destination: {trip_name}')


_SKIP_MIME_TYPES = {
    'application/vnd.google-apps.folder',
    'application/vnd.google-apps.form',
    'application/vnd.google-apps.script',
    'application/vnd.google-apps.drawing',
    'application/vnd.google-apps.map',
    'application/vnd.google-apps.site',
}

_ALREADY_NAMED = re.compile(r'^\d{4}-\d{2}-\d{2} - .* - .*(\.\w+)?$')


def sweep_drive_root(dry_run=True, service=None):
    """Move un-named files from Drive root into Inbox so the sorter picks them up."""
    if not service:
        service = get_drive_service()

    results = service.files().list(
        q="'root' in parents and trashed = false",
        fields="files(id, name, mimeType)",
        pageSize=100,
    ).execute()
    files = results.get('files', [])

    swept = 0
    for f in files:
        if f['mimeType'] in _SKIP_MIME_TYPES:
            continue
        if _ALREADY_NAMED.match(f['name']):
            continue
        if not dry_run:
            if move_file(service, f['id'], INBOX_ID, f['name']):
                logger.info(f"  [Sweep] {f['name']} → Inbox")
                stats.swept += 1
                swept += 1
        else:
            logger.info(f"  [Sweep/dry] {f['name']}")
            swept += 1

    if swept:
        logger.info(f"Sweep: {swept} file(s) moved to Inbox")


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

        # Skip reserved files handled by other pipelines
        if name == 'Health Connect.zip':
            logger.info(f"Skipping {name} (reserved for health pipeline)")
            continue

        # Skip files flagged for manual review
        if name.startswith('[MANUAL] '):
            logger.info(f"Skipping {name} (flagged for manual review)")
            continue

        # Skip Google Apps types that can't be meaningfully renamed
        if mime in _SKIP_MIME_TYPES:
            continue

        # Validation: check if file is already processed (extension optional for Google Docs)
        is_valid_name = _ALREADY_NAMED.match(name)
        if is_valid_name and not name.startswith("0000-00-00"):
            if mode != 'inbox':
                continue

        try:
            try:
                content = download_file_content(service, fid, mime)
            except Exception as dl_err:
                if '500' in str(dl_err) or 'internalError' in str(dl_err).lower():
                    logger.warning(f"  [Export] {name}: Drive export 500, classifying by name only")
                    content = f"File: {name}\n(Export failed; classify by filename only)".encode('utf-8')
                    mime = 'text/plain'
                else:
                    raise
            if not content: continue

            context_hint = f"File located in folder: {folder_name}. Created: {f.get('createdTime')}"

            # --- AI ANALYSIS ---
            analysis, tokens = analyze_with_gemini(content, mime, name, folder_paths_str, context_hint, file_id=fid, use_free_tier=True)
            if tokens:
                quota_manager.record_tokens(tokens)

            new_name = generate_new_name(analysis, name, f.get('createdTime'))
            confidence = analysis.get('confidence', 'Low')
            reasoning = analysis.get('reasoning', 'No reasoning provided.')
            folder_path = analysis.get('folder_path')

            print(f"  [AI] {name} -> {new_name} ({confidence})")
            logger.info(f"Analysis for {name}: FolderPath={folder_path}, Entity={analysis.get('entity')}, Reasoning={reasoning}")

            # --- ACTION LOGIC ---
            if not dry_run:
                # Flag unresolvable files for manual review
                if analysis.get('summary') == 'Invalid_PDF' and not name.startswith('[MANUAL] '):
                    manual_name = f'[MANUAL] {name}'
                    service.files().update(fileId=fid, body={'name': manual_name}).execute()
                    logger.warning(f"  [Manual] Flagged for manual review: {name}")
                    send_message(f"Manual review needed: {drive_file_link(fid, name)}\nCould not parse as PDF after full-file retry.", service="ai-sorter")
                    stats.processed += 1
                    continue

                # Rename if High or Medium (Rename-only fallback for Medium)
                if new_name != name and confidence in ['High', 'Medium']:
                    service.files().update(fileId=fid, body={'name': new_name}).execute()
                    stats.renamed += 1
                    logger.info(f"  [Renamed] {new_name}")

                    # Log rename
                    target_id = resolve_folder_id(folder_path) or 'Unknown'
                    target_path = ID_TO_PATH.get(target_id, folder_path)
                    log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, target_id, target_path, f'Auto-Rename ({confidence})')

                # Move ONLY if High confidence and we have a target
                target_id = resolve_folder_id(folder_path)
                if not target_id and folder_path:
                    _maybe_flag_new_trip(folder_path, name, fid)
                if confidence == 'High' and target_id and target_id != folder_id:
                    if move_file(service, fid, target_id, new_name):
                        stats.moved += 1
                        stats._moved_fids.add(fid)
                        full_path = ID_TO_PATH.get(target_id, folder_path or 'Unknown')
                        stats.move_details.append((name, new_name, folder_path or full_path, fid))
                        logger.info(f"  [Moved] -> {full_path}")
                        # Log move (if not already logged via Rename)
                        if new_name == name:
                            log_to_sheet(time.strftime("%Y-%m-%d %H:%M:%S"), fid, name, new_name, target_id, full_path, 'Auto-Move')
                elif confidence == 'Medium':
                    logger.info(f"  [Skip Move] Medium confidence for {name}")

                # Record rename-only (not moved)
                if new_name != name and confidence == 'Medium' and fid not in stats._moved_fids:
                    stats.rename_details.append((name, new_name, fid))

            stats.processed += 1
                
        except Exception as e:
            logger.error(f"  [Error] {name}: {e}")
            stats.errors += 1
            stats.error_details.append((name, str(e), fid))

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

    if quota_manager.is_budget_exhausted():
        logger.info(f"Daily quota exhausted ({quota_manager.load()['total_tokens_used']:,} tokens). Skipping run.")
        sys.exit(0)

    target_id = args.folder_id or INBOX_ID
    target_name = args.folder_name or ("Inbox" if target_id == INBOX_ID else "Custom Folder")

    tokens_before = quota_manager.load().get('total_tokens_used', 0)

    try:
        if args.execute:
            logger.info(f"Mode: Execute (Target: {target_name})")
            sweep_drive_root(dry_run=False)
            scan_folder(target_id, dry_run=False, limit=args.limit, mode='inbox' if target_id == INBOX_ID else 'scan', folder_name=target_name, recursive=args.recursive)
        else:
            logger.info(f"Mode: Dry-Run/Scan (Target: {target_name})")
            sweep_drive_root(dry_run=True)
            scan_folder(target_id, dry_run=True, limit=args.limit, folder_name=target_name, recursive=args.recursive)
            
    finally:
        logger.info(stats.get_summary())
        tokens_this_run = quota_manager.load().get('total_tokens_used', 0) - tokens_before
        quota_manager.log_cost('sorter', stats.processed, tokens_this_run)
        if stats.moved > 0 or stats.renamed > 0 or stats.swept > 0 or stats.errors > 0:
            send_message(stats.get_notification(), service="ai-sorter")
