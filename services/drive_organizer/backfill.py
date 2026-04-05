"""
AI Drive Sorter — Backfill Job.
Processes Drive files that predate or were missed by the hourly inbox sorter.
Quota-aware, resumable across nights, Telegram-notified.

Usage:
  python backfill.py --count-only   # survey all folders, print scope, no Gemini
  python backfill.py --dry-run      # process but don't rename/move
  python backfill.py --limit 50     # cap files this run (default from quota_state)
  python backfill.py                # real run
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

# Ensure toolbox is on path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.lib.ai_engine import analyze_with_gemini, get_ai_supported_mime
from toolbox.lib import quota_manager
from toolbox.lib.telegram import send_message
from toolbox.lib.drive_utils import (
    get_drive_service, get_sheets_service,
    download_file_content, move_file,
    get_folder_path, resolve_folder_id,
    get_category_prompt_str,
    INBOX_ID, HISTORY_SHEET_ID, CONFIG_PATH,
)

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
STATE_PATH = os.path.join(CONFIG_DIR, 'backfill_state.json')
CACHE_PATH = os.path.join(CONFIG_DIR, 'gemini_cache.json')
TREE_PATH  = os.path.join(CONFIG_DIR, 'drive_tree.json')
LOG_FILE   = os.path.join(BASE_DIR, 'logs', 'backfill.log')

VALID_NAME_RE = re.compile(r'^\d{4}-\d{2}-\d{2} - .+ - .+\.\w+$')
MIDNIGHT_BUFFER_SECS = 300  # stop 5 min before midnight

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("DriveSorter.Backfill")
fh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
fh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
logger.addHandler(fh)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read backfill_state.json: {e}")
    return {"pending": [], "completed_ids": [], "last_run": None, "total_processed": 0}


def save_state(state: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


# ---------------------------------------------------------------------------
# Sheet logging (mirrors main.py logic)
# ---------------------------------------------------------------------------

def log_to_sheet(timestamp, file_id, original_name, new_name, target_folder_id, target_folder_name, run_type):
    if not HISTORY_SHEET_ID:
        return
    safe_new_name = new_name.replace('"', '""')
    link_file = f'=HYPERLINK("https://drive.google.com/open?id={file_id}", "{safe_new_name}")'
    safe_target_name = target_folder_name.replace('"', '""')
    if target_folder_id and target_folder_id not in ["None", "Unknown"]:
        link_folder = f'=HYPERLINK("https://drive.google.com/drive/u/0/folders/{target_folder_id}", "{safe_target_name}")'
    else:
        link_folder = target_folder_name
    try:
        svc = get_sheets_service()
        svc.spreadsheets().values().append(
            spreadsheetId=HISTORY_SHEET_ID, range="Log!A:A",
            valueInputOption="USER_ENTERED",
            body={'values': [[timestamp, file_id, original_name, link_file, link_folder, run_type]]}
        ).execute()
    except Exception as e:
        logger.error(f"  [Log Error] Failed to write to Sheet: {e}")


# ---------------------------------------------------------------------------
# Name generation (mirrors main.py logic)
# ---------------------------------------------------------------------------

def generate_new_name(analysis: dict, original_name: str, created_time_str: str) -> str:
    ext = os.path.splitext(original_name)[1]
    date = analysis.get('doc_date', '0000-00-00')
    if date == '0000-00-00':
        match = re.search(r'(\d{4}-\d{2}-\d{2})', original_name)
        if match:
            date = match.group(1)
        elif created_time_str:
            date = created_time_str[:10]

    entity  = str(analysis.get('entity') or 'Unknown')
    summary = str(analysis.get('summary') or 'Doc')
    safe_entity  = re.sub(r'[^\w\s\-]', '', entity).strip().replace(' ', '_')
    safe_summary = re.sub(r'[^\w\s\-]', '', summary).strip().replace(' ', '_')

    if date in ('0000-00-00', '', None):
        safe_summary += '_(NoDate)'

    person = analysis.get('person')
    if person and str(person).strip().capitalize() in {'Dawn', 'Thomas', 'Sofia'}:
        return f"{date} - {safe_entity} - {person.strip().capitalize()} - {safe_summary}{ext}"

    return f"{date} - {safe_entity} - {safe_summary}{ext}"


# ---------------------------------------------------------------------------
# Queue building
# ---------------------------------------------------------------------------

# Subtrees within backfill_extra_roots that should not be processed.
# These are raw data dumps (exports, sensor data, asset archives) with no
# document-like content worth renaming.
BACKFILL_EXCLUDE_PREFIXES = [
    '09 - Archive/Source_Dumps',   # Garmin takeouts, Health Sync CSVs, Readwise/Logseq exports
    '05 - Media/Google Photos',    # ~14K year-sorted photos (1988–2019); not document-like
    '05 - Media/QNAP831X',         # NAS backup mirror; raw files, not for renaming
]


def build_extra_folder_map(service) -> dict:
    """Crawl backfill_extra_roots (Media, Archive) and return a path→id map."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    extra_roots = config.get('backfill_extra_roots', [])
    top_level = config.get('top_level_folders', {})

    # Build reverse map: id → name
    id_to_name = {v['id']: k for k, v in top_level.items()}

    path_to_id = {}
    for root_id in extra_roots:
        root_name = id_to_name.get(root_id, root_id)
        _crawl_for_backfill(service, root_id, root_name, path_to_id)
    return path_to_id


