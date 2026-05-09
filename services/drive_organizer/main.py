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
import re
from datetime import datetime

# Setup paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from toolbox.lib.log_manager import LogManager, log
logger = LogManager.get_instance("ai-sorter").logger

from toolbox.lib.drive_utils import (
    get_drive_service, download_file_content, move_file,
    resolve_folder_id, get_category_prompt_str,
    INBOX_ID, ID_TO_PATH, _ALREADY_NAMED, _SKIP_MIME_TYPES,
    SORTER_SYSTEM_PROMPT, escape_query_string
)
from toolbox.lib.telegram import send_message, drive_file_link
from toolbox.lib.llm_gateway import call_json_llm
from toolbox.lib import quota_manager
from toolbox.lib.entity_ids import render_entity_comment, order_entity_id, travel_entity_id, build_entity_id, canonicalize_key
from toolbox.lib.entity_memory import EntityMemory

# --- CONFIG ---
stats = None # Global stats placeholder
STATE_PATH = os.path.join(BASE_DIR, 'config', 'ai_sorter_state.json')

class RunStats:
    def __init__(self, app_name="ai-sorter"):
        self.app_name = app_name
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
        log("RUN_COMPLETE", "SUCCESS" if self.errors == 0 else "WARNING", 
            f"Drive organizer run finished in {duration}s", data={
            "processed": self.processed,
            "moved": self.moved,
            "renamed": self.renamed,
            "errors": self.errors,
            "duration_s": duration
        }, app_name=self.app_name)
        return f"Run completed in {duration}s. Processed: {self.processed}, Moved: {self.moved}, Renamed: {self.renamed}, Errors: {self.errors}."

    def get_notification(self):
        duration = int(time.time() - self.start_time)
        parts = []
        if self.moved > 0:
            parts.append(f"📦 Moved {self.moved}")
        if self.renamed > 0:
            # only count renames that weren't also moved
            pure_renames = len([r for r in self.rename_details if r[2] not in self._moved_fids])
            if pure_renames > 0:
                parts.append(f"✏️ Renamed {pure_renames}")
        if self.swept > 0:
            parts.append(f"🧹 Swept {self.swept}")
        if self.errors > 0:
            parts.append(f"❌ Errors {self.errors}")
            
        if not parts: return None
        
        header = f"<b>AI Sorter: {', '.join(parts)}</b> ({duration}s)"
        lines = [header]
        
        # Add move details
        for old, new, folder, fid in self.move_details[:10]:
            folder_name = folder.split('/')[-1]
            lines.append(f"  • {new} → <code>{folder_name}</code>")
        
        if len(self.move_details) > 10:
            lines.append(f"  ...and {len(self.move_details)-10} more")
            
        return "\n".join(lines)

def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except:
            pass
    return {"analyzed_ids": {}} # file_id -> last_analyzed_name

def save_state(state):
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)

def _skip_mime_types():
    return [
        'application/vnd.google-apps.spreadsheet',
        'application/vnd.google-apps.folder',
        'application/vnd.google-apps.form',
        'application/vnd.google-apps.site',
        'application/google-apps.map',
        'application/vnd.google-apps.drawing',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ]

_SKIP_MIME_TYPES = _skip_mime_types()

def log_to_sheet(timestamp, fid, old_name, new_name, target_id, target_path, status):
    """Placeholder for legacy sheet logging if needed."""
    pass

def _maybe_flag_new_trip(folder_path, filename, fid):
    """If AI thinks it's a trip but we don't have the folder, notify."""
    if 'Trips/' in folder_path:
        # Trip folder doesn't exist yet
        send_message(
            f"New Trip detected? Folder missing for: <code>{folder_path}</code>\nFile: {drive_file_link(fid, filename)}",
            service="ai-sorter",
            category="warning",
        )

def check_duplicate(service, target_folder_id, filename, checksum=None):
    """Check if a file with same name or same MD5 exists in the target folder."""
    # 1. Check by Checksum (if binary) - Detects same content with different names
    if checksum:
        q_hash = f"md5Checksum = '{checksum}' and '{target_folder_id}' in parents and trashed = false"
        res_hash = service.files().list(q=q_hash, fields="files(id, name)").execute()
        files_hash = res_hash.get('files', [])
        if files_hash:
            return files_hash[0]['id'], "hash_match"

    # 2. Check by Name - Catch Workspace files or different versions
    safe_name = escape_query_string(filename)
    q_name = f"name = '{safe_name}' and '{target_folder_id}' in parents and trashed = false"
    res_name = service.files().list(q=q_name, fields="files(id)").execute()
    files_name = res_name.get('files', [])
    if files_name:
        return files_name[0]['id'], "name_match"

    return None, None

