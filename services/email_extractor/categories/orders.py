"""
Orders category processor.
First email for an order: full entry (product, price, status).
Subsequent emails: compact status-only update.
State tracks seen order numbers to detect duplicates.

Costco: multi-item support — extracts all line items from HTML body,
tracks per-item status since items may ship in separate shipments.
"""
import re
import logging
from ..writers import append_to_memory, update_in_memory

logger = logging.getLogger('EmailExtractor.Orders')

ORDER_KEYWORDS = (
    'order', 'shipped', 'delivered', 'delivery', 'in transit', 'dispatched',
    'arrived', 'installed', 'confirmed', 'placed', 'cancel', 'tracking',
    'pillpack', 'shipment',
)


def _is_order_email(subject: str, plain: str) -> bool:
    combined = (subject + ' ' + plain[:500]).lower()
    return any(kw in combined for kw in ORDER_KEYWORDS)


def _get_body(email: dict) -> str:
    """Return best available plain text: plain first, HTML-converted fallback."""
    plain = email.get('plain') or ''
    if plain:
        return plain
    html = email.get('html') or ''
    if html:
        from ..scanner import html_to_text
        text, _ = html_to_text(html)
        return text
    return ''


def _extract_order_number(vendor: str, subject: str, body: str) -> str:
    patterns = [
        r'[Oo]rder\s*[#Nn]o?\.?\s*([A-Z0-9\-]{6,})',
        r'[Oo]rder\s+[Nn]umber\s+(\d{8,})',
        r'[Oo]rder\s+number\s+is\s+([A-Z][A-Z0-9]{4,})',  # WHOOP plain text
        r'order=([A-Z][A-Z0-9]{4,})',                       # WHOOP URL param
        r'\[([a-z][0-9]{15,})\]',                           # lululemon
        r'#(\d{8,})',
    ]
    for text in (subject, body[:3000]):
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)
    return ''