def _crawl_for_backfill(service, folder_id, path, path_to_id):
    if any(path.startswith(p) for p in BACKFILL_EXCLUDE_PREFIXES):
        logger.debug(f"  [Skip] Excluded subtree: {path}")
        return
    path_to_id[path] = folder_id
    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            pageSize=200
        ).execute()
        for child in results.get('files', []):
            _crawl_for_backfill(service, child['id'], f"{path}/{child['name']}", path_to_id)
    except Exception as e:
        logger.error(f"Error crawling {path}: {e}")


def build_queue(service) -> list:
    """Crawl all Drive folders and return list of unprocessed file dicts."""
    with open(TREE_PATH) as f:
        tree_data = json.load(f)
    with open(CACHE_PATH) as f:
        cache = json.load(f)

    path_to_id = dict(tree_data['path_to_id'])

    # Also include Media and Archive (excluded from tree/routing but backfill should cover them)
    extra = build_extra_folder_map(service)
    path_to_id.update(extra)
    logger.info(f"Tree folders: {len(tree_data['path_to_id'])}, extra (Media/Archive): {len(extra)}")

    pending = []

    for folder_path in sorted(path_to_id.keys()):
        folder_id = path_to_id[folder_path]
        if folder_id == INBOX_ID:
            continue  # handled by hourly sorter

        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                fields="files(id, name, mimeType, createdTime)",
                pageSize=1000
            ).execute()
            files = results.get('files', [])
        except Exception as e:
            logger.error(f"Error listing {folder_path}: {e}")
            continue

        # Oldest files first within each folder
        files.sort(key=lambda f: f.get('createdTime', ''))

        for f in files:
            fid  = f['id']
            name = f['name']
            mime = f['mimeType']

            if fid in cache:
                continue
            if VALID_NAME_RE.match(name) and not name.startswith('0000'):
                continue

            # Skip if unsupported mime AND no rule-based shortcut would apply
            is_rule_based = (
                name.lower().endswith('summary.txt') or
                name.lower().endswith('transcript.txt') or
                ' - Journal - ' in name or
                bool(re.match(r'^\d{2}-\d{2}\s', name))
            )
            if not is_rule_based and get_ai_supported_mime(mime, name) is None:
                logger.debug(f"  [Skip] Unsupported mime at queue time: {name} ({mime})")
                continue

            pending.append({
                "id": fid,
                "name": name,
                "mimeType": f['mimeType'],
                "createdTime": f.get('createdTime', ''),
                "folder_id": folder_id,
                "folder_path": folder_path,
            })

    logger.info(f"Queue built: {len(pending)} files across all folders")
    return pending