def post_process_memory(analysis, final_name, fid):
    """Update entity memory with organized file metadata."""
    entity = analysis.get('entity', 'Unknown')
    doc_date = analysis.get('doc_date', '0000-00-00')
    folder_path = analysis.get('folder_path', '')
    
    if entity == 'Unknown' or not entity:
        return

    # Map folder_path to Memory category
    category = "General"
    if "Finance" in folder_path: category = "Finance"
    elif "Health" in folder_path: category = "Health"
    elif "Travel" in folder_path: category = "Travel"
    elif "Career" in folder_path: category = "Work"
    elif "Personal" in folder_path: category = "Personal"

    mem_filename = f"{entity}.md"
    try:
        mem = EntityMemory.load_from_drive(category, mem_filename)
        
        # Add entity ID if missing
        if not mem.entity_id:
            mem.entity_id = build_entity_id(category.lower(), canonicalize_key(entity))
            
        # Append timeline event
        event = f"[Document Organized] {final_name}"
        mem.add_timeline_event(event, date=doc_date)
        
        # Add source
        mem.add_source(f"Drive: {drive_file_link(fid, final_name)}")
        
        mem.save_to_drive(category, mem_filename)
        logger.info(f"Updated memory for entity: {entity} ({category})")
    except Exception as e:
        logger.error(f"Failed to update memory for {entity}: {e}")

def scan_folder(folder_id, dry_run=True, csv_path='sorter_dry_run.csv', limit=None, mode='scan', folder_name="Inbox", service=None, recursive=True, state=None):
    if not service:
        service = get_drive_service()
    
    if state is None:
        state = {"analyzed_ids": {}}

    print(f"Scanning folder {folder_name} ({folder_id})...")
    
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, createdTime, md5Checksum)"
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
        checksum = f.get('md5Checksum', '')

        # Recursion
        if mime == 'application/vnd.google-apps.folder':
            if recursive:
                scan_folder(fid, dry_run, csv_path, limit, mode, folder_name=f"{folder_name}/{name}", service=service, recursive=recursive, state=state)
            continue

        # 1. Skip logic: don't re-analyze what hasn't changed
        # If the name is already standardized AND we've seen this ID before, skip it.
        is_already_standard = _ALREADY_NAMED.match(name) and not name.startswith("0000-00-00")
        if is_already_standard and fid in state["analyzed_ids"]:
            # Only skip if the name matches our record (sanity check)
            if state["analyzed_ids"][fid] == name:
                logger.debug(f"Skipping already standardized file: {name}")
                stats.processed += 1
                continue

        # Skip reserved files
        if name == 'Health Connect.zip': continue
        if name.startswith('[MANUAL] '): continue
        if mime in _SKIP_MIME_TYPES: continue

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

            # --- AI ANALYSIS ---
            full_prompt = SORTER_SYSTEM_PROMPT.format(
                context_hint=f"Filename: {name}",
                folder_paths=folder_paths_str
            )
            analysis, reasoning, tokens_this_run = call_json_llm(
                task_type='automation',
                prompt=full_prompt,
                content_bytes=content,
                mime_type=mime,
                filename=name
            )
            
            new_name = analysis.get('new_filename', name)
            folder_path = analysis.get('folder_path', '')
            confidence = str(analysis.get('confidence', 'Low')).strip().capitalize()

            print(f"  [AI] {name} -> {new_name} ({confidence})")
            log("FILE_ANALYZED", "SUCCESS", f"Analyzed {name}", data={
                "file_id": fid,
                "original_name": name,
                "new_name": new_name,
                "confidence": confidence,
                "category": folder_path
            }, app_name=stats.app_name)

            # --- ACTION LOGIC ---
            if not dry_run:
                # 1. Handle Low Confidence or Unresolvable Routing
                if confidence == 'Low' or not folder_path or folder_path == 'Unknown':
                    folder_path = '00 - Staging/Review'
                    logger.info(f"  [Routing] Low confidence or unknown; routing to Review: {name}")

                target_id = resolve_folder_id(folder_path)
                if not target_id:
                    folder_path = '00 - Staging/Review'
                    target_id = resolve_folder_id(folder_path)
                    logger.warning(f"  [Routing] Target path unresolvable; routing to Review: {folder_path}")

                # 2. Rename (High/Medium only, otherwise keep name for review)
                final_name = name
                if new_name != name and confidence in ['High', 'Medium']:
                    try:
                        service.files().update(fileId=fid, body={'name': new_name}).execute()
                        stats.renamed += 1
                        log("FILE_RENAMED", "SUCCESS", f"Renamed {name} -> {new_name}", data={"file_id": fid}, app_name=stats.app_name)
                        final_name = new_name
                    except Exception as ren_err:
                        logger.error(f"  [Rename Error] {name}: {ren_err}")

                # 3. Deduplication Check
                if target_id and target_id != folder_id:
                    dup_id, dup_type = check_duplicate(service, target_id, final_name, checksum)
                    if dup_id:
                        logger.info(f"  [Dedup] Duplicate found in target ({dup_type}): {final_name}")
                        stats.swept += 1
                        log("FILE_SKIPPED", "INFO", f"Skipped duplicate {final_name}", data={"file_id": fid, "dup_id": dup_id}, app_name=stats.app_name)
                    else:
                        # 4. Move
                        if move_file(service, fid, target_id, final_name):
                            stats.moved += 1
                            stats._moved_fids.add(fid)
                            full_path = ID_TO_PATH.get(target_id, folder_path)
                            stats.move_details.append((name, final_name, full_path, fid))
                            log("FILE_MOVED", "SUCCESS", f"Moved {final_name} to {full_path}", data={
                                "file_id": fid,
                                "target_id": target_id,
                                "target_path": full_path
                            }, app_name=stats.app_name)
                            
                            # 5. Memory Integration (High/Medium only)
                            if confidence in ['High', 'Medium']:
                                post_process_memory(analysis, final_name, fid)

                # Update state cache
                state["analyzed_ids"][fid] = final_name

            stats.processed += 1
                
        except Exception as e:
            logger.error(f"  [Error] {name}: {e}")
            stats.errors += 1
            stats.error_details.append((name, str(e), fid))

