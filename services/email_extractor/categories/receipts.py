"""
Receipts category processor.
Extracts: vendor, amount, date, account, type.
Type line includes date: **Type:** [Reminder] 2026-04-01
For bills: Reminder → Payment transitions update type+date in-place.
Dedup key: vendor:amount (only upgrades from Reminder to a concrete type).
"""
import re
import logging
from datetime import datetime
from ..writers import append_to_memory, update_in_memory
from ..enrichment import enrich_receipt

logger = logging.getLogger('EmailExtractor.Receipts')

REMINDER_KEYWORDS = ('reminder', 'upcoming', 'scheduled', 'due soon', 'autopay', 'auto pay')

FINANCIAL_VENDORS = {
    'Capital One', 'Chase', 'Citi / Costco Visa', 'Toyota Financial',
    'Volvo Financial', 'PSEG Long Island', 'T-Mobile', 'E-ZPass NY',
}


def _extract_amount(subject: str, plain: str) -> str:
    combined = f'{subject}\n{plain[:3000]}'
    priority_patterns = [
        r'(?:amount|payment|minimum payment|statement balance|total|autopay|auto pay)'
        r'[^$\n]{0,80}\$\s*([\d,]+\.\d{2})',
        r'\$\s*([\d,]+\.\d{2})[^.\n]{0,80}'
        r'(?:due|scheduled|posted|received|confirmed|payment|statement)',
    ]
    for pattern in priority_patterns:
        m = re.search(pattern, combined, re.IGNORECASE)
        if m:
            return f'${m.group(1)}'
    for text in (subject, plain[:2000]):
        m = re.search(r'\$\s*([\d,]+\.\d{2})', text)
        if m:
            return f'${m.group(1)}'
    return ''


def _extract_account(plain: str) -> str:
    for pattern in [
        r'[Cc]ard\s*ending\s*in\s*(\d{4})',
        r'[Cc]ard\s*ending\s*(?:with|in)?\s*[x*• ]*(\d{4})',
        r'[Aa]ccount\s*ending\s*(?:with|in)?\s*[x*• ]*(\d{4})',
        r'[Aa]ccount\s*[Nn]umber[:\s]+[x*]+(\d{4,})',
        r'[Aa]ccount[:\s]+[x*•]+(\d{4})',
        r'[Aa]ccount\s*[Nn]umber[:\s]+\**(\d{4,})',
    ]:
        m = re.search(pattern, plain[:3000])
        if m:
            return f'...{m.group(1)}'
    return ''


