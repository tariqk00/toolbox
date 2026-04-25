"""
Orders category processor.
Regex handles order number + status (structural, reliable).
Gemini handles item extraction (name, qty, price, total, tracking)
so no per-vendor parsing code is needed.

First email for an order: full entry with all items.
Subsequent emails: compact status-only update in-place per item.
"""
import json
import logging
import os
import re
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from ..writers import append_to_memory, update_in_memory
from ..enrichment import enrich_order
from ..scanner import html_to_text

logger = logging.getLogger('EmailExtractor.Orders')


ORDER_KEYWORDS = (
    'order', 'shipped', 'delivered', 'delivery', 'in transit', 'dispatched',
    'arrived', 'installed', 'confirmed', 'placed', 'cancel', 'tracking',
    'pillpack', 'shipment', 'return', 'refund', 'exchange',
)

EXTRACT_PROMPT = """\
Extract order details from this {vendor} email.

Return ONLY valid JSON in this exact format:
{{
  "items": [{{"name": "...", "qty": "1", "price": "$X.XX"}}],
  "total": "$X.XX",
  "carrier": "",
  "tracking": "",
  "estimated_delivery": ""
}}

Rules:
- items: list every individual product or line item. Include memberships and subscriptions.
- qty: quantity as a string, default "1"
- price: per-item price with $ sign, or "" if not shown
- total: the amount actually charged (after tax/shipping), with $ sign, or "" if not found
- carrier: UPS, FedEx, USPS, DHL, Amazon, OnTrac, or "" if not found
- tracking: UPS/FedEx/USPS tracking number if present, or ""
- estimated_delivery: delivery ETA/date as YYYY-MM-DD if present, or ""
- Use "" for missing fields, not null
- Return only JSON, no explanation

Subject: {subject}

Email:
{body}"""


# ── Helpers ─────────────────────────────────────────────────────────────────

def _is_order_email(subject: str, plain: str) -> bool:
    combined = (subject + ' ' + plain[:500]).lower()
    return any(kw in combined for kw in ORDER_KEYWORDS)


def _get_body(email: dict) -> str:
    plain = email.get('plain') or ''
    html_raw = email.get('html') or ''
    # If plain contains HTML tags it's not true plain text — use html_to_text instead
    if plain and not re.search(r'<[a-zA-Z]+[\s>]', plain[:500]):
        return plain
    if html_raw:
        text, _ = html_to_text(html_raw)
        return text
    return plain


def _prep_for_llm(body: str) -> str:
    """Strip noise before sending to LLM: HTML entities, invisible chars, URLs, whitespace."""
    import html as html_mod
    body = html_mod.unescape(body)
    # Remove invisible/zero-width Unicode used in email templates
    body = re.sub(r'[\u034f\u00ad\u200b-\u200f\u2028\u2029\ufeff]', '', body)
    # Remove URLs — they're tracking links, not useful for extraction
    body = re.sub(r'https?://\S+', '', body)
    # Collapse tabs and spaces
    body = re.sub(r'[ \t]+', ' ', body)
    # Drop whitespace-only lines, collapse 3+ blank lines to 2
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def _extract_order_number(vendor: str, subject: str, body: str) -> str:
    patterns = [
        r'[Oo]rder\s*[#Nn]o?\.?\s*([A-Z0-9\-]{6,})',
        r'[Oo]rder\s+[Nn]umber\s+(\d{8,})',
        r'[Oo]rder\s+[Nn]umber\s+is\s+([A-Z][A-Z0-9]{4,})',
        r'order=([A-Z][A-Z0-9]{4,})',
        r'\[([a-z][0-9]{15,})\]',
        r'#(\d{8,})',
    ]
    for text in (subject, body[:3000]):
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
    return ''


def _extract_pillpack_shipment_key(body: str, email_date: str) -> str:
    m = re.search(
        r'(?:arrive by|arriving by|arrives by|scheduled for|arrival by)'
        r'\s+(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?'
        r'([A-Z][a-z]+\.?\s+\d{1,2})',
        body[:1000],
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip().rstrip('.')
        year = email_date[:4]
        months = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
        }
        abbr = raw[:3].lower()
        if abbr in months:
            return f'{year}-{months[abbr]}'
    return email_date[:7]


