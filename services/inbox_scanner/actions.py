"""
Drive writer and Telegram notifier for inbox_scanner.
Writes to 01 - Second Brain/Inbox/ in Drive.
"""
import io
import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from googleapiclient.http import MediaIoBaseUpload
from toolbox.lib.drive_utils import get_drive_service
from toolbox.lib.telegram import send_message, escape, monit_link

logger = logging.getLogger('InboxScanner.Actions')

INBOX_ROOT = '01 - Second Brain/Inbox'

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
    parts = path.strip('/').split('/')
    parent_id = 'root'
    for part in parts:
        parent_id = _find_or_create_folder(service, part, parent_id)
    return parent_id


def _get_file_in_folder(service, folder_id: str, filename: str) -> str | None:
    query = f"'{folder_id}' in parents and name = '{filename}' and trashed = false"
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None


def append_to_inbox(filename: str, content: str) -> None:
    """Append content to 01 - Second Brain/Inbox/{filename}."""
    service = get_drive_service()
    folder_id = _resolve_path(service, INBOX_ROOT)
    file_id = _get_file_in_folder(service, folder_id, filename)
    if file_id:
        existing_bytes = service.files().get_media(fileId=file_id).execute()
        existing = existing_bytes.decode('utf-8') if isinstance(existing_bytes, bytes) else existing_bytes
        full_content = existing.rstrip('\n') + '\n\n' + content
        media = MediaIoBaseUpload(io.BytesIO(full_content.encode()), mimetype='text/markdown')
        service.files().update(fileId=file_id, media_body=media).execute()
        logger.info(f'Updated Inbox/{filename}')
    else:
        media = MediaIoBaseUpload(io.BytesIO(content.encode()), mimetype='text/markdown')
        meta = {'name': filename, 'parents': [folder_id]}
        service.files().create(body=meta, media_body=media, fields='id').execute()
        logger.info(f'Created Inbox/{filename}')


def write_action_required(items: list) -> None:
    """Write action required items to Drive log."""
    from datetime import date
    today = date.today().isoformat()
    lines = [f'## {today} — {len(items)} action required\n']
    for item in items:
        priority_flag = ' [HIGH]' if item.get('priority') == 'high' else ''
        lines.append(f'### {item["subject"]}{priority_flag}')
        lines.append(f'**From:** {item["sender"]}  ')
        lines.append(f'**Date:** {item["date"]}  ')
        lines.append(f'**Why:** {item["reason"]}')
        lines.append('')
    lines.append('---')
    append_to_inbox('Action Required.md', '\n'.join(lines))


def write_inquiries(items: list) -> None:
    """Write inquiry items to Drive log."""
    from datetime import date
    today = date.today().isoformat()
    lines = [f'## {today} — {len(items)} inquiries\n']
    for item in items:
        lines.append(f'### {item["subject"]}')
        lines.append(f'**From:** {item["sender"]}  ')
        lines.append(f'**Date:** {item["date"]}  ')
        lines.append(f'**Why:** {item["reason"]}')
        lines.append('')
    lines.append('---')
    append_to_inbox('Inquiries.md', '\n'.join(lines))


def send_immediate_alert(item: dict, telegram_service: str) -> None:
    """Send immediate Telegram alert for high-priority action required."""
    msg = (
        f'<b>Action required [HIGH]:</b> {escape(item["subject"])}\n'
        f'From: {escape(item["sender"])}\n'
        f'Why: {escape(item["reason"])}'
    )
    send_message(msg, service=telegram_service)


def send_run_summary(results: dict, errors: int, mailbox_email: str, telegram_service: str) -> None:
    """Send end-of-run Telegram summary."""
    total = sum(len(v) for v in results.values())
    if total == 0 and errors == 0:
        send_message(f'Inbox scanner ({mailbox_email}): nothing actionable', service=telegram_service)
        return

    lines = [f'<b>Inbox scanner ({escape(mailbox_email)}): {total} items</b>']

    action_items = results.get('action_required', [])
    if action_items:
        lines.append(f'\n<b>Action required ({len(action_items)}):</b>')
        for item in action_items:
            flag = ' [HIGH]' if item.get('priority') == 'high' else ''
            lines.append(f'  • {escape(item["subject"])}{flag}')

    inquiries = results.get('inquiry', [])
    if inquiries:
        lines.append(f'\n<b>Inquiries ({len(inquiries)}):</b>')
        for item in inquiries:
            lines.append(f'  • {escape(item["subject"])} — {escape(item["sender"][:40])}')

    if errors:
        lines.append(f'\n<b>{errors} error{"s" if errors > 1 else ""}:</b>')
        lines.append(f'  {monit_link("Check Monit")} · <code>journalctl --user -u inbox-scanner -n 50</code>')

    send_message('\n'.join(lines), service=telegram_service)
