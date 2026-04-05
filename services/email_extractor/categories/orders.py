"""
Orders category processor.
First email for an order: full entry (product, price, status).
Subsequent emails: compact status-only update.
State tracks seen order numbers to detect duplicates.
"""
import re
import logging
from ..writers import append_to_memory

logger = logging.getLogger('EmailExtractor.Orders')

ORDER_KEYWORDS = (
    'order', 'shipped', 'delivered', 'delivery', 'in transit', 'dispatched',
    'arrived', 'installed', 'confirmed', 'placed', 'cancel', 'tracking',
    'pillpack', 'shipment',
)


def _is_order_email(subject: str, plain: str) -> bool:
    combined = (subject + ' ' + plain[:500]).lower()
    return any(kw in combined for kw in ORDER_KEYWORDS)


def _extract_order_number(vendor: str, subject: str, plain: str) -> str:
    patterns = [
        r'[Oo]rder\s*[#Nn]o?\.?\s*([A-Z0-9\-]{6,})',
        r'[Oo]rder\s+[Nn]umber\s+(\d{8,})',
        r'\[([a-z][0-9]{15,})\]',           # lululemon [c177512979471524]
        r'#(\d{8,})',
    ]
    for text in (subject, plain[:2000]):
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
    return ''


def _extract_product(vendor: str, subject: str, plain: str) -> str:
    if vendor == 'Amazon':
        m = re.search(r'Shipped:\s*"([^"]+)"(?:\s*and\s*(\d+)\s*more)?', subject)
        if m:
            name = m.group(1).rstrip('.')
            return f'{name} (+{m.group(2)} more)' if m.group(2) else name

    if vendor == 'Amazon Pharmacy':
        m = re.search(r'containing\s+(\d+\s+of\s+\d+\s+medication)', plain[:500])
        return m.group(1) if m else 'PillPack medications'

    if vendor == 'Costco':
        # Costco body has "Your Order\n<product name>"
        m = re.search(r'(?:Your Order|LG|Samsung|Sony|Dyson|Dell|HP|Apple)\s+([A-Za-z0-9][^\n]{8,60})', plain[:3000])
        if m:
            return m.group(0).strip()[:80]

    if vendor == 'lululemon':
        m = re.search(
            r"((?:Men's|Women's|Unisex)?\s*[A-Z][a-zA-Z\s]+"
            r"(?:Short|Pant|Top|Jacket|Vest|Hoodie|Shirt|Tee|Bra|Legging|Tight|Shorts)[a-zA-Z\s]*)",
            plain[:3000]
        )
        if m:
            return m.group(0).strip()[:80]

    if vendor == 'WHOOP':
        m = re.search(r'(WHOOP\s+[\d\.]+[^\n]{0,30}|WHOOP\s+[A-Za-z]+[^\n]{0,30})', plain[:2000])
        if m:
            return m.group(1).strip()[:60]

    return ''


def _extract_total(plain: str) -> str:
    """Find the order total (not per-item price)."""
    patterns = [
        r'[Oo]rder\s+[Tt]otal[:\s]+\$\s*([\d,]+\.\d{2})',
        r'[Tt]otal[:\s]+\$\s*([\d,]+\.\d{2})',
        r'[Aa]mount[:\s]+\$\s*([\d,]+\.\d{2})',
        r'[Ss]ubtotal[:\s]+\$\s*([\d,]+\.\d{2})',
    ]
    for pattern in patterns:
        m = re.search(pattern, plain[:4000])
        if m:
            return f'${m.group(1)}'
    # Fallback: first dollar amount in body
    m = re.search(r'\$\s*([\d,]+\.\d{2})', plain[:2000])
    return f'${m.group(1)}' if m else ''


def _extract_tracking(plain: str) -> str:
    for pattern in [
        r'[Tt]racking\s*[Nn]umber[:\s]+([A-Z0-9]{10,})',
        r'\b(1Z[A-Z0-9]{16})\b',
        r'\b(\d{20,22})\b',
    ]:
        m = re.search(pattern, plain[:3000])
        if m:
            return m.group(1)
    return ''


def _extract_status(subject: str) -> str:
    lower = subject.lower()
    if any(w in lower for w in ('shipped', 'on its way', 'in transit', 'dispatched', 'has shipped')):
        return 'Shipped'
    if any(w in lower for w in ('delivered', 'arrived', 'installed', 'has been installed',
                                 'has been delivered')):
        return 'Delivered'
    if any(w in lower for w in ('confirmed', 'received your order', 'we got your order',
                                 'is confirmed', 'order confirmed')):
        return 'Confirmed'
    if 'cancel' in lower:
        return 'Cancelled'
    if 'placed' in lower or 'successfully placed' in lower:
        return 'Placed'
    if 'preparing' in lower or 'processing' in lower:
        return 'Processing'
    return 'Update'


def process(email: dict, state: dict) -> str | None:
    vendor = email['vendor']
    subject = email['subject']
    plain = email['plain'] or ''
    date = email['date']

    if not _is_order_email(subject, plain):
        return None

    status = _extract_status(subject)
    order_num = _extract_order_number(vendor, subject, plain)
    tracking = _extract_tracking(plain)
    state_key = order_num or f'{vendor}:{date}'

    known_orders = state.setdefault('order_numbers', {})
    filename = f'{vendor}.md'

    if order_num and order_num in known_orders:
        # Status update only — compact block
        prev_status = known_orders[order_num].get('status', '')
        if status == prev_status:
            return None  # Nothing changed, skip

        lines = [f'↳ {date}: **{status}**']
        if tracking:
            lines.append(f'  Tracking: {tracking}')

        append_to_memory('Orders', filename, '\n'.join(lines))
        known_orders[order_num]['status'] = status

        summary = f'{vendor} #{order_num} → {status}'
        if tracking:
            summary += f' ({tracking[:20]})'
        logger.info(f'Orders/{filename}: status update {summary}')
        return summary

    # First time seeing this order — full entry
    product = _extract_product(vendor, subject, plain)
    total = _extract_total(plain)

    lines = [f'## {date} — Order #{order_num or "N/A"} [{status}]']
    lines.append(f'**Vendor:** {vendor}')
    if product:
        lines.append(f'**Product:** {product}')
    if total:
        lines.append(f'**Amount:** {total}')
    if tracking:
        lines.append(f'**Tracking:** {tracking}')
    lines.append('---')

    append_to_memory('Orders', filename, '\n'.join(lines))

    if order_num:
        known_orders[order_num] = {'vendor': vendor, 'status': status, 'date': date}

    label = f'{vendor} #{order_num}' if order_num else vendor
    details = []
    if product:
        details.append(product[:40])
    if total:
        details.append(total)
    summary = label
    if details:
        summary += ': ' + ' — '.join(details)
    summary += f' [{status}]'
    logger.info(f'Orders/{filename}: new order — {summary}')
    return summary