def _extract_status(subject: str) -> str:
    lower = subject.lower()
    if any(w in lower for w in ('shipped', 'on its way', 'in transit', 'dispatched', 'has shipped')):
        return 'Shipped'
    if any(w in lower for w in ('delivered', 'arrived', 'has been delivered',
                                 'installed', 'has been installed')):
        return 'Delivered'
    if any(w in lower for w in ('out for delivery', 'get ready for your', 'landing on your')):
        return 'Out for Delivery'
    if any(w in lower for w in ('confirmed', 'received your order', 'we got your order',
                                 'is confirmed', 'order confirmed', 'thank you for your order')):
        return 'Confirmed'
    if any(w in lower for w in ('refund', 'refunded', 'credit issued', 'return approved',
                                 'return received', 'returned')):
        return 'Refunded'
    if 'cancel' in lower:
        return 'Cancelled'
    if 'placed' in lower or 'successfully placed' in lower:
        return 'Placed'
    if 'preparing' in lower or 'processing' in lower or 'pricing is now available' in lower:
        return 'Processing'
    return 'Update'


def _item_key(name: str) -> str:
    return re.sub(r'\s+', '_', name[:30].lower().strip())


def _extract_carrier(body: str) -> str:
    """Detect carrier name from shipping email body."""
    lower = body[:3000].lower()
    if 'fedex' in lower or 'federal express' in lower:
        return 'FedEx'
    if 'united parcel' in lower or re.search(r'\bups\b', lower):
        return 'UPS'
    if 'usps' in lower or 'postal service' in lower or 'post office' in lower:
        return 'USPS'
    if 'dhl' in lower:
        return 'DHL'
    if 'amazon logistics' in lower or 'amazon delivery' in lower or 'amazon.com/gp/css/trackIt' in body[:3000]:
        return 'Amazon'
    if 'ontrac' in lower:
        return 'OnTrac'
    return ''


def _normalize_delivery_date(raw: str, email_date: str) -> str:
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


def _extract_delivery_date(body: str, email_date: str) -> str:
    date_pattern = (
        r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|'
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s+\d{4})?)'
    )
    patterns = [
        rf'(?:arriving|arrives|arrival|delivery|delivered|estimated delivery|eta)'
        rf'[^.\n]{{0,50}}(?:on|by)?\s*{date_pattern}',
        rf'{date_pattern}[^.\n]{{0,50}}(?:delivery|arriving|arrives|delivered)',
    ]
    for pattern in patterns:
        m = re.search(pattern, body[:4000], re.IGNORECASE)
        if m:
            return _normalize_delivery_date(m.group(1), email_date)
    return ''


def _extract_tracking(body: str) -> str:
    text = body[:5000]
    labeled = re.search(
        r'(?:tracking|tracking number|track(?:ing)? id|shipment id)[^A-Z0-9]{0,20}'
        r'([A-Z0-9][A-Z0-9 -]{7,34}[A-Z0-9])',
        text,
        re.IGNORECASE,
    )
    if labeled:
        value = re.sub(r'[\s-]+', '', labeled.group(1)).strip()
        return re.sub(r'(?i)^number', '', value)

    carrier_patterns = [
        r'\b(1Z[0-9A-Z]{16})\b',                 # UPS
        r'\b(\d{12,22})\b',                      # FedEx
        r'\b(9[234]\d{20,32})\b',                # USPS
    ]
    for pattern in carrier_patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return ''


def _shipping_details(extracted: dict, body: str, email_date: str) -> dict:
    return {
        'carrier': extracted.get('carrier') or _extract_carrier(body),
        'tracking': extracted.get('tracking') or _extract_tracking(body),
        'estimated_delivery': (
            extracted.get('estimated_delivery')
            or extracted.get('delivery_date')
            or extracted.get('eta')
            or _extract_delivery_date(body, email_date)
        ),
    }


def _order_url(vendor: str, order_num: str) -> str:
    """Return a direct order URL for vendors that support it, else empty string."""
    if vendor == 'Amazon' and order_num:
        return f'https://www.amazon.com/gp/your-account/order-details?orderID={order_num}'
    return ''


# ── Gemini extraction ────────────────────────────────────────────────────────

def _extract_items_llm(vendor: str, subject: str, body: str) -> dict:
    """
    Ask Gemini to extract items, total, and tracking from an order email.
    Returns {items: [{name, qty, price}], total, carrier, tracking, estimated_delivery}.
    Falls back to empty dict on failure.
    """
    from toolbox.lib.llm import call_json
    prompt = EXTRACT_PROMPT.format(
        vendor=vendor,
        subject=subject,
        body=_prep_for_llm(body)[:4000],
    )
    return call_json(prompt)