def _extract_pillpack_shipment_key(body: str, email_date: str) -> str:
    """
    Derive a stable dedup key for a PillPack shipment.
    Tries to extract the estimated arrival date; falls back to email year-month.
    """
    m = re.search(
        r'(?:arrive by|arriving by|arrives by|scheduled for|arrival by)'
        r'\s+(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?'
        r'([A-Z][a-z]+\.?\s+\d{1,2})',
        body[:1000],
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip().rstrip('.')
        # Normalise "Mar 29" → "2026-03" (year from email_date)
        year = email_date[:4]
        months = {'jan':'01','feb':'02','mar':'03','apr':'04','may':'05','jun':'06',
                  'jul':'07','aug':'08','sep':'09','oct':'10','nov':'11','dec':'12'}
        abbr = raw[:3].lower()
        if abbr in months:
            return f'{year}-{months[abbr]}'
    # Fallback: year-month of the email itself
    return email_date[:7]


def _extract_items_costco(html: str) -> list[dict]:
    """
    Extract all line items from a Costco HTML email.
    Product name, Item #, and price are in separate <td> cells — search
    the tag-stripped, whitespace-normalised text for sequential patterns.
    Returns list of {name, item_num, price}.
    """
    import html as html_mod
    # Strip tags, decode entities, collapse whitespace to single spaces
    flat = re.sub(r'<[^>]+>', ' ', html)
    flat = html_mod.unescape(flat)
    flat = re.sub(r'[\u200b\u200c]', '', flat)   # remove zero-width chars
    flat = re.sub(r'\s+', ' ', flat)

    def _clean_name(raw: str) -> str:
        # Strip leading conditional-comment junk ending in "Standard --> "
        raw = re.sub(r'^.*?Standard\s*-->\s*', '', raw, flags=re.IGNORECASE)
        return raw.strip()[:100]

    found = {}
    # Confirmation: {name} Item # {num} ${price} Quantity
    for m in re.finditer(
        r'([A-Z][A-Za-z0-9][^\$]{5,100}?)\s+Item\s+#\s*(\d{5,})'
        r'[^$]{0,60}\$([\d,]+\.\d{2})\s+Quantity',
        flat[:30000],
    ):
        item_num = m.group(2)
        if item_num not in found:
            name = _clean_name(m.group(1))
            if name and re.search(r'[a-z]', name):
                found[item_num] = {'name': name, 'item_num': item_num,
                                   'price': f'${m.group(3)}'}

    # Shipped: {name} Item # {num} Quantity N Subtotal ${price}
    for m in re.finditer(
        r'([A-Z][A-Za-z0-9][^\$]{5,100}?)\s+Item\s+#\s*(\d{5,})'
        r'\s+Quantity\s+\d+[^$]{0,60}Subtotal\s+\$([\d,]+\.\d{2})',
        flat[:30000],
    ):
        item_num = m.group(2)
        if item_num not in found:
            name = _clean_name(m.group(1))
            if name and re.search(r'[a-z]', name):
                found[item_num] = {'name': name, 'item_num': item_num,
                                   'price': f'${m.group(3)}'}

    return list(found.values())


def _extract_product(vendor: str, subject: str, body: str) -> str:
    if vendor == 'Amazon':
        m = re.search(r'Shipped:\s*"([^"]+)"(?:\s*and\s*(\d+)\s*more)?', subject)
        if m:
            name = m.group(1).rstrip('.')
            return f'{name} (+{m.group(2)} more)' if m.group(2) else name

    if vendor == 'Amazon Pharmacy':
        m = re.search(r'containing\s+(\d+\s+of\s+\d+\s+medication)', body[:500])
        return m.group(1) if m else 'PillPack medications'

    if vendor == 'lululemon':
        m = re.search(
            r"((?:Men's|Women's|Unisex)?\s*[A-Z][a-zA-Z\s]+"
            r"(?:Short|Pant|Top|Jacket|Vest|Hoodie|Shirt|Tee|Bra|Legging|Tight|Shorts)[a-zA-Z\s]*)",
            body[:3000]
        )
        if m:
            return m.group(0).strip()[:80]

    if vendor == 'WHOOP':
        # Extract items+prices from ORDER SUMMARY, pick paid items first
        m = re.search(r'ORDER SUMMARY\s*(.*?)\s*(?:Subtotal|Total Due)', body, re.DOTALL | re.IGNORECASE)
        if m:
            section = m.group(1).replace('\r', '')  # normalise CRLF
            item_names = re.findall(r'^([A-Z][A-Za-z0-9][A-Za-z0-9 \+]{3,50})$', section, re.MULTILINE)
            prices = re.findall(r'\$(\d+\.\d{2})', section)
            item_names = [i.strip() for i in item_names if i.strip()]
            # Pair items with prices; prefer items with non-zero price
            paired = list(zip(item_names, prices)) if prices else [(n, '0.00') for n in item_names]
            paid = [name for name, price in paired if price != '0.00']
            items = paid if paid else item_names
            if items:
                return ', '.join(items[:3])
        # Fallback
        m = re.search(r'(WHOOP\s+(?:MG|4\.0|5\.0)[^\n]{0,30})', body[:2000])
        if m:
            return m.group(1).strip()[:60]

    return ''


def _extract_total(body: str) -> str:
    """Find the order total (not per-item price)."""
    patterns = [
        r'[Oo]rder\s+[Tt]otal[:\s]+\$\s*([\d,]+\.\d{2})',
        r'[Tt]otal[:\s]+\$\s*([\d,]+\.\d{2})',
        r'[Aa]mount[:\s]+\$\s*([\d,]+\.\d{2})',
        r'[Ss]ubtotal[:\s]+\$\s*([\d,]+\.\d{2})',
    ]
    for pattern in patterns:
        m = re.search(pattern, body[:4000])
        if m:
            return f'${m.group(1)}'
    m = re.search(r'\$\s*([\d,]+\.\d{2})', body[:2000])
    return f'${m.group(1)}' if m else ''


def _extract_tracking(body: str) -> str:
    for pattern in [
        r'[Tt]racking\s*[Nn]umber[:\s]+([A-Z0-9]{10,})',
        r'\b(1Z[A-Z0-9]{16})\b',
        r'\b(\d{20,22})\b',
    ]:
        m = re.search(pattern, body[:3000])
        if m:
            return m.group(1)
    return ''


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


def process(email: dict, state: dict) -> str | None:
    vendor = email['vendor']
    subject = email['subject']
    body = _get_body(email)
    date = email['date']

    if not _is_order_email(subject, body):
        return None

    status = _extract_status(subject)
    order_num = _extract_order_number(vendor, subject, body)
    tracking = _extract_tracking(body)

    known_orders = state.setdefault('order_numbers', {})
    filename = f'{vendor}.md'

    # ── Costco: multi-item path ─────────────────────────────────────────────
    if vendor == 'Costco':
        items = _extract_items_costco(email.get('html') or '')

        if order_num and order_num in known_orders:
            # Update [Status] in-place on each affected item line
            prev_items = known_orders[order_num].get('items', {})
            updated = []
            for item in items:
                num = item['item_num']
                if num not in prev_items:
                    continue
                prev_status = prev_items[num].get('status', '')
                if status == prev_status:
                    continue
                name = prev_items[num]['name']
                price = prev_items[num]['price']
                prev_date = prev_items[num].get('date', '')
                old_line = f'- {name} — {price} [{prev_status}] {prev_date}'.rstrip()
                new_line = f'- {name} — {price} [{status}] {date}'
                update_in_memory('Orders', filename, old_line, new_line)
                prev_items[num]['status'] = status
                prev_items[num]['date'] = date
                updated.append({'name': name, 'price': price})

            if not updated:
                return None

            item_lines = '; '.join(f'{i["name"][:40]} — {i["price"]}' for i in updated)
            summary = f'Costco #{order_num} → {status}: {item_lines}'
            if tracking:
                summary += f' | Tracking: {tracking}'
            logger.info(f'Orders/{filename}: status update {summary}')
            return summary

        # First time — full entry with all items
        total = _extract_total(body)
        lines = [f'## {date} — Order #{order_num or "N/A"} [{status}]']
        lines.append(f'**Vendor:** {vendor}')
        if total:
            lines.append(f'**Total:** {total}')
        lines.append('')
        for item in items:
            lines.append(f'- {item["name"]} — {item["price"]} [{status}] {date}')
        if not items:
            lines.append('*(items not extracted)*')
        lines.append('---')

        append_to_memory('Orders', filename, '\n'.join(lines))

        if order_num:
            item_dict = {
                i['item_num']: {'name': i['name'], 'price': i['price'], 'status': status, 'date': date}
                for i in items
            }
            known_orders[order_num] = {'vendor': vendor, 'date': date, 'items': item_dict}

        n = len(items)
        summary = f'Costco #{order_num}: {n} item{"s" if n != 1 else ""}'
        if total:
            summary += f' — {total}'
        summary += f' [{status}]'
        logger.info(f'Orders/{filename}: new order — {summary}')
        return summary

    # ── Amazon Pharmacy: month-based dedup (no order number) ───────────────
    if vendor == 'Amazon Pharmacy':
        if status == 'Update':
            return None  # skip generic/recall notices for the order log
        shipment_key = _extract_pillpack_shipment_key(body, date)
        state_key = f'pillpack:{shipment_key}'

        product = _extract_product(vendor, subject, body)
        total = _extract_total(body)

        if state_key in known_orders:
            prev_status = known_orders[state_key].get('status', '')
            if status == prev_status:
                return None
            # Update status line in-place
            prev_product = known_orders[state_key].get('product', product)
            old_line = f'**Status:** [{prev_status}]'
            new_line = f'**Status:** [{status}] {date}'
            if not update_in_memory('Orders', filename, old_line, new_line):
                # fallback: old entries may not have date on first write
                update_in_memory('Orders', filename,
                                 f'**Status:** {prev_status}', new_line)
            known_orders[state_key]['status'] = status
            summary = f'Amazon Pharmacy: {prev_product} → {status}'
            logger.info(f'Orders/{filename}: status update {summary}')
            return summary

        # First entry for this shipment
        status_line = f'**Status:** [{status}] {date}'
        lines = [f'## {date} — PillPack {shipment_key} [{status}]']
        lines.append(f'**Vendor:** Amazon Pharmacy')
        lines.append(status_line)
        if product:
            lines.append(f'**Medications:** {product}')
        if total:
            lines.append(f'**Amount:** {total}')
        lines.append('---')

        append_to_memory('Orders', filename, '\n'.join(lines))
        known_orders[state_key] = {
            'vendor': vendor, 'status': status, 'date': date, 'product': product,
        }
        summary = f'Amazon Pharmacy: {product or "PillPack"} [{status}]'
        if total:
            summary += f' — {total}'
        logger.info(f'Orders/{filename}: new shipment — {summary}')
        return summary

    # ── Single-item path (all other vendors) ───────────────────────────────
    if order_num and order_num in known_orders:
        prev_status = known_orders[order_num].get('status', '')
        if status == prev_status:
            return None

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

    # First time — full entry
    product = _extract_product(vendor, subject, body)
    total = _extract_total(body)

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
