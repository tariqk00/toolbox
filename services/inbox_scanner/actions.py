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


PROPERTY_INQUIRY_PROMPT = """You are processing a property rental inquiry email.
Extract the following from the email content:
- prospective_tenant: name of the prospective tenant (null if not found)
- move_in_date: desired move-in timeframe (null if not mentioned)
- unit_type: unit size or type they are interested in (null if not mentioned)
- questions: list of specific questions asked (empty list if none)
- notes: any other relevant detail (null if nothing)

Return ONLY valid JSON, no other text:
{{"prospective_tenant": "...", "move_in_date": "...", "unit_type": "...", "questions": ["..."], "notes": "..."}}

Email:
{text}"""


def handle_monitored_inquiry(email: dict, classification: dict, monitor_config: dict,
                              telegram_service: str) -> None:
    """Structured extraction + dedicated Drive log + immediate Telegram alert for monitored senders."""
    import json
    import re
    from toolbox.lib.gemini import call_gemini
    from toolbox.services.email_extractor.scanner import html_to_text
    from toolbox.services.email_extractor.writers import append_to_memory

    label = monitor_config.get('label', 'Property')
    property_name = monitor_config.get('property', label)
    date = email.get('date', '')
    subject = email.get('subject', '')
    from_h = email.get('from', '')
    html = email.get('html', '')
    plain = email.get('plain', '')

    text, _ = html_to_text(html) if html else (plain, [])

    # Gemini extraction
    extracted = {}
    if text and len(text) > 50:
        raw = call_gemini(PROPERTY_INQUIRY_PROMPT.format(text=text[:5000]))
        if raw:
            try:
                raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
                raw = re.sub(r'\s*```$', '', raw)
                extracted = json.loads(raw)
            except Exception as e:
                logger.warning(f'Property inquiry extraction failed: {e}')

    tenant = extracted.get('prospective_tenant')
    move_in = extracted.get('move_in_date')
    unit_type = extracted.get('unit_type')
    questions = extracted.get('questions') or []
    notes = extracted.get('notes')

    # Build Drive content
    lines = [f'## {date} — {subject}', '', f'**From:** {from_h}']
    if tenant:
        lines.append(f'**Prospective tenant:** {tenant}')
    detail_parts = []
    if move_in:
        detail_parts.append(f'Move-in: {move_in}')
    if unit_type:
        detail_parts.append(f'Unit: {unit_type}')
    if detail_parts:
        lines.append(f'**{" • ".join(detail_parts)}**')
    if questions:
        lines.append('**Questions:**')
        for q in questions:
            lines.append(f'- {q}')
    if not tenant and not questions:
        reason = classification.get('reason', '')
        if reason:
            lines.append(f'**Summary:** {reason}')
    if notes:
        lines.append(f'*{notes}*')
    lines += ['', '---']

    append_to_memory('Properties', f'{label} Inquiries.md', '\n'.join(lines))
    logger.info(f'Monitored inquiry written: {label} — {subject}')

    # Immediate Telegram alert
    alert_lines = [f'<b>New inquiry — {escape(property_name)}</b>',
                   f'Subject: {escape(subject)}']
    if tenant:
        alert_lines.append(f'Tenant: {escape(tenant)}')
    detail_str = ' | '.join(filter(None, [
        f'Move-in: {move_in}' if move_in else None,
        f'Unit: {unit_type}' if unit_type else None,
    ]))
    if detail_str:
        alert_lines.append(detail_str)
    if questions:
        alert_lines.append(f'Questions: {escape(", ".join(str(q) for q in questions[:3]))}')
    send_message('\n'.join(alert_lines), service=telegram_service)


def send_run_summary(results: dict, errors: int, mailbox_email: str, telegram_service: str) -> None:
    """Send end-of-run Telegram summary."""
    total = sum(len(v) for v in results.values())
    if total == 0 and errors == 0:
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