# ── Main processor ───────────────────────────────────────────────────────────

def process(email: dict, state: dict) -> str | None:
    vendor = email['vendor']
    subject = email['subject']
    body = _get_body(email)
    date = email['date']

    if not _is_order_email(subject, body):
        return None

    status = _extract_status(subject)
    filename = f'{vendor}.md'
    known_orders = state.setdefault('order_numbers', {})

    # ── Amazon Pharmacy: month-based dedup key ──────────────────────────────
    if vendor == 'Amazon Pharmacy':
        if status == 'Update':
            return None
        order_key = f'pillpack:{_extract_pillpack_shipment_key(body, date)}'

        if order_key in known_orders:
            prev = known_orders[order_key]
            prev_status = prev.get('status', '')
            if status == prev_status:
                return None
            old_line = f'**Status:** [{prev_status}]'
            new_line = f'**Status:** [{status}] {date}'
            if not update_in_memory('Orders', filename, old_line, new_line):
                update_in_memory('Orders', filename,
                                 f'**Status:** {prev_status}', new_line)
            prev['status'] = status
            summary = f'Amazon Pharmacy → {status}'
            logger.info(f'Orders/{filename}: status update {summary}')
            return summary

        extracted = _extract_items_llm(vendor, subject, body)
        items = extracted.get('items', [])
        total = extracted.get('total', '')
        product = items[0]['name'] if items else 'PillPack medications'

        lines = [f'## {date} — PillPack {order_key.split(":", 1)[1]} [{status}]']
        lines.append(f'**Vendor:** Amazon Pharmacy')
        lines.append(f'**Status:** [{status}] {date}')
        if product:
            lines.append(f'**Medications:** {product}')
        if total:
            lines.append(f'**Amount:** {total}')
        lines.append('---')

        append_to_memory('Orders', filename, '\n'.join(lines))
        known_orders[order_key] = {
            'vendor': vendor, 'status': status, 'date': date, 'product': product,
        }
        summary = f'Amazon Pharmacy: {product} [{status}]'
        if total:
            summary += f' — {total}'
        logger.info(f'Orders/{filename}: new shipment — {summary}')
        return summary

    # ── All other vendors: order-number dedup ───────────────────────────────
    order_num = _extract_order_number(vendor, subject, body)

    if order_num and order_num in known_orders:
        prev = known_orders[order_num]
        prev_status = prev.get('status', '')
        if status == prev_status:
            return None

        # Update per-item status lines
        items = prev.get('items', {})
        updated = []
        for item in items.values():
            item_status = item.get('status', '')
            if status == item_status:
                continue
            old_line = f'- {item["name"]} — {item["price"]} [{item_status}] {item.get("date", "")}'.rstrip()
            new_line = f'- {item["name"]} — {item["price"]} [{status}] {date}'
            update_in_memory('Orders', filename, old_line, new_line)
            item['status'] = status
            item['date'] = date
            updated.append(item)

        if not updated and not items:
            append_to_memory('Orders', filename, f'↳ {date}: **{status}**')

        # Update lifecycle header fields in-place (placeholder → real value)
        carrier = ''
        new_tracking = ''

        if status == 'Shipped':
            ship_extract = _extract_items_llm(vendor, subject, body)
            shipping = _shipping_details(ship_extract, body, date)
            carrier = shipping['carrier']
            new_tracking = shipping['tracking']
            eta = shipping['estimated_delivery']
            new_shipped = f'**Shipped:** {date}'
            if carrier:
                new_shipped += f' | Carrier: {carrier}'
            if new_tracking:
                new_shipped += f' | Tracking: {new_tracking}'
            if eta:
                new_shipped += f' | ETA: {eta}'
            old_shipped = prev.get('shipped_line', '**Shipped:** —')
            if not update_in_memory('Orders', filename, old_shipped, new_shipped):
                # No placeholder (old entry) — append a note instead
                append_to_memory('Orders', filename, f'↳ {new_shipped}')
            prev['shipped_line'] = new_shipped

        elif status == 'Delivered':
            new_delivered = f'**Delivered:** {date}'
            old_delivered = prev.get('delivered_line', '**Delivered:** —')
            if not update_in_memory('Orders', filename, old_delivered, new_delivered):
                append_to_memory('Orders', filename, f'↳ {new_delivered}')
            prev['delivered_line'] = new_delivered

        elif status == 'Refunded':
            append_to_memory('Orders', filename, f'**Refunded:** {date}')

        prev['status'] = status

        # Telegram summary
        summary = f'{vendor} #{order_num}\n{prev_status} → {status}'
        if status == 'Shipped' and (carrier or new_tracking or eta):
            parts = []
            if carrier:
                parts.append(f'Carrier: {carrier}')
            if new_tracking:
                parts.append(f'Tracking: {new_tracking}')
            if eta:
                parts.append(f'ETA: {eta}')
            summary += ' | ' + ' | '.join(parts)
        url = _order_url(vendor, order_num)
        if url:
            summary += f'\n{url}'
        logger.info(f'Orders/{filename}: status update — {vendor} #{order_num} → {status}')
        return summary

    # New order — call LLM for item extraction
    extracted = _extract_items_llm(vendor, subject, body)
    items = extracted.get('items', [])
    total = extracted.get('total', '')
    shipping = _shipping_details(extracted, body, date)
    tracking = shipping['tracking']
    carrier = shipping['carrier'] if status in ('Shipped', 'Out for Delivery', 'Delivered') else ''
    eta = shipping['estimated_delivery']

    # Build lifecycle placeholder lines — updated in-place as order progresses
    shipped_placeholder = '**Shipped:** —'
    delivered_placeholder = '**Delivered:** —'
    if status == 'Shipped':
        shipped_line = f'**Shipped:** {date}'
        if carrier:
            shipped_line += f' | Carrier: {carrier}'
        if tracking:
            shipped_line += f' | Tracking: {tracking}'
        if eta:
            shipped_line += f' | ETA: {eta}'
        shipped_placeholder = shipped_line
    elif status == 'Delivered':
        delivered_placeholder = f'**Delivered:** {eta or date}'

    lines = [f'## {date} — Order #{order_num or "N/A"} [{status}]']
    lines.append(f'**Vendor:** {vendor}')
    url = _order_url(vendor, order_num)
    if url:
        lines.append(f'**URL:** {url}')
    lines.append(f'**Status:** [{status}]')
    lines.append(shipped_placeholder)
    lines.append(delivered_placeholder)
    if carrier:
        lines.append(f'**Carrier:** {carrier}')
    if tracking:
        lines.append(f'**Tracking:** {tracking}')
    if eta:
        lines.append(f'**Estimated Delivery:** {eta}')
    if total:
        lines.append(f'**Total:** {total}')
    lines.append('')
    for item in items:
        name = item.get('name', '').strip()
        price = item.get('price', '').strip()
        qty = item.get('qty', '1').strip()
        qty_suffix = f' \u00d7{qty}' if qty and qty != '1' else ''
        price_part = f' — {price}' if price else ''
        lines.append(f'- {name}{qty_suffix}{price_part} [{status}] {date}')
    if not items:
        lines.append('*(items not extracted)*')
    lines.append('---')

    append_to_memory('Orders', filename, '\n'.join(lines))

    if order_num:
        item_dict = {
            _item_key(i.get('name', '')): {
                'name': i.get('name', ''),
                'price': i.get('price', ''),
                'status': status,
                'date': date,
            }
            for i in items
            if i.get('name')
        }
        known_orders[order_num] = {
            'vendor': vendor, 'date': date, 'status': status, 'items': item_dict,
            'shipped_line': shipped_placeholder,
            'delivered_line': delivered_placeholder,
            'carrier': carrier,
            'tracking': tracking,
            'estimated_delivery': eta,
        }

    n = len(items)
    label = f'{vendor} #{order_num}' if order_num else vendor
    summary = f'{label}: {n} item{"s" if n != 1 else ""}'
    if total:
        summary += f' — {total}'
    if carrier:
        summary += f' | Carrier: {carrier}'
    if tracking:
        summary += f' | Tracking: {tracking}'
    if eta:
        summary += f' | ETA: {eta}'
    summary += f' [{status}]'
    url = _order_url(vendor, order_num)
    if url:
        summary += f'\n{url}'
    summary = enrich_order(summary, vendor, order_num, n, total, status)
    logger.info(f'Orders/{filename}: new order — {label}: {n} items [{status}]')
    return summary