# ---------------------------------------------------------------------------
# Count-only mode
# ---------------------------------------------------------------------------

def count_only(service) -> None:
    with open(TREE_PATH) as f:
        tree_data = json.load(f)
    with open(CACHE_PATH) as f:
        cache = json.load(f)

    path_to_id = dict(tree_data['path_to_id'])
    extra = build_extra_folder_map(service)
    path_to_id.update(extra)
    print(f"\n{'Folder':<55} {'Total':>6} {'Cached':>7} {'Named':>6} {'Todo':>6}")
    print("-" * 85)

    grand_total = grand_cached = grand_named = grand_todo = 0

    for path in sorted(path_to_id.keys()):
        folder_id = path_to_id[path]
        if folder_id == INBOX_ID:
            continue
        try:
            results = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                fields="files(id, name)",
                pageSize=1000
            ).execute()
            files = results.get('files', [])
        except Exception as e:
            print(f"  ERROR {path}: {e}")
            continue

        total  = len(files)
        cached = sum(1 for f in files if f['id'] in cache)
        named  = sum(1 for f in files if VALID_NAME_RE.match(f['name']) and not f['name'].startswith('0000'))
        todo   = sum(1 for f in files if f['id'] not in cache and not (VALID_NAME_RE.match(f['name']) and not f['name'].startswith('0000')))

        if total > 0:
            indent = "  " * path.count('/')
            label = indent + path.split('/')[-1]
            print(f"{label:<55} {total:>6} {cached:>7} {named:>6} {todo:>6}")

        grand_total += total; grand_cached += cached
        grand_named += named; grand_todo += todo

    print("-" * 85)
    print(f"{'TOTAL':<55} {grand_total:>6} {grand_cached:>7} {grand_named:>6} {grand_todo:>6}")
    print(f"\nBackfill queue estimate: ~{grand_todo} files to process")


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def secs_until_midnight() -> int:
    now = datetime.now()
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return max(0, int((midnight - now).total_seconds()))


