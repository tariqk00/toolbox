"""
Drive dedup utility.

Two modes:

  --folder PATH
      Within-folder dedup. Groups files by name; within each name group,
      keeps the newest (by modifiedTime) and trashes the rest.
      Useful for removing duplicates caused by two services writing to the
      same folder with the same filename pattern.

  --source PATH --target PATH
      Cross-folder consolidation. For each file in source:
        - If target has a file with the same name → trash source copy
          (target is canonical).
        - Otherwise → move source file to target.
      After all files are processed, if source folder is empty it is trashed.

Dry-run by default. Pass --execute to apply changes.

Usage:
  python3 -m toolbox.bin.dedup_drive --folder "01 - Second Brain/Plaud"
  python3 -m toolbox.bin.dedup_drive --source "Filing Cabinet/Plaud" \\
      --target "01 - Second Brain/Plaud"
  python3 -m toolbox.bin.dedup_drive --folder "01 - Second Brain/Plaud" --execute
"""
import argparse
import logging
import os
import sys
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from toolbox.lib.drive_utils import get_drive_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('dedup_drive')


# ── Drive helpers ─────────────────────────────────────────────────────────────

def resolve_path(service, path: str) -> str:
    """Walk a slash-separated path from Drive root, return folder ID."""
    parts = path.strip('/').split('/')
    parent_id = 'root'
    for part in parts:
        q = (
            f"name = '{part}'"
            f" and mimeType = 'application/vnd.google-apps.folder'"
            f" and '{parent_id}' in parents"
            f" and trashed = false"
        )
        res = service.files().list(q=q, spaces='drive', fields='files(id, name)').execute()
        files = res.get('files', [])
        if not files:
            raise ValueError(f"Folder not found: '{part}' (in path '{path}')")
        parent_id = files[0]['id']
    return parent_id


def list_files(service, folder_id: str) -> list[dict]:
    """List all non-trashed files (not folders) in a folder, handling pagination."""
    results = []
    page_token = None
    while True:
        kwargs = dict(
            q=f"'{folder_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
            fields='nextPageToken, files(id, name, md5Checksum, modifiedTime, size)',
            pageSize=200,
        )
        if page_token:
            kwargs['pageToken'] = page_token
        resp = service.files().list(**kwargs).execute()
        results.extend(resp.get('files', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return results


def trash_file(service, file_id: str, execute: bool) -> None:
    if execute:
        service.files().update(fileId=file_id, body={'trashed': True}).execute()


def move_file(service, file_id: str, source_id: str, target_id: str, execute: bool) -> None:
    if execute:
        service.files().update(
            fileId=file_id,
            addParents=target_id,
            removeParents=source_id,
            fields='id, parents',
        ).execute()


def folder_is_empty(service, folder_id: str) -> bool:
    res = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields='files(id)',
        pageSize=1,
    ).execute()
    return len(res.get('files', [])) == 0


# ── Modes ─────────────────────────────────────────────────────────────────────

def dedup_within_folder(service, folder_path: str, execute: bool) -> None:
    """
    Group files in folder by name. Keep newest, trash rest.
    """
    logger.info(f'Resolving folder: {folder_path}')
    folder_id = resolve_path(service, folder_path)
    logger.info(f'Folder ID: {folder_id}')

    files = list_files(service, folder_id)
    logger.info(f'Found {len(files)} files')

    by_name: dict[str, list[dict]] = defaultdict(list)
    for f in files:
        by_name[f['name']].append(f)

    dup_groups = {name: group for name, group in by_name.items() if len(group) > 1}
    logger.info(f'{len(dup_groups)} name groups with duplicates')

    if not dup_groups:
        logger.info('No duplicates found.')
        return

    trashed = 0
    for name, group in sorted(dup_groups.items()):
        # Sort by modifiedTime descending — keep first (newest)
        group_sorted = sorted(group, key=lambda f: f.get('modifiedTime', ''), reverse=True)
        keeper = group_sorted[0]
        rest = group_sorted[1:]
        logger.info(
            f'[DUP] {name!r} — {len(group)} copies'
            f' | keep {keeper["modifiedTime"][:10]}'
            f' | trash {len(rest)}'
        )
        for f in rest:
            logger.info(f'  {"TRASH" if execute else "would trash"}: {f["id"]} ({f.get("modifiedTime", "")[:10]})')
            trash_file(service, f['id'], execute)
            trashed += 1

    action = 'Trashed' if execute else 'Would trash'
    logger.info(f'{action} {trashed} duplicate files.')


def consolidate_folders(service, source_path: str, target_path: str, execute: bool) -> None:
    """
    For each file in source:
      - If target has same name → trash source (target is canonical).
      - Otherwise → move to target.
    If source is empty after, trash it.
    """
    logger.info(f'Resolving source: {source_path}')
    source_id = resolve_path(service, source_path)
    logger.info(f'Resolving target: {target_path}')
    target_id = resolve_path(service, target_path)

    source_files = list_files(service, source_id)
    target_files = list_files(service, target_id)
    logger.info(f'Source: {len(source_files)} files | Target: {len(target_files)} files')

    target_names: set[str] = {f['name'] for f in target_files}

    trashed = moved = 0
    for f in sorted(source_files, key=lambda x: x['name']):
        name = f['name']
        if name in target_names:
            logger.info(f'  {"TRASH" if execute else "would trash"} (exists in target): {name}')
            trash_file(service, f['id'], execute)
            trashed += 1
        else:
            logger.info(f'  {"MOVE" if execute else "would move"}: {name}')
            move_file(service, f['id'], source_id, target_id, execute)
            moved += 1

    action = '' if execute else ' (dry-run)'
    logger.info(f'{action} Done: {trashed} trashed, {moved} moved.')

    if execute and folder_is_empty(service, source_id):
        logger.info(f'Source folder is now empty — trashing it: {source_path}')
        trash_file(service, source_id, execute=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Google Drive dedup / consolidation utility')
    parser.add_argument('--folder', help='Path to folder for within-folder dedup')
    parser.add_argument('--source', help='Source folder path (consolidation mode)')
    parser.add_argument('--target', help='Target folder path (consolidation mode)')
    parser.add_argument('--execute', action='store_true', default=False,
                        help='Apply changes (default: dry-run)')
    args = parser.parse_args()

    if not args.folder and not (args.source and args.target):
        parser.error('Provide either --folder or both --source and --target')
    if args.folder and (args.source or args.target):
        parser.error('--folder and --source/--target are mutually exclusive')

    mode = 'DRY-RUN' if not args.execute else 'EXECUTE'
    logger.info(f'Mode: {mode}')

    service = get_drive_service()

    if args.folder:
        dedup_within_folder(service, args.folder, args.execute)
    else:
        consolidate_folders(service, args.source, args.target, args.execute)


if __name__ == '__main__':
    main()
