"""
Drive markdown writer for the email extraction pipeline.
Writes to 01 - Second Brain/Memory/{category}/{filename}.md
Appends to existing files (download → append → re-upload).
"""
import io
import logging
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from googleapiclient.http import MediaIoBaseUpload
from toolbox.lib.drive_utils import get_drive_service, escape_query_string
from toolbox.lib.log_manager import LogManager

# Initialize centralized logger
log_manager = LogManager.get_instance('email-extractor')
logger = log_manager.logger

MEMORY_ROOT = '01 - Second Brain/Memory'

_folder_cache: dict[str, str] = {}


def _find_or_create_folder(service, name: str, parent_id: str) -> str:
    cache_key = f'{parent_id}/{name}'
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]

    safe_name = escape_query_string(name)
    query = (
        f"'{parent_id}' in parents and name = '{safe_name}' "
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
    safe_filename = escape_query_string(filename)
    query = f"'{folder_id}' in parents and name = '{safe_filename}' and trashed = false"
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def get_memory_content(category: str | None, filename: str) -> str:
    """
    Download and return the current text content of a Memory file.
    Returns '' if the file doesn't exist yet.
    """
    service = get_drive_service()
    folder_path = f'{MEMORY_ROOT}/{category}' if category else MEMORY_ROOT
    folder_id = _resolve_path(service, folder_path)
    file_id = _get_file_in_folder(service, folder_id, filename)
    if not file_id:
        return ''
    existing_bytes = service.files().get_media(fileId=file_id).execute()
    return existing_bytes.decode('utf-8') if isinstance(existing_bytes, bytes) else existing_bytes


def list_memory_files(category: str | None) -> dict[str, str]:
    """Return {filename: file_id} for all files in a memory folder."""
    service = get_drive_service()
    folder_path = f'{MEMORY_ROOT}/{category}' if category else MEMORY_ROOT
    folder_id = _resolve_path(service, folder_path)
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields='files(id, name)').execute()
    return {f['name']: f['id'] for f in results.get('files', [])}


def set_memory_content(category: str | None, filename: str, content: str) -> None:
    """Create or replace the full contents of a Memory file."""
    service = get_drive_service()
    folder_path = f'{MEMORY_ROOT}/{category}' if category else MEMORY_ROOT
    folder_id = _resolve_path(service, folder_path)
    file_id = _get_file_in_folder(service, folder_id, filename)
    media = MediaIoBaseUpload(io.BytesIO(content.encode()), mimetype='text/markdown')

    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
        logger.info(f'Set {category or "Memory"}/{filename}')
    else:
        meta = {'name': filename, 'parents': [folder_id]}
        service.files().create(body=meta, media_body=media, fields='id').execute()
        logger.info(f'Created {category or "Memory"}/{filename}')


def block_exists(content: str, date: str, *identifiers: str) -> bool:
    """
    Return True if `content` already contains a markdown block (separated by
    '---') whose header starts with '## {date}' and that contains every
    non-empty identifier string.

    Used as a content-based dedup safety net before appending a new entry.
    """
    if not content or f'## {date}' not in content:
        return False
    for block in re.split(r'\n---\s*\n?', content):
        if f'## {date}' not in block:
            continue
        if all(ident in block for ident in identifiers if ident):
            return True
    return False


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


def render_financial_markdown(record: dict) -> str:
    """Standardized Markdown entry for Memory/Receipts and Memory/Orders."""
    date = record.get('date', 'Unknown')
    amount = record.get('accounting', {}).get('total', record.get('record_type', 'Payment'))
    vendor = record.get('vendor', 'Unknown')
    
    lines = [f'## {date} — {amount}']
    
    # Entity identity for cross-pipeline tracking
    from toolbox.lib.entity_ids import build_entity_id, render_entity_comment
    entity_key = f"{date}|{vendor}|{amount}"
    entity_id = build_entity_id(record.get('category', 'receipts'), entity_key)
    lines.append(render_entity_comment(entity_id))
    
    lines.append(f'**Merchant:** {vendor}')
    lines.append(f'**Type:** [{record.get("record_type", "Receipt")}] {date}')
    
    # Payment info
    pay = record.get('payment', {})
    if pay.get('method'):
        acc_str = f" ({pay['last_4']})" if pay.get('last_4') else ""
        cardholder = f" [{pay['cardholder']}]" if pay.get('cardholder') else ""
        lines.append(f'**Payment:** {pay["method"]}{acc_str}{cardholder}')
    
    # Financial Breakdown
    acc = record.get('accounting', {})
    breakdown = []
    if acc.get('subtotal'): breakdown.append(f"Subtotal: {acc['subtotal']}")
    if acc.get('tax'): breakdown.append(f"Tax: {acc['tax']}")
    if acc.get('shipping_fees'): breakdown.append(f"Fees/Shipping: {acc['shipping_fees']}")
    if acc.get('discounts'): breakdown.append(f"Discounts: {acc['discounts']}")
    
    if breakdown:
        lines.append('**Financial Breakdown:** ' + ' | '.join(breakdown))
    
    # Items
    items = record.get('line_items', [])
    if items:
        lines.append('\n**Items:**')
        for item in items:
            qty_str = f" ×{item['qty']}" if int(item.get('qty', 1)) > 1 else ""
            price_str = f" — {item['unit_price']}" if item.get('unit_price') else ""
            lines.append(f'- {item["name"]}{qty_str}{price_str}')
            
    # Metadata
    meta = record.get('metadata', {})
    if meta.get('order_number'):
        lines.append(f'**Order Number:** {meta["order_number"]}')
    if meta.get('tracking'):
        carrier = f" ({meta['carrier']})" if meta.get('carrier') else ""
        lines.append(f'**Tracking:** {meta["tracking"]}{carrier}')
    if meta.get('estimated_delivery'):
        lines.append(f'**Estimated Delivery:** {meta["estimated_delivery"]}')
        
    lines.append('---')
    return "\n".join(lines)


def append_to_memory(category: str, filename: str, new_content: str,
                      dedup_date: str = '', dedup_ids: tuple = ()) -> bool:
    """
    Append new_content to Memory/{category}/{filename}.
    category: e.g. 'Orders', 'Receipts', 'Digests' (or None for Travel.md at Memory root)
    filename: e.g. 'Amazon.md'

    If dedup_date is provided, checks block_exists before appending.
    Returns True if content was written, False if skipped as duplicate.
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
        if dedup_date and block_exists(existing, dedup_date, *dedup_ids):
            logger.info(f'Skipping duplicate block in {category}/{filename} [{dedup_date}]')
            return False
        full_content = existing.rstrip('\n') + '\n\n' + new_content
        media = MediaIoBaseUpload(io.BytesIO(full_content.encode()), mimetype='text/markdown')
        service.files().update(fileId=file_id, media_body=media).execute()
        logger.info(f'Updated {category}/{filename}')
    else:
        media = MediaIoBaseUpload(io.BytesIO(new_content.encode()), mimetype='text/markdown')
        meta = {'name': filename, 'parents': [folder_id]}
        service.files().create(body=meta, media_body=media, fields='id').execute()
        logger.info(f'Created {category}/{filename}')
    return True
