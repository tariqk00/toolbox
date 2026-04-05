"""
Orders category processor.
Extracts: vendor, order number, items, status, tracking, amount.
Rule-based from subject + plain text body.
"""
import re
import logging
from ..writers import append_to_memory

logger = logging.getLogger('EmailExtractor.Orders')


def _extract_order_number(subject: str, plain: str) -> str:
    for pattern in [
        r'[Oo]rder\s*[#Nn]o?\.?\s*([A-Z0-9\-]{6,})',
        r'\[([a-z][0-9]{15,})\]',        # lululemon [c177512979471524]
        r'[Nn]umber\s+(\d{8,})',
        r'#(\d{8,})',
    ]:
        for text in (subject, plain[:2000]):
            m = re.search(pattern, text)
            if m:
                return m.group(1)
    return ''


def _extract_tracking(plain: str) -> str:
    for pattern in [
        r'[Tt]racking\s*[Nn]umber[:\s]+([A-Z0-9]{10,})',
        r'Track[:\s]+([A-Z0-9]{10,})',
        r'\b(1Z[A-Z0-9]{16})\b',         # UPS
        r'\b(\d{12,22})\b',              # FedEx/USPS
    ]:
        m = re.search(pattern, plain[:3000])
        if m:
            return m.group(1)
    return ''


def _extract_amount(plain: str) -> str:
    m = re.search(r'\$\s*([\d,]+\.\d{2})', plain[:2000])
    return f'${m.group(1)}' if m else ''


def _extract_items_amazon(subject: str) -> str:
    """'Shipped: "Item Name..." and N more items' → 'Item Name, +N more'"""
    m = re.search(r'Shipped:\s*"([^"]+)"(?:\s*and\s*(\d+)\s*more)?', subject)
    if m:
        item = m.group(1).rstrip('.')
        if m.group(2):
            return f'{item}, +{m.group(2)} more'
        return item
    return ''


ORDER_KEYWORDS = (
    'order', 'shipped', 'delivered', 'delivery', 'in transit', 'dispatched',
    'arrived', 'installed', 'confirmed', 'placed', 'cancel', 'tracking',
    'pillpack', 'shipment',
)


def _is_order_email(subject: str, plain: str) -> bool:
    """Filter out non-order emails from order senders (e.g. WHOOP health updates)."""
    combined = (subject + ' ' + plain[:500]).lower()
    return any(kw in combined for kw in ORDER_KEYWORDS)


def _extract_status(subject: str) -> str:
    lower = subject.lower()
    if any(w in lower for w in ('shipped', 'on its way', 'in transit', 'dispatched')):
        return 'Shipped'
    if any(w in lower for w in ('delivered', 'arrived', 'installed')):
        return 'Delivered'
    if any(w in lower for w in ('confirmed', 'received your order', 'we got your order')):
        return 'Confirmed'
    if 'cancel' in lower:
        return 'Cancelled'
    if 'placed' in lower:
        return 'Placed'
    return 'Update'


def process(email: dict) -> bool:
    vendor = email['vendor']
    subject = email['subject']
    plain = email['plain'] or ''
    date = email['date']

    if not _is_order_email(subject, plain):
        logger.debug(f'Skipping non-order email from {vendor}: {subject[:60]}')
        return False

    status = _extract_status(subject)
    order_num = _extract_order_number(subject, plain)
    tracking = _extract_tracking(plain)
    amount = _extract_amount(plain)
    items = _extract_items_amazon(subject) if vendor == 'Amazon' else ''

    lines = [f'## {date} — {status}']
    if order_num:
        lines.append(f'**Order:** #{order_num}')
    if items:
        lines.append(f'**Items:** {items}')
    if amount:
        lines.append(f'**Amount:** {amount}')
    if tracking:
        lines.append(f'**Tracking:** {tracking}')
    lines.append(f'**Subject:** {subject}')
    lines.append('---')

    content = '\n'.join(lines)
    filename = f'{vendor}.md'
    append_to_memory('Orders', filename, content)
    summary = f'{vendor}: {status}' + (f' #{order_num}' if order_num else '') + (f' — {items}' if items else '')
    logger.info(f'Orders/{filename}: {summary}')
    return summary
