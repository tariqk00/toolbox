"""
Receipts category processor.
Extracts: vendor, amount, date, account, type, reminder flag.
Uber: also extracts rider name from subject/body.
"""
import re
import logging
from ..writers import append_to_memory

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

    # Look for "Thanks for riding, Name" or "Thanks for tipping, Name"
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


def process(email: dict) -> bool:
    vendor = email['vendor']
    subject = email['subject']
    plain = email['plain'] or ''
    date = email['date']

    amount = _extract_amount(subject, plain)
    account = _extract_account(plain)
    receipt_type = _extract_type(subject)
    is_reminder = _is_reminder(subject, plain)

    lines = [f'## {date} — {amount or receipt_type}']
    lines.append(f'**Type:** {"⚠️ Reminder — " if is_reminder else ""}{receipt_type}')
    if amount:
        lines.append(f'**Amount:** {amount}')
    if account:
        lines.append(f'**Account:** {account}')

    if vendor == 'Uber':
        rider = _extract_uber_rider(subject, plain)
        if rider:
            lines.append(f'**Rider:** {rider}')

    lines.append(f'**Subject:** {subject}')
    lines.append('---')

    content = '\n'.join(lines)
    filename = f'{vendor}.md'
    append_to_memory('Receipts', filename, content)
    logger.info(f'Receipts/{filename}: {receipt_type} {amount}')
    return True