def near_midnight() -> bool:
    return secs_until_midnight() < MIDNIGHT_BUFFER_SECS


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(args):
    start = time.time()
    dry_run = args.dry_run
    service = get_drive_service()

    if args.count_only:
        count_only(service)
        return

    state = load_state()

    # Check quota
    if quota_manager.is_budget_exhausted():
        msg = f"Daily quota exhausted ({quota_manager.load()['total_tokens_used']:,} tokens used). Skipping run."
        logger.info(msg)
        send_message(msg, service="ai-sorter-backfill")
        return

    # Build queue if empty
    if not state['pending']:
        logger.info("Pending queue empty — crawling Drive to build queue...")
        state['pending'] = build_queue(service)
        save_state(state)
        if not state['pending']:
            msg = "Backfill complete — no files left to process."
            logger.info(msg)
            send_message(msg, service="ai-sorter-backfill")
            return

    limit = args.limit or quota_manager.load().get('files_per_run', quota_manager.FILES_PER_RUN)
    folder_paths_str = get_category_prompt_str()

    processed = moved = renamed = errors = 0
    move_details = []   # (original, new_name, folder_path)
    rename_details = [] # (original, new_name)
    error_details = []  # (name, error_str)
    moved_fids = set()

    logger.info(f"Starting backfill run: {len(state['pending'])} queued, limit={limit}, dry_run={dry_run}")

    while state['pending'] and processed < limit:
        if quota_manager.is_budget_exhausted():
            logger.info("Quota exhausted mid-run, stopping.")
            break
        if near_midnight():
            logger.info("Approaching midnight, stopping to preserve quota boundary.")
            break

        item = state['pending'].pop(0)
        fid  = item['id']
        name = item['name']
        mime = item['mimeType']
        folder_id   = item['folder_id']
        folder_path = item['folder_path']

        try:
            content = download_file_content(service, fid, mime)
            if not content:
                state['completed_ids'].append(fid)
                save_state(state)
                continue

            context_hint = f"File in folder: {folder_path}. Created: {item.get('createdTime', '')}"
            analysis, tokens = analyze_with_gemini(content, mime, name, folder_paths_str, context_hint, file_id=fid)
            if tokens:
                quota_manager.record_tokens(tokens)

            new_name   = generate_new_name(analysis, name, item.get('createdTime', ''))
            confidence = analysis.get('confidence', 'Low')
            folder_target = analysis.get('folder_path')

            logger.info(f"  [AI] {name} -> {new_name} ({confidence})")

            if not dry_run:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")

                if new_name != name and confidence in ('High', 'Medium'):
                    service.files().update(fileId=fid, body={'name': new_name}).execute()
                    renamed += 1
                    logger.info(f"  [Renamed] {new_name}")
                    target_id_for_log = resolve_folder_id(folder_target) or 'Unknown'
                    target_path_for_log = get_folder_path(service, target_id_for_log) if target_id_for_log != 'Unknown' else folder_path
                    log_to_sheet(ts, fid, name, new_name, target_id_for_log, target_path_for_log, f'Backfill-Rename ({confidence})')

                target_id = resolve_folder_id(folder_target)
                if confidence == 'High' and target_id and target_id != folder_id:
                    if move_file(service, fid, target_id, new_name):
                        moved += 1
                        moved_fids.add(fid)
                        full_path = get_folder_path(service, target_id)
                        move_details.append((name, new_name, folder_target or folder_path))
                        logger.info(f"  [Moved] -> {folder_target}")
                        if new_name == name:
                            log_to_sheet(ts, fid, name, new_name, target_id, full_path, 'Backfill-Move')

                if new_name != name and confidence == 'Medium' and fid not in moved_fids:
                    rename_details.append((name, new_name))

            processed += 1
            state['completed_ids'].append(fid)
            state['total_processed'] = state.get('total_processed', 0) + 1
            save_state(state)

        except Exception as e:
            logger.error(f"  [Error] {name}: {e}")
            errors += 1
            error_details.append((name, str(e)))
            state['completed_ids'].append(fid)
            save_state(state)

    elapsed = int(time.time() - start)
    remaining_queue = len(state['pending'])
    tokens_used = quota_manager.load().get('total_tokens_used', 0)

    state['last_run'] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    logger.info(f"Run complete: {processed} processed, {moved} moved, {renamed} renamed, {errors} errors — {remaining_queue} remaining in queue")

    # Build Telegram summary
    summary_parts = []
    if moved:    summary_parts.append(f"{moved} moved")
    if renamed:  summary_parts.append(f"{renamed} renamed")
    if errors:   summary_parts.append(f"{errors} error{'s' if errors > 1 else ''}")
    if not summary_parts:
        summary_parts.append(f"{processed} processed (no changes)")

    lines = [f"{', '.join(summary_parts)} ({elapsed}s) — {remaining_queue} files remaining"]
    lines.append(f"Quota: {tokens_used:,} / {quota_manager.load().get('daily_budget', quota_manager.DAILY_BUDGET):,} tokens used today")

    MAX = 10
    detail_lines = []
    for orig, new, folder in move_details:
        detail_lines.append(f"  Moved: {orig}\n    → {folder}/{new}")
    for orig, new in rename_details:
        detail_lines.append(f"  Renamed: {orig}\n    → {new}")
    for name, err in error_details:
        detail_lines.append(f"  Error: {name}\n    {err}")
    lines.extend(detail_lines[:MAX])
    if len(detail_lines) > MAX:
        lines.append(f"  ... and {len(detail_lines) - MAX} more")

    send_message("\n".join(lines), service="ai-sorter-backfill")


def parse_args():
    parser = argparse.ArgumentParser(description="AI Drive Sorter — Backfill Job")
    parser.add_argument('--count-only', action='store_true', help="Survey folders and print scope; no Gemini calls")
    parser.add_argument('--dry-run',    action='store_true', help="Analyze files but don't rename or move")
    parser.add_argument('--limit',      type=int, default=0, help="Max files to process this run (default: from quota_state)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args)
