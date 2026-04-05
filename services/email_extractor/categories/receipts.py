"""
Receipts category processor.
Extracts: vendor, amount, date, account, type.
Type line includes date: **Type:** [Reminder] 2026-04-01
For bills: Reminder → Payment transitions update type+date in-place.
Dedup key: vendor:amount (only upgrades from Reminder to a concrete type).
"""
import re
import logging
from ..writers import append_to_memory, update_in_memory

logger = logging.getLogger('EmailExtractor.Receipts')

REMINDER_KEYWORDS = ('reminder', 'upcoming', 'scheduled', 'due soon', 'autopay', 'auto pay')


def _extract_amount(subject: str, plain: str) -> str:
    for text in (subject, plain[:2000]):
        m = re.search(r'\$\s*([\d,]+\.\d{2})', text)
        if m:
            return f'${m.group(1)}'
    return ''


def _extract_account(plain: str) -> str:
    for pattern in [
        r'[Cc]ard\s*ending\s*in\s*(\d{4})',
        r'[Aa]ccount\s*[Nn]umber[:\s]+[x*]+(\d{4,})',
        r'[Aa]ccount[:\s]+[x*•]+(\d{4})',
        r'[Aa]ccount\s*[Nn]umber[:\s]+\**(\d{4,})',
    ]:
        m = re.search(pattern, plain[:3000])
        if m:
            return f'...{m.group(1)}'
    return ''


def _is_reminder(subject: str, plain: str) -> bool:
    combined = (subject + ' ' + plain[:500]).lower()
    return any(kw in combined for kw in REMINDER_KEYWORDS)


def _extract_uber_rider(subject: str, plain: str) -> str:
    """Extract rider from '[Family] Your trip' or '[Personal] Your trip' + name in body."""
    label_match = re.search(r'\[(Family|Personal)\]', subject)
    label = label_match.group(1) if label_match else ''
    name_match = re.search(r'Thanks for (?:riding|tipping),\s+(\w+)', plain[:500])
    name = name_match.group(1) if name_match else ''
    if name and label:
        return f'{name} ({label})'
    return name or label


def _extract_type(subject: str) -> str:
    lower = subject.lower()
    if any(w in lower for w in REMINDER_KEYWORDS):
        return 'Reminder'
    if any(w in lower for w in ('receipt', 'payment receipt')):
        return 'Receipt'
    if any(w in lower for w in ('payment posted', 'payment received', 'payment confirmed',
                                 'payment confirmation', 'payment has posted')):
        return 'Payment'
    if 'invoice' in lower:
        return 'Invoice'
    if any(w in lower for w in ('scheduled', 'set up')):
        return 'Scheduled'
    return 'Payment'


def process(email: dict, state: dict) -> str | None:
    vendor = email['vendor']
    subject = email['subject']
    plain = email['plain'] or ''
    date = email['date']

    amount = _extract_amount(subject, plain)
    account = _extract_account(plain)
    receipt_type = _extract_type(subject)
    type_line = f'**Type:** [{receipt_type}] {date}'

    filename = f'{vendor}.md'
    known_receipts = state.setdefault('receipts', {})

    # Dedup key: Reminder → Payment transition for the same bill
    # Uber rides are always unique (skip dedup)
    dedup_key = f'{vendor}:{amount}' if vendor != 'Uber' and amount else None

    if dedup_key and dedup_key in known_receipts:
        prev = known_receipts[dedup_key]
        prev_type = prev.get('type', '')
        # Only update if previous was a Reminder and current is a concrete type
        if prev_type == 'Reminder' and receipt_type != 'Reminder':
            old_line = prev.get('type_line', f'**Type:** [Reminder] {prev["date"]}')
            update_in_memory('Receipts', filename, old_line, type_line)
            prev['type'] = receipt_type
            prev['type_line'] = type_line
            prev['date'] = date

            summary = f'{vendor}: {amount} → {receipt_type} [{date}]'
            logger.info(f'Receipts/{filename}: {summary}')
            return summary
        # Same type again or non-Reminder already seen — fall through to new entry

    # New entry
    lines = [f'## {date} — {amount or receipt_type}']
    lines.append(type_line)
    if amount:
        lines.append(f'**Amount:** {amount}')
    if account:
        lines.append(f'**Account:** {account}')

    if vendor == 'Uber':
        rider = _extract_uber_rider(subject, plain)
        if rider:
            lines.append(f'**Rider:** {rider}')

    lines.append('---')

    append_to_memory('Receipts', filename, '\n'.join(lines))

    if dedup_key and receipt_type == 'Reminder':
        known_receipts[dedup_key] = {
            'type': receipt_type, 'type_line': type_line,
            'date': date, 'account': account,
        }

    summary = f'{vendor}: {amount} [{receipt_type}]' if amount else f'{vendor}: [{receipt_type}]'
    if vendor == 'Uber' and (rider := _extract_uber_rider(subject, plain)):
        summary += f' — {rider}'
    logger.info(f'Receipts/{filename}: {summary}')
    return summary
