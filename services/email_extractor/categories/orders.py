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
from toolbox.lib.entity_ids import order_entity_id, render_entity_comment

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
        r'[Oo]rder\s*(?:confirmation\s*)?[#Nn]o?\.?\s*([A-Za-z0-9\-]{6,})',
        r'[Oo]rder\s+[Nn]umber\s+([A-Za-z0-9\-]{6,})',
        r'[Oo]rder\s+([A-Z][A-Z0-9\-]{5,})',
        r'[Oo]rder\s+[Nn]umber\s+is\s+([A-Za-z0-9\-]{4,})',
        r'order=([A-Za-z0-9\-]{4,})',
        r'\[([a-z0-9]{15,})\]',
        r'#([A-Za-z0-9\-]{6,})',
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
    if any(w in lower for w in ('confirmed', 'confirmation', 'received your order', 'we got your order',
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


def _format_item_line(name: str, qty: str, price: str, status: str, date: str) -> str:
    qty = (qty or '1').strip()
    qty_suffix = f' ×{qty}' if qty != '1' else ''
    price = (price or '').strip()
    price_part = f' — {price}' if price else ''
    return f'- {name}{qty_suffix}{price_part} [{status}] {date}'


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
    if vendor == 'Costco':
        return 'https://www.costco.com/OrderStatusView'
    if vendor == 'Target':
        return 'https://www.target.com/orders'
    if vendor == 'Best Buy':
        return 'https://www.bestbuy.com/identity/global/signin'
    if vendor == 'Walmart':
        return 'https://www.walmart.com/orders'
    if vendor == 'lululemon':
        return 'https://shop.lululemon.com/account/orders'
    if vendor == 'WHOOP':
        return 'https://shop.whoop.com/account/'
    return ''


def _extract_total_fallback(subject: str, body: str) -> str:
    text = f'{subject}\n{body[:5000]}'
    patterns = [
        r'(?:order total|grand total|total charged|amount charged|payment total|total)'
        r'[^$\n]{0,40}\$\s*([\d,]+\.\d{2})',
        r'\$\s*([\d,]+\.\d{2})[^.\n]{0,40}(?:total|charged|payment)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return f'${m.group(1)}'
    return ''


def _looks_like_product_line(line: str) -> bool:
    lower = line.lower().strip()
    if len(lower) < 4:
        return False
    reject_tokens = (
        'order #', 'tracking', 'subtotal', 'total', 'tax', 'shipping', 'delivery',
        'arriving', 'returns', 'return', 'payment', 'visa', 'mastercard', 'discover',
        'account ending', 'gift card', 'billing address', 'shipping address',
    )
    if any(token in lower for token in reject_tokens):
        return False
    return '$' in line


def _looks_like_section_header(line: str) -> bool:
    lower = line.lower().strip(' :')
    return lower in {
        'items ordered',
        'items in this shipment',
        'shipment details',
        'order summary',
        'item details',
        'item description',
        'your gear',
        'order details',
    }


def _looks_like_name_only_product_line(line: str) -> bool:
    lower = line.lower().strip()
    if len(lower) < 4 or '$' in line:
        return False
    reject_tokens = (
        'order #', 'tracking', 'subtotal', 'total', 'tax', 'shipping', 'delivery',
        'arriving', 'returns', 'return', 'payment', 'visa', 'mastercard', 'discover',
        'account ending', 'gift card', 'billing address', 'shipping address',
        'order status', 'track your package', 'carrier', 'estimated delivery',
        'quantity', 'qty', 'size', 'color', 'price', 'item description',
    )
    if any(token in lower for token in reject_tokens):
        return False
    if re.fullmatch(r'[A-Z0-9\- ]{3,}', line.strip()):
        return False
    words = re.findall(r'[A-Za-z0-9]+', line)
    return len(words) >= 2


def _extract_qty_nearby(lines: list[str], start_idx: int) -> str:
    for offset in range(1, 3):
        idx = start_idx + offset
        if idx >= len(lines):
            break
        candidate = re.sub(r'\s+', ' ', lines[idx]).strip(' •\t')
        if not candidate:
            continue
        match = re.search(r'\b(?:qty|quantity)[: ]+(\d+)\b', candidate, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'^(\d+)\s*(?:x|×)\b', candidate, re.IGNORECASE)
        if match:
            return match.group(1)
    return '1'


def _extract_items_fallback(body: str) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    lines = body.splitlines()
    for raw_line in lines:
        line = re.sub(r'\s+', ' ', raw_line).strip(' •\t')
        if not _looks_like_product_line(line):
            continue

        qty = '1'
        qty_match = re.search(r'^(?:qty[: ]*)?(\d+)\s*[x×]\s+(.+)$', line, re.IGNORECASE)
        if qty_match:
            qty = qty_match.group(1)
            line = qty_match.group(2).strip()

        price_match = re.search(r'\$\s*([\d,]+\.\d{2})\b', line)
        if not price_match:
            continue
        price = f'${price_match.group(1)}'

        name = line[:price_match.start()].strip(' -:\u2022')
        if not name:
            after_price = line[price_match.end():].strip(' -:\u2022')
            if after_price:
                name = after_price
        if not name or len(name) < 2:
            continue

        leading_qty = re.search(r'\bqty[: ]*(\d+)\b', name, re.IGNORECASE)
        if leading_qty:
            qty = leading_qty.group(1)
            name = re.sub(r'\bqty[: ]*\d+\b', '', name, flags=re.IGNORECASE).strip(' -:')

        key = (name.lower(), qty, price)
        if key in seen:
            continue
        seen.add(key)
        items.append({'name': name, 'qty': qty, 'price': price})
        if len(items) >= 8:
            break

    if items:
        return items

    in_item_section = False
    for idx, raw_line in enumerate(lines):
        line = re.sub(r'\s+', ' ', raw_line).strip(' •\t')
        if not line:
            if in_item_section:
                in_item_section = False
            continue
        if _looks_like_section_header(line):
            in_item_section = True
            continue
        if not in_item_section:
            continue
        if not _looks_like_name_only_product_line(line):
            continue

        qty = _extract_qty_nearby(lines, idx)
        key = (line.lower(), qty, '')
        if key in seen:
            continue
        seen.add(key)
        items.append({'name': line, 'qty': qty, 'price': ''})
        if len(items) >= 8:
            break

    return items


def _merge_extracted_order_data(subject: str, body: str, extracted: dict) -> dict:
    merged = dict(extracted or {})
    items = list(merged.get('items') or [])
    if not items:
        items = _extract_items_fallback(body)
    total = merged.get('total') or _extract_total_fallback(subject, body)
    merged['items'] = items
    merged['total'] = total
    return merged


# ── Gemini extraction ────────────────────────────────────────────────────────

def _fallback_extract_items(body: str) -> list[dict]:
    """Deterministic fallback for item extraction if LLM fails."""
    items = []
    # Common pattern: "Items: 1 of Widget A" or "1 of Widget A"
    m_items = re.findall(r'(\d+)\s+of\s+([^.\n]{2,60})', body[:4000])
    for qty, name in m_items:
        items.append({'name': name.strip(), 'qty': qty, 'price': ''})
    
    # Another pattern: bullet points with prices
    # • Widget B — $12.34
    m_bullets = re.findall(r'[•*-]\s+([^—\n]{2,60})—\s*(\$\s*[\d,]+\.\d{2})', body[:4000])
    for name, price in m_bullets:
        items.append({'name': name.strip(), 'qty': '1', 'price': price.strip()})
        
    return items


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

def process(email: dict, state: dict) -> dict | None:
    vendor = email['vendor']
    subject = email['subject']
    body = _get_body(email)
    date = email['date']

    if not _is_order_email(subject, body):
        return None

    status = _extract_status(subject)
    filename = f'{vendor}.md'
    known_orders = state.setdefault('order_numbers', {})

    # Simple confidence scoring for Spec v2
    confidence = 1.0
    if vendor == 'UnknownVendor': confidence -= 0.4

    # ── Amazon Pharmacy: month-based dedup key ──────────────────────────────
    if vendor == 'Amazon Pharmacy':
        if status == 'Update':
            return None
        order_key = f'pillpack:{_extract_pillpack_shipment_key(body, date)}'

        status_icons = {'Shipped': '🚚', 'Delivered': '✅', 'Confirmed': '📩', 'Out for Delivery': '📦'}
        icon = status_icons.get(status, '📝')

        if order_key in known_orders:
            prev = known_orders[order_key]
            prev_status = prev.get('status', '')
            if status == prev_status:
                return None
            
            # 1. Update in-place in Markdown
            old_line = prev.get('status_line') or f'**Status:** [{prev_status}] {prev.get("date", "")}'.rstrip()
            new_line = f'**Status:** [{status}] {date}'
            if not update_in_memory('Orders', filename, old_line, new_line):
                fallback_old_line = f'**Status:** [{prev_status}]'
                update_in_memory('Orders', filename, fallback_old_line, new_line)
            
            # 2. Update Header Icon
            month_key = order_key.split(":", 1)[1]
            old_header = f'## {prev.get("date", "")} — PillPack {month_key} [{prev_status}]'
            new_header = f'## {date} — PillPack {month_key} [{status}] {icon}'
            update_in_memory('Orders', filename, old_header, new_header)

            # 3. Update State
            prev['status'] = status
            prev['date'] = date
            prev['status_line'] = new_line
            
            summary = f'{vendor} → {status} {icon}'
            logger.info(f'Orders/{filename}: status update {summary}')
            return {'summary': summary, 'confidence': 1.0, 'category': 'orders'}

        # New Shipment
        extracted = _merge_extracted_order_data(subject, body, _extract_items_llm(vendor, subject, body))
        items = extracted.get('items', [])
        total = extracted.get('total', '')
        product = items[0]['name'] if items else 'PillPack medications'
        status_line = f'**Status:** [{status}] {date}'

        lines = [f'## {date} — PillPack {order_key.split(":", 1)[1]} [{status}] {icon}']
        lines.append(render_entity_comment(order_entity_id(vendor, order_key)))
        lines.append(f'**Vendor:** {vendor}')
        lines.append(status_line)
        if product:
            lines.append(f'**Medications:** {product}')
        if total:
            lines.append(f'**Amount:** {total}')
        lines.append('---')

        append_to_memory('Orders', filename, '\n'.join(lines))
        known_orders[order_key] = {
            'vendor': vendor, 'status': status, 'date': date, 'product': product,
            'status_line': status_line,
            'entity_id': order_entity_id(vendor, order_key),
        }
        summary = f'{vendor}: {product} [{status}] {icon}'
        if total:
            summary += f' — {total}'
        logger.info(f'Orders/{filename}: new shipment — {summary}')
        return {'summary': summary, 'confidence': 1.0, 'category': 'orders'}

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
            old_line = _format_item_line(
                item['name'],
                item.get('qty', '1'),
                item.get('price', ''),
                item_status,
                item.get('date', ''),
            )
            new_line = _format_item_line(
                item['name'],
                item.get('qty', '1'),
                item.get('price', ''),
                status,
                date,
            )
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
            ship_extract = _merge_extracted_order_data(subject, body, _extract_items_llm(vendor, subject, body))
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
        return {'summary': summary, 'confidence': 1.0, 'category': 'orders'}

    # New order — call LLM for item extraction
    extracted = _merge_extracted_order_data(subject, body, _extract_items_llm(vendor, subject, body))
    items = extracted.get('items', [])
    if not items:
        items = _fallback_extract_items(body)
        
    total = extracted.get('total', '')
    if not total:
        # Simple total fallback: "Order Total: $45.99"
        m_total = re.search(r'(?:total|amount due|grand total)[:\s]*(\$\s*[\d,]+\.\d{2})', body[:4000], re.IGNORECASE)
        if m_total:
            total = m_total.group(1).strip()

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

    entity_key = order_num or f'{date}|{subject[:120]}'
    lines = [f'## {date} — Order #{order_num or "N/A"} [{status}]']
    lines.append(render_entity_comment(order_entity_id(vendor, entity_key)))
    lines.append(f'**Vendor:** {vendor}')
    lines.append(f'**Order Number:** {order_num or "N/A"}')
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
        lines.append(_format_item_line(name, qty, price, status, date))
    if not items:
        lines.append('*(items not extracted)*')
    lines.append('---')

    append_to_memory('Orders', filename, '\n'.join(lines))

    if order_num:
        item_dict = {
            _item_key(i.get('name', '')): {
                'name': i.get('name', ''),
                'qty': i.get('qty', '1'),
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
            'entity_id': order_entity_id(vendor, entity_key),
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
    return {
        'summary': summary,
        'confidence': max(0.0, confidence),
        'category': 'orders'
    }
