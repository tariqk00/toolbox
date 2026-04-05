"""
Reset email extractor memory files in Drive and local state.
Deletes all markdown files under 01 - Second Brain/Memory/ and clears state.json.
Run once before a clean test.
"""
import json
import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger('reset_memory')

from toolbox.lib.drive_utils import get_drive_service

MEMORY_ROOT = '01 - Second Brain/Memory'
STATE_FILE = os.path.join(BASE_DIR, 'config', 'email_extractor_state.json')


def _find_folder(service, name: str, parent_id: str) -> str | None:
    query = (
        f"'{parent_id}' in parents and name = '{name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def _resolve_path(service, path: str) -> str | None:
    parts = path.strip('/').split('/')
    parent_id = 'root'
    for part in parts:
        fid = _find_folder(service, part, parent_id)
        if not fid:
            return None
        parent_id = fid
    return parent_id


def _list_md_files(service, folder_id: str) -> list[dict]:
    """Recursively list all .md files under folder_id."""
    found = []
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields='files(id,name,mimeType)').execute()
    for f in results.get('files', []):
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            found.extend(_list_md_files(service, f['id']))
        elif f['name'].endswith('.md'):
            found.append(f)
    return found


def run():
    service = get_drive_service()

    memory_id = _resolve_path(service, MEMORY_ROOT)
    if not memory_id:
        logger.info(f'Memory folder not found at {MEMORY_ROOT} — nothing to delete')
    else:
        files = _list_md_files(service, memory_id)
        if not files:
            logger.info('No markdown files found in Memory folder')
        else:
            for f in files:
                service.files().delete(fileId=f['id']).execute()
                logger.info(f"Deleted: {f['name']}")
            logger.info(f'Deleted {len(files)} files')

    # Reset state — remove run history and dedup state, keep nothing
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
        logger.info(f'Deleted state file: {STATE_FILE}')
    else:
        logger.info('No state file to delete')

    logger.info('Reset complete — next run will be treated as first run')


if __name__ == '__main__':
    run()
