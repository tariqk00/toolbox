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
from toolbox.lib.drive_utils import get_drive_service, append_to_file
from toolbox.lib.task_utils import add_task
from toolbox.lib.telegram import send_message, escape, monit_link

logger = logging.getLogger('InboxScanner.Actions')

INBOX_ROOT = '01 - Second Brain/Inbox'
UPTOWN_INQUIRY_CATEGORY = 'Properties'
UPTOWN_INQUIRY_FILENAME = 'Uptown Edenton Inquiries.md'


def write_action_required(items: list) -> None:
    """Write action required items to Drive log and Google Tasks with dedup."""
    for item in items:
        add_task(
            subject=item["subject"],
            sender=item["sender"],
            reason=item["reason"],
            priority=item.get("priority", "medium"),
            date_str=item.get("date"),
            sync_to_google_tasks=True
        )


def write_inquiries(items: list) -> None:
    """Write inquiry items to Drive log."""
    from datetime import date
    if not items:
        return
    today = date.today().isoformat()
    lines = [f'## {today} — {len(items)} inquiries\n']
    for item in items:
        lines.append(f'### {item["subject"]}')
        lines.append(f'**From:** {item["sender"]}  ')
        lines.append(f'**Date:** {item["date"]}  ')
        lines.append(f'**Why:** {item["reason"]}')
        lines.append('')
    lines.append('---')
    append_to_file(INBOX_ROOT, 'Inquiries.md', '\n'.join(lines))


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
    from toolbox.lib.llm import call_json
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

    # LLM extraction
    extracted = {}
    if text and len(text) > 50:
        extracted = call_json(PROPERTY_INQUIRY_PROMPT.format(text=text[:5000]))

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


def send_uptown_inquiry_alert(item: dict, telegram_service: str) -> None:
    """Send two Telegram messages for a new Uptown Edenton inquiry: details + shadow response."""
    tenant = item.get('tenant') or 'Unknown'
    platform = item.get('platform', 'Direct')
    subject = item.get('subject', '')
    sender = item.get('sender', '')
    unit_interest = item.get('unit_interest', '')
    move_in = item.get('move_in', '')
    questions = item.get('questions', [])
    contact_phone = item.get('contact_phone', '')
    shadow = item.get('shadow_response', '')

    # Message 1: inquiry details
    lines = [f'<b>New inquiry — Uptown Edenton</b>']
    lines.append(f'<b>From:</b> {escape(tenant)} via {escape(platform)}')
    lines.append(f'<b>Email:</b> {escape(sender)}')
    if contact_phone:
        lines.append(f'<b>Phone:</b> {escape(contact_phone)}')
    if unit_interest:
        lines.append(f'<b>Interested in:</b> {escape(unit_interest)}')
    if move_in:
        lines.append(f'<b>Move-in:</b> {escape(move_in)}')
    if questions:
        lines.append(f'<b>Questions:</b>')
        for q in questions[:5]:
            lines.append(f'  • {escape(str(q))}')
    lines.append(f'\n<i>Subject: {escape(subject)}</i>')
    send_message('\n'.join(lines), service=telegram_service)

    # Message 2: shadow response draft
    if shadow:
        draft_msg = f'<b>Shadow response draft:</b>\n\n{escape(shadow)}'
        send_message(draft_msg, service=telegram_service)


def send_uptown_nudge(inquiry: dict, hours_old: int, telegram_service: str) -> None:
    """Alert that an inquiry has not been responded to within the timeout window."""
    tenant = inquiry.get('tenant') or 'Unknown prospect'
    date = inquiry.get('date', '')
    subject = inquiry.get('subject', '')
    days = hours_old // 24
    age_str = f'{days}d {hours_old % 24}h' if days else f'{hours_old}h'
    msg = (
        f'<b>Uptown Edenton — no response yet</b>\n'
        f'Inquiry from <b>{escape(tenant)}</b> ({age_str} ago, {escape(date)})\n'
        f'Subject: {escape(subject)}'
    )
    send_message(msg, service=telegram_service)


def write_uptown_inquiries(items: list) -> None:
    """Write Uptown Edenton inquiries to Memory/Properties/Uptown Edenton Inquiries.md."""
    if not items:
        return
    from toolbox.services.email_extractor.writers import get_memory_content, set_memory_content
    content = get_memory_content(UPTOWN_INQUIRY_CATEGORY, UPTOWN_INQUIRY_FILENAME)
    for item in items:
        content = upsert_uptown_inquiry_entry(content, item)
        logger.info(f'Uptown inquiry logged: {item.get("tenant") or item.get("sender","")} — {item.get("subject","")}')
    set_memory_content(UPTOWN_INQUIRY_CATEGORY, UPTOWN_INQUIRY_FILENAME, content)


