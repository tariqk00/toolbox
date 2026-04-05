"""
Trips category processor.
Extracts: type, destination, dates, confirmation number.
First email: full entry with [Status] date on the status line.
Subsequent emails: update status+date in-place via update_in_memory.
"""
import re
import logging
from ..writers import append_to_memory, update_in_memory

logger = logging.getLogger('EmailExtractor.Trips')


def _extract_confirmation(subject: str, plain: str) -> str:
    for pattern in [
        r'[Cc]onfirmation\s*[Nn]umber[:\s]+([A-Z0-9]{4,12})',
        r'[Cc]onfirmation[:\s#]+([A-Z0-9]{4,12})',
        r'\b([A-Z]{2,6}\d{3,8})\b',       # e.g. HXXKJD (Delta)
        r'[Rr]eservation\s*(?:ID|#)[:\s]+([A-Z0-9\-]{4,20})',
    ]:
        for text in (subject, plain[:2000]):
            m = re.search(pattern, text)
            if m:
                val = m.group(1)
                if len(val) >= 4 and not val.isdigit():
                    return val
    # numeric confirmation
    m = re.search(r'[Cc]onfirmation[:\s#]+(\d{6,})', plain[:2000])
    return m.group(1) if m else ''


def _extract_dates(plain: str) -> str:
    patterns = [
        r'([A-Z][a-z]+\s+\d{1,2})\s*[–\-]\s*([A-Z][a-z]+\s+\d{1,2},?\s*\d{4})',
        r'([A-Z][a-z]+\s+\d{1,2},?\s*\d{4})\s*(?:through|to|–|-)\s*([A-Z][a-z]+\s+\d{1,2},?\s*\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})\s*(?:to|-)\s*(\d{1,2}/\d{1,2}/\d{4})',
        r'([A-Z][a-z]+\.?\s+\d{1,2},?\s*\d{4})',
    ]
    for pattern in patterns:
        m = re.search(pattern, plain[:3000])
        if m:
            return ' — '.join(g for g in m.groups() if g)
    return ''


def _extract_trip_type(vendor: str, subject: str) -> str:
    lower = subject.lower()
    # Vendor-specific checks first to avoid keyword false-positives
    if vendor in ('Delta', 'AmEx Global Business Travel'):
        return 'Flight'
    if vendor == 'National Car Rental':
        return 'Car Rental'
    if vendor == 'Resy':
        return 'Dining'
    if vendor == 'Marriott Vacation Club':
        return 'Hotel'
    # Keyword fallbacks for other vendors
    if any(w in lower for w in ('flight', 'check in', 'boarding', 'airline')):
        return 'Flight'
    if any(w in lower for w in ('hotel', 'resort', 'check-in')):
        return 'Hotel'
    if 'car rental' in lower or 'car reservation' in lower:
        return 'Car Rental'
    if 'restaurant' in lower or 'dining' in lower:
        return 'Dining'
    return 'Travel'


def _extract_destination(vendor: str, subject: str, plain: str) -> str:
    if vendor == 'Marriott Vacation Club':
        for pattern in [r"Maui|Kauai|Hawaii|Hawaii'i|Honolulu|Waikiki"]:
            m = re.search(pattern, subject + ' ' + plain[:1000], re.IGNORECASE)
            if m:
                return m.group(0)
    if vendor == 'Delta':
        m = re.search(r'flight\s+(?:to\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', subject, re.IGNORECASE)
        if m:
            return m.group(1)
    if vendor == 'National Car Rental':
        m = re.search(r'at\s+([A-Z\s]+(?:ARPT|AIRPORT))', subject)
        if m:
            return m.group(1).strip()
    if vendor == 'Resy':
        m = re.search(r'at\s+([A-Z][A-Z\s&]+)', subject)
        if m:
            return m.group(1).title().strip()
    return ''


def _extract_status(subject: str) -> str | None:
    lower = subject.lower()
    if 'cancel' in lower:
        return 'Cancelled'
    if any(w in lower for w in ('confirmed', 'confirmation', 'booked', 'reservation')):
        return 'Confirmed'
    if 'check in' in lower or 'check-in' in lower or 'time to check in' in lower:
        return 'Check-in'
    if any(w in lower for w in ('days until', 'upcoming arrival', 'arrival reminder')):
        return 'Reminder'
    if any(w in lower for w in ('change', 'update', 'modified')):
        return 'Changed'
    return None  # unknown/generic — skip


def process(email: dict, state: dict) -> str | None:
    vendor = email['vendor']
    subject = email['subject']
    plain = email['plain'] or ''
    date = email['date']

    status = _extract_status(subject)
    if not status:
        return None

    trip_type = _extract_trip_type(vendor, subject)
    confirmation = _extract_confirmation(subject, plain)
    dates = _extract_dates(plain)
    destination = _extract_destination(vendor, subject, plain)

    known_trips = state.setdefault('trip_confirmations', {})

    if confirmation and confirmation in known_trips:
        prev = known_trips[confirmation]
        if status == prev.get('status'):
            return None

        # Update [Status] date in-place on the status line
        old_line = prev.get('status_line', f'**Status:** [{prev["status"]}] {prev["date"]}')
        new_line = f'**Status:** [{status}] {date}'
        update_in_memory(None, 'Travel.md', old_line, new_line)
        prev['status'] = status
        prev['status_line'] = new_line
        prev['date'] = date

        dest = prev.get('destination', '')
        summary = f'{trip_type}: {dest} ({vendor})' if dest else f'{trip_type}: {vendor}'
        summary += f' → {status} [{date}]'
        logger.info(f'Travel.md: status update {summary}')
        return summary

    # First time — full entry
    status_line = f'**Status:** [{status}] {date}'
    header = f'{trip_type} — {destination}' if destination else trip_type
    lines = [f'## {date} — {header}']
    lines.append(f'**Vendor:** {vendor}')
    lines.append(status_line)
    if dates:
        lines.append(f'**Dates:** {dates}')
    if confirmation:
        lines.append(f'**Confirmation:** {confirmation}')
    lines.append('---')

    append_to_memory(None, 'Travel.md', '\n'.join(lines))

    if confirmation:
        known_trips[confirmation] = {
            'vendor': vendor, 'status': status, 'status_line': status_line,
            'date': date, 'destination': destination,
        }

    summary = f'{trip_type}: {destination} ({vendor})' if destination else f'{trip_type}: {vendor}'
    summary += f' [{status}]'
    if dates:
        summary += f' — {dates[:40]}'
    logger.info(f'Travel.md: {summary}')
    return summary