def _normalize_date(raw: str, email_date: str) -> str:
    raw = raw.strip().strip(',.')
    raw = re.sub(r'\s+', ' ', raw)
    formats = [
        '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y',
        '%B %d, %Y', '%b %d, %Y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    year = email_date[:4]
    for fmt in ('%B %d', '%b %d'):
        try:
            return datetime.strptime(f'{raw} {year}', f'{fmt} %Y').strftime('%Y-%m-%d')
        except ValueError:
            pass
    return raw


def _extract_date_by_label(text: str, labels: tuple[str, ...], email_date: str) -> str:
    date_pattern = (
        r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|'
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s+\d{4})?)'
    )
    for label in labels:
        patterns = [
            rf'{label}[^A-Za-z0-9]{{0,20}}{date_pattern}',
            rf'{date_pattern}[^.\n]{{0,40}}{label}',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                raw = m.group(1) if not m.group(1).lower().startswith(label.lower()[:3]) else m.group(2)
                return _normalize_date(raw, email_date)
    if any('due' in label for label in labels):
        m = re.search(rf'\b(?:due|is due)\s+(?:on|by)?\s*{date_pattern}', text, re.IGNORECASE)
        if m:
            return _normalize_date(m.group(1), email_date)
    return ''


def _extract_payment_method(plain: str) -> str:
    text = plain[:3000]
    patterns = [
        r'(?:paid from|payment method|from)[:\s]+((?:bank|checking|savings|card|account)[^.\n]{0,80}(?:\d{4}))',
        r'((?:Visa|Mastercard|Amex|American Express|Discover)[^.\n]{0,50}(?:\d{4}))',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return re.sub(r'\s+', ' ', m.group(1)).strip()
    return ''


def _extract_financial_type(subject: str, plain: str, fallback: str) -> str:
    combined = f'{subject} {plain[:1000]}'.lower()
    if any(w in combined for w in ('statement is ready', 'new statement', 'monthly statement', 'statement available')):
        return 'Statement'
    if any(w in combined for w in ('minimum payment due', 'payment due', 'due alert', 'due soon')):
        return 'Payment Due'
    if any(w in combined for w in ('autopay', 'auto pay', 'automatic payment')):
        if any(w in combined for w in ('scheduled', 'upcoming', 'will be made')):
            return 'Autopay Scheduled'
        return 'Autopay'
    if any(w in combined for w in ('payment posted', 'payment received', 'payment confirmed',
                                   'payment confirmation', 'payment has posted')):
        return 'Payment'
    if any(w in combined for w in ('purchase alert', 'transaction alert', 'charge alert')):
        return 'Transaction'
    return fallback


def _extract_financial_details(vendor: str, subject: str, plain: str, email_date: str,
                               receipt_type: str) -> dict:
    text = f'{subject}\n{plain[:5000]}'
    financial_type = _extract_financial_type(subject, plain, receipt_type)
    return {
        'institution': vendor,
        'event_type': financial_type,
        'account': _extract_account(plain),
        'payment_method': _extract_payment_method(plain),
        'due_date': _extract_date_by_label(text, ('due date', 'payment due', 'due by'), email_date),
        'payment_date': _extract_date_by_label(
            text,
            ('payment date', 'posted on', 'processed on', 'scheduled for', 'will be made on'),
            email_date,
        ),
        'statement_date': _extract_date_by_label(text, ('statement date', 'statement closing date'), email_date),
    }


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
    financial_details = {}
    if vendor in FINANCIAL_VENDORS:
        financial_details = _extract_financial_details(vendor, subject, plain, date, receipt_type)
        receipt_type = financial_details.get('event_type') or receipt_type
        account = financial_details.get('account') or account
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
    if financial_details:
        lines.append(f'**Institution:** {financial_details["institution"]}')
    lines.append(type_line)
    if amount:
        lines.append(f'**Amount:** {amount}')
    if account:
        lines.append(f'**Account:** {account}')
    if financial_details.get('payment_method'):
        lines.append(f'**Payment Method:** {financial_details["payment_method"]}')
    if financial_details.get('due_date'):
        lines.append(f'**Due Date:** {financial_details["due_date"]}')
    if financial_details.get('payment_date'):
        lines.append(f'**Payment Date:** {financial_details["payment_date"]}')
    if financial_details.get('statement_date'):
        lines.append(f'**Statement Date:** {financial_details["statement_date"]}')

    if vendor == 'Uber':
        rider = _extract_uber_rider(subject, plain)
        if rider:
            lines.append(f'**Rider:** {rider}')

    lines.append('---')

    dedup_ids = (amount,) if amount else ()
    append_to_memory('Receipts', filename, '\n'.join(lines),
                     dedup_date=date, dedup_ids=dedup_ids)

    if dedup_key and receipt_type == 'Reminder':
        known_receipts[dedup_key] = {
            'type': receipt_type, 'type_line': type_line,
            'date': date, 'account': account,
        }

    summary = f'{vendor}: {amount} [{receipt_type}]' if amount else f'{vendor}: [{receipt_type}]'
    if financial_details:
        extras = []
        if account:
            extras.append(account)
        if financial_details.get('due_date'):
            extras.append(f'due {financial_details["due_date"]}')
        if financial_details.get('payment_date'):
            extras.append(financial_details['payment_date'])
        if extras:
            summary += ' — ' + ' | '.join(extras)
    if vendor == 'Uber' and (rider := _extract_uber_rider(subject, plain)):
        summary += f' — {rider}'
    summary = enrich_receipt(summary, vendor, amount, receipt_type)
    logger.info(f'Receipts/{filename}: {summary.splitlines()[0]}')
    return summary