def _render_uptown_inquiry_block(item: dict, kb_filename: str = '', response_status: str = 'Pending') -> str:
    date = item.get('date', '')
    subject = item.get('subject', '')
    tenant = item.get('tenant', '')
    platform = item.get('platform', 'Direct')
    sender = item.get('sender', '')
    unit_interest = item.get('unit_interest', '')
    move_in = item.get('move_in', '')
    questions = item.get('questions', [])
    contact_phone = item.get('contact_phone', '')
    notes = item.get('notes', '')
    thread_id = item.get('thread_id', '')

    lines = [f'## {date} — {subject}']
    lines.append(f'**From:** {sender} ({platform})')
    if tenant:
        lines.append(f'**Tenant:** {tenant}')
    if contact_phone:
        lines.append(f'**Phone:** {contact_phone}')
    if unit_interest:
        lines.append(f'**Interested in:** {unit_interest}')
    if move_in:
        lines.append(f'**Move-in:** {move_in}')
    if questions:
        lines.append('**Questions:**')
        for q in questions:
            lines.append(f'- {q}')
    if notes:
        lines.append(f'*{notes}*')
    if thread_id:
        lines.append(f'**Thread ID:** {thread_id}')
    lines.append(f'**KB File:** {kb_filename or "Pending"}')
    lines.append(f'**Response:** {response_status}')
    lines.append('---')
    return '\n'.join(lines)


def _split_blocks(content: str) -> list[str]:
    return [block.strip() for block in content.split('---') if block.strip()]


def _join_blocks(blocks: list[str]) -> str:
    if not blocks:
        return ''
    return '\n\n---\n\n'.join(blocks).strip() + '\n'


def _block_thread_id(block: str) -> str:
    import re
    match = re.search(r'^\*\*Thread ID:\*\*\s*(.+)$', block, re.MULTILINE)
    return match.group(1).strip() if match else ''


def _block_header(block: str) -> tuple[str, str]:
    import re
    match = re.search(r'^##\s+(\S+)\s+—\s+(.+)$', block, re.MULTILINE)
    if not match:
        return '', ''
    return match.group(1).strip(), match.group(2).strip()


def upsert_uptown_inquiry_entry(content: str, item: dict) -> str:
    blocks = _split_blocks(content)
    thread_id = item.get('thread_id', '')
    replacement = _render_uptown_inquiry_block(item)
    for idx, block in enumerate(blocks):
        if thread_id and _block_thread_id(block) == thread_id:
            blocks[idx] = replacement
            return _join_blocks(blocks)
    blocks.append(replacement)
    return _join_blocks(blocks)


def sync_uptown_inquiry_index(kb_entries: list[dict]) -> None:
    """Update Uptown inquiry index with KB filename links and responded status."""
    from toolbox.services.email_extractor.writers import get_memory_content, set_memory_content
    import re

    content = get_memory_content(UPTOWN_INQUIRY_CATEGORY, UPTOWN_INQUIRY_FILENAME)
    blocks = _split_blocks(content)
    changed = False
    seen_threads = {_block_thread_id(block) for block in blocks if _block_thread_id(block)}

    for idx, block in enumerate(blocks):
        thread_id = _block_thread_id(block)
        if not thread_id:
            continue
        match = next((entry for entry in kb_entries if entry.get('thread_id') == thread_id), None)
        if not match:
            continue
        updated = block
        kb_file = match.get('_kb_filename', '')
        if kb_file:
            if re.search(r'^\*\*KB File:\*\* .+$', updated, re.MULTILINE):
                updated = re.sub(r'^\*\*KB File:\*\* .+$', f'**KB File:** {kb_file}', updated, flags=re.MULTILINE)
            else:
                updated += f'\n**KB File:** {kb_file}'
        if re.search(r'^\*\*Response:\*\* .+$', updated, re.MULTILINE):
            updated = re.sub(r'^\*\*Response:\*\* .+$', '**Response:** Responded', updated, flags=re.MULTILINE)
        else:
            updated += '\n**Response:** Responded'
        if updated != block:
            blocks[idx] = updated
            changed = True

    for entry in kb_entries:
        thread_id = entry.get('thread_id', '')
        if not thread_id or thread_id in seen_threads:
            continue
        entry_date = entry.get('date', '')
        entry_subject = entry.get('subject', '')
        already_present = any(
            _block_header(block) == (entry_date, entry_subject)
            for block in blocks
        )
        if already_present:
            continue
        blocks.append(_render_uptown_inquiry_block({
            'date': entry.get('date', ''),
            'subject': entry.get('subject', ''),
            'tenant': entry.get('lead_name', ''),
            'platform': entry.get('source', 'Direct'),
            'sender': entry.get('lead_name', ''),
            'notes': 'Linked from Uptown response KB',
            'thread_id': entry.get('thread_id', ''),
        }, kb_filename=entry.get('_kb_filename', ''), response_status='Responded'))
        changed = True

    if changed:
        set_memory_content(UPTOWN_INQUIRY_CATEGORY, UPTOWN_INQUIRY_FILENAME, _join_blocks(blocks))


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
