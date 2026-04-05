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

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from ..writers import append_to_memory, update_in_memory
from ..scanner import html_to_text

logger = logging.getLogger('EmailExtractor.Orders')

GEMINI_FREE_SECRET = os.path.join(BASE_DIR, 'config', 'gemini_ai_studio_secret')
GEMINI_FREE_MODEL = os.getenv('GEMINI_FREE_MODEL', 'gemini-2.5-flash-lite')

ORDER_KEYWORDS = (
    'order', 'shipped', 'delivered', 'delivery', 'in transit', 'dispatched',
    'arrived', 'installed', 'confirmed', 'placed', 'cancel', 'tracking',
    'pillpack', 'shipment',
)

EXTRACT_PROMPT = """\
Extract order details from this {vendor} email.

Return ONLY valid JSON in this exact format:
{{
  "items": [{{"name": "...", "qty": "1", "price": "$X.XX"}}],
  "total": "$X.XX",
  "tracking": ""
}}

Rules:
- items: list every individual product or line item. Include memberships and subscriptions.
- qty: quantity as a string, default "1"
- price: per-item price with $ sign, or "" if not shown
- total: the amount actually charged (after tax/shipping), with $ sign, or "" if not found
- tracking: UPS/FedEx/USPS tracking number if present, or ""
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
    if plain:
        return plain
    html = email.get('html') or ''
    if html:
        text, _ = html_to_text(html)
        return text
    return ''


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
    if 'cancel' in lower:
        return 'Cancelled'
    if 'placed' in lower or 'successfully placed' in lower:
        return 'Placed'
    if 'preparing' in lower or 'processing' in lower or 'pricing is now available' in lower:
        return 'Processing'
    return 'Update'


def _item_key(name: str) -> str:
    return re.sub(r'\s+', '_', name[:30].lower().strip())


# ── Gemini extraction ────────────────────────────────────────────────────────

def _get_gemini_client():
    try:
        from google import genai
        key = open(GEMINI_FREE_SECRET).read().strip()
        return genai.Client(api_key=key)
    except Exception as e:
        logger.error(f'Gemini client init failed: {e}')
        return None


def _extract_items_llm(vendor: str, subject: str, body: str) -> dict:
    """
    Ask Gemini to extract items, total, and tracking from an order email.
    Returns {items: [{name, qty, price}], total, tracking}.
    Falls back to empty dict on failure.
    """
    client = _get_gemini_client()
    if not client:
        return {}
    try:
        prompt = EXTRACT_PROMPT.format(
            vendor=vendor,
            subject=subject,
            body=body[:4000],
        )
        response = client.models.generate_content(
            model=GEMINI_FREE_MODEL,
            contents=prompt,
        )
        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        logger.error(f'Gemini order extraction failed ({vendor}): {e}')
        return {}


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
            # Old-format state entry with no items dict — fall back to append
            append_to_memory('Orders', filename, f'↳ {date}: **{status}**')

        prev['status'] = status
        summary = f'{vendor} #{order_num} → {status}'
        logger.info(f'Orders/{filename}: status update — {summary}')
        return summary

    # New order — call LLM for item extraction
    extracted = _extract_items_llm(vendor, subject, body)
    items = extracted.get('items', [])
    total = extracted.get('total', '')
    tracking = extracted.get('tracking', '')

    lines = [f'## {date} — Order #{order_num or "N/A"} [{status}]']
    lines.append(f'**Vendor:** {vendor}')
    if total:
        lines.append(f'**Total:** {total}')
    if tracking:
        lines.append(f'**Tracking:** {tracking}')
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
        }

    n = len(items)
    label = f'{vendor} #{order_num}' if order_num else vendor
    summary = f'{label}: {n} item{"s" if n != 1 else ""}'
    if total:
        summary += f' — {total}'
    summary += f' [{status}]'
    logger.info(f'Orders/{filename}: new order — {summary}')
    return summary
