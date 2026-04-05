"""
Drive markdown writer for the email extraction pipeline.
Writes to 01 - Second Brain/Memory/{category}/{filename}.md
Appends to existing files (download → append → re-upload).
"""
import io
import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from googleapiclient.http import MediaIoBaseUpload
from toolbox.lib.drive_utils import get_drive_service

logger = logging.getLogger('EmailExtractor.Writers')

MEMORY_ROOT = '01 - Second Brain/Memory'

_folder_cache: dict[str, str] = {}


def _find_or_create_folder(service, name: str, parent_id: str) -> str:
    cache_key = f'{parent_id}/{name}'
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]

    query = (
        f"'{parent_id}' in parents and name = '{name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    if files:
        fid = files[0]['id']
    else:
        meta = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id],
        }
        fid = service.files().create(body=meta, fields='id').execute()['id']
        logger.info(f'Created folder: {name} under {parent_id}')

    _folder_cache[cache_key] = fid
    return fid


def _resolve_path(service, path: str) -> str:
    """Resolve a Drive path like '01 - Second Brain/Memory/Orders' to a folder ID."""
    parts = path.strip('/').split('/')
    parent_id = 'root'
    for part in parts:
        parent_id = _find_or_create_folder(service, part, parent_id)
    return parent_id


def _get_file_in_folder(service, folder_id: str, filename: str) -> str | None:
    """Return file ID if filename exists in folder, else None."""
    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def update_in_memory(category: str, filename: str, old_text: str, new_text: str) -> bool:
    """
    Replace old_text with new_text in an existing memory file.
    Returns True if the text was found and replaced, False if not found.
    """
    service = get_drive_service()
    folder_path = f'{MEMORY_ROOT}/{category}' if category else MEMORY_ROOT
    folder_id = _resolve_path(service, folder_path)
    file_id = _get_file_in_folder(service, folder_id, filename)
    if not file_id:
        return False
    existing_bytes = service.files().get_media(fileId=file_id).execute()
    existing = existing_bytes.decode('utf-8') if isinstance(existing_bytes, bytes) else existing_bytes
    if old_text not in existing:
        return False
    updated = existing.replace(old_text, new_text, 1)
    media = MediaIoBaseUpload(io.BytesIO(updated.encode()), mimetype='text/markdown')
    service.files().update(fileId=file_id, media_body=media).execute()
    logger.info(f'Updated {category or "Memory"}/{filename}')
    return True


def append_to_memory(category: str, filename: str, new_content: str) -> None:
    """
    Append new_content to Memory/{category}/{filename}.
    category: e.g. 'Orders', 'Receipts', 'Digests' (or None for Travel.md at Memory root)
    filename: e.g. 'Amazon.md'
    """
    service = get_drive_service()

    if category:
        folder_path = f'{MEMORY_ROOT}/{category}'
    else:
        folder_path = MEMORY_ROOT

    folder_id = _resolve_path(service, folder_path)
    file_id = _get_file_in_folder(service, folder_id, filename)

    if file_id:
        existing_bytes = service.files().get_media(fileId=file_id).execute()
        existing = existing_bytes.decode('utf-8') if isinstance(existing_bytes, bytes) else existing_bytes
        full_content = existing.rstrip('\n') + '\n\n' + new_content
        media = MediaIoBaseUpload(io.BytesIO(full_content.encode()), mimetype='text/markdown')
        service.files().update(fileId=file_id, media_body=media).execute()
        logger.info(f'Updated {category}/{filename}')
    else:
        media = MediaIoBaseUpload(io.BytesIO(new_content.encode()), mimetype='text/markdown')
        meta = {'name': filename, 'parents': [folder_id]}
        service.files().create(body=meta, media_body=media, fields='id').execute()
        logger.info(f'Created {category}/{filename}')