def sweep_drive_root(dry_run=True, service=None, state=None):
    """Special mode to only look at root and move obvious stuff to Inbox."""
    if not service:
        service = get_drive_service()
    
    print("Sweeping Drive Root...")
    results = service.files().list(
        q="'root' in parents and trashed = false",
        fields="files(id, name, mimeType)"
    ).execute()
    files = results.get('files', [])
    
    for f in files:
        name = f['name']
        fid = f['id']
        mime = f['mimeType']
        
        if mime == 'application/vnd.google-apps.folder': continue
        
        # Obvious candidates for sorting (Receipts, PDFs, etc)
        if mime == 'application/pdf' or _ALREADY_NAMED.match(name):
            print(f"  [Sweep] Moving {name} to Inbox")
            if not dry_run:
                move_file(service, fid, INBOX_ID, name)
                stats.swept += 1

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Drive AI Sorter")
    parser.add_argument("--run", action="store_true", help="Actually execute moves/renames")
    parser.add_argument("--limit", type=int, help="Limit number of files to process")
    parser.add_argument("--recursive", action="store_true", help="Scan subfolders of Inbox")
    parser.add_argument(
        "--execute",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--inbox",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def run(argv=None):
    args = parse_args(argv)

    global stats
    stats = RunStats()
    
    state = load_state()
    service = get_drive_service()

    # 1. Sweep Root -> Inbox
    execute = args.run or args.execute
    sweep_drive_root(dry_run=not execute, service=service, state=state)

    # 2. Scan Inbox
    scan_folder(
        INBOX_ID, 
        dry_run=not execute,
        limit=args.limit, 
        mode='inbox', 
        service=service, 
        recursive=args.recursive,
        state=state
    )

    # 3. Finalize
    summary = stats.get_summary()
    print(f"\n{summary}")
    
    if execute:
        save_state(state)
        if stats.moved > 0 or stats.renamed > 0 or stats.swept > 0 or stats.errors > 0:
            send_message(stats.get_notification(), service="ai-sorter", category="notification")

if __name__ == '__main__':
    run()
