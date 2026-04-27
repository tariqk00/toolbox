#!/usr/bin/env python3
"""
One-time deduplication of existing Memory files.

Handles:
  - Memory/Travel.md         (dedup key: date + vendor + trip_type)
  - Memory/Orders/*.md       (dedup key: order_number from header; fallback: date + vendor)
  - Memory/Receipts/*.md     (dedup key: date + amount; fallback: date + vendor)

Run from toolbox root:
  source google-drive/venv/bin/activate
  PYTHONPATH=/home/tariqk/github/tariqk00 python3 bin/dedup_memory.py [--dry-run]

Outputs a summary of duplicates removed per file.
"""
import argparse
import io
import logging
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BASE_DIR)
for p in (BASE_DIR, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from toolbox.lib.drive_utils import get_drive_service
from toolbox.lib.telegram import send_message, escape
from googleapiclient.http import MediaIoBaseUpload

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger('dedup_memory')

MEMORY_ROOT_PATH = '01 - Second Brain/Memory'

# ── Drive helpers ────────────────────────────────────────────────────────────

def _resolve_folder(service, path: str) -> str:
    """Resolve a slash-separated path to a folder ID, starting from root."""
    parent = 'root'
    for part in path.strip('/').split('/'):
        q = (f"'{parent}' in parents and name = '{part}' "
             f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        results = service.files().list(q=q, fields='files(id)').execute()
        files = results.get('files', [])
        if not files:
            raise FileNotFoundError(f"Folder not found: {part} (under {parent})")
        parent = files[0]['id']
    return parent


def _list_md_files(service, folder_id: str) -> list[dict]:
    """Return all .md files in folder_id as list of {id, name}."""
    q = f"'{folder_id}' in parents and name contains '.md' and trashed = false"
    results = service.files().list(q=q, fields='files(id, name)').execute()
    return results.get('files', [])


def _download(service, file_id: str) -> str:
    raw = service.files().get_media(fileId=file_id).execute()
    return raw.decode('utf-8') if isinstance(raw, bytes) else raw


def _upload(service, file_id: str, content: str, dry_run: bool) -> None:
    if dry_run:
        return
    media = MediaIoBaseUpload(io.BytesIO(content.encode()), mimetype='text/markdown')
    service.files().update(fileId=file_id, media_body=media).execute()


# ── Block parsing ────────────────────────────────────────────────────────────

def _split_blocks(content: str) -> list[str]:
    """Split content into blocks by '---' separator.

    Strips orphaned leading '↳ ...' lines from each block — these were appended
    by old orders.py after a separator, and land before the next block's '##' header,
    breaking key extraction.
    """
    blocks = re.split(r'\n---\n?', content)
    result = []
    for b in blocks:
        b = b.strip()
        if not b or b == '---':
            continue
        # Drop any ↳ lines orphaned at the start of a block
        lines = b.splitlines()
        while lines and lines[0].startswith('↳'):
            lines.pop(0)
        b = '\n'.join(lines).strip()
        if b:
            result.append(b)
    return result


def _rejoin(blocks: list[str]) -> str:
    return '\n---\n'.join(blocks) + '\n---\n'


# ── Dedup key extractors ─────────────────────────────────────────────────────

def _travel_key(block: str) -> str:
    """(date, vendor, trip_type) from a Travel.md block."""
    date = ''
    vendor = ''
    trip_type = ''

    m = re.match(r'## (\d{4}-\d{2}-\d{2}) — ([A-Za-z ]+)', block)
    if m:
        date = m.group(1)
        trip_type = m.group(2).strip().split(' — ')[0].strip()

    mv = re.search(r'\*\*Vendor:\*\* (.+)', block)
    if mv:
        vendor = mv.group(1).strip()

    return f'{date}|{vendor}|{trip_type}'


def _order_key(block: str) -> str:
    """Order number from header; fallback: date + vendor."""
    m = re.match(r'## (\d{4}-\d{2}-\d{2}) — Order #([^\s\[]+)', block)
    if m:
        return f'order|{m.group(2)}'

    date = ''
    vendor = ''
    md = re.match(r'## (\d{4}-\d{2}-\d{2})', block)
    if md:
        date = md.group(1)
    mv = re.search(r'\*\*Vendor:\*\* (.+)', block)
    if mv:
        vendor = mv.group(1).strip()
    return f'date-vendor|{date}|{vendor}'


def _receipt_key(block: str) -> str:
    """Date + amount; fallback: date + vendor."""
    date = ''
    amount = ''
    vendor = ''

    md = re.match(r'## (\d{4}-\d{2}-\d{2})', block)
    if md:
        date = md.group(1)
    ma = re.search(r'\*\*Amount:\*\* (.+)', block)
    if ma:
        amount = ma.group(1).strip()
    mv = re.search(r'\*\*Vendor:\*\* (.+)', block)
    if mv:
        vendor = mv.group(1).strip()

    if amount:
        return f'{date}|{amount}'
    return f'{date}|{vendor}'


# ── Core dedup ───────────────────────────────────────────────────────────────

def dedup_content(content: str, key_fn) -> tuple[str, int]:
    """
    Return (deduped_content, n_removed).
    Keeps the first occurrence of each key; discards subsequent duplicates.
    """
    blocks = _split_blocks(content)
    seen: dict[str, int] = {}
    kept = []
    removed = 0

    for block in blocks:
        key = key_fn(block)
        if key in seen:
            logger.debug(f'  Removing duplicate block (key={key!r})')
            removed += 1
        else:
            seen[key] = 1
            kept.append(block)

    return _rejoin(kept), removed


# ── Per-category runners ─────────────────────────────────────────────────────

def dedup_file(service, file_id: str, filename: str, key_fn, dry_run: bool) -> int:
    """Download, dedup, and re-upload one file. Returns number of blocks removed."""
    content = _download(service, file_id)
    if not content.strip():
        return 0
    cleaned, removed = dedup_content(content, key_fn)
    if removed:
        logger.info(f'  {filename}: {removed} duplicate(s) removed'
                    + (' [dry-run, not uploading]' if dry_run else ''))
        _upload(service, file_id, cleaned, dry_run)
    return removed


def run_travel(service, dry_run: bool) -> dict:
    logger.info('--- Travel.md ---')
    folder_id = _resolve_folder(service, MEMORY_ROOT_PATH)
    files = _list_md_files(service, folder_id)
    travel = next((f for f in files if f['name'] == 'Travel.md'), None)
    if not travel:
        logger.info('  Travel.md not found, skipping')
        return {}
    removed = dedup_file(service, travel['id'], 'Travel.md', _travel_key, dry_run)
    return {'Travel.md': removed}


def run_orders(service, dry_run: bool) -> dict:
    logger.info('--- Orders/ ---')
    try:
        folder_id = _resolve_folder(service, f'{MEMORY_ROOT_PATH}/Orders')
    except FileNotFoundError:
        logger.info('  Orders/ folder not found, skipping')
        return {}
    files = _list_md_files(service, folder_id)
    results = {}
    for f in files:
        removed = dedup_file(service, f['id'], f['name'], _order_key, dry_run)
        results[f['name']] = removed
    return results


def run_receipts(service, dry_run: bool) -> dict:
    logger.info('--- Receipts/ ---')
    try:
        folder_id = _resolve_folder(service, f'{MEMORY_ROOT_PATH}/Receipts')
    except FileNotFoundError:
        logger.info('  Receipts/ folder not found, skipping')
        return {}
    files = _list_md_files(service, folder_id)
    results = {}
    for f in files:
        removed = dedup_file(service, f['id'], f['name'], _receipt_key, dry_run)
        results[f['name']] = removed
    return results


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Deduplicate Memory files in Drive')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be removed without uploading')
    parser.add_argument('--travel-only', action='store_true')
    parser.add_argument('--orders-only', action='store_true')
    parser.add_argument('--receipts-only', action='store_true')
    args = parser.parse_args()

    service = get_drive_service()
    total_removed = 0
    all_results = {}

    run_all = not (args.travel_only or args.orders_only or args.receipts_only)

    if run_all or args.travel_only:
        r = run_travel(service, args.dry_run)
        all_results.update(r)
        total_removed += sum(r.values())

    if run_all or args.orders_only:
        r = run_orders(service, args.dry_run)
        all_results.update(r)
        total_removed += sum(r.values())

    if run_all or args.receipts_only:
        r = run_receipts(service, args.dry_run)
        all_results.update(r)
        total_removed += sum(r.values())

    print()
    print('=== Dedup summary ===')
    
    html_lines = ["<b>🧹 Memory Dedup Complete</b>"]
    files_modified = 0
    
    for filename, removed in sorted(all_results.items()):
        if removed:
            msg = f'{filename}: {removed} duplicate(s) removed'
            print(f'  {msg}' + (' (dry-run)' if args.dry_run else ''))
            html_lines.append(f"• <i>{escape(filename)}</i>: {removed} removed")
            files_modified += 1
            
    if total_removed == 0:
        print('  No duplicates found.')
    else:
        print(f'\n  Total: {total_removed} block(s) removed across {files_modified} file(s)')
        html_lines.append(f"\n<b>Total:</b> {total_removed} blocks across {files_modified} files")
        
    if args.dry_run:
        print('  [dry-run: no files were modified]')
        
    # Send rich telegram message (spam deduped by skipping if 0 removed)
    if total_removed > 0 and not args.dry_run:
        html_body = "\n".join(html_lines)
        send_message(html_body, service="memory-dedup")


if __name__ == '__main__':
    main()
