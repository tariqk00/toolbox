"""
Optional Groq enrichment pass for email extraction pipeline.

Gated behind MEMORY_ENRICH=on environment variable.
When disabled: returns the original plain summary unchanged.
When enabled: runs a lightweight Groq call to normalize vendor names,
infer missing fields, and produce a richer Telegram summary line.

Falls back to the plain summary on any error — never blocks the main pipeline.
"""
import json
import logging
import os
import re

logger = logging.getLogger('EmailExtractor.Enrichment')

_ENABLED = None  # lazy check


def _is_enabled() -> bool:
    global _ENABLED
    if _ENABLED is None:
        _ENABLED = os.getenv('MEMORY_ENRICH', '').lower() == 'on'
    return _ENABLED


def _call_groq(prompt: str) -> str:
    """Call Groq and return raw text, or '' on failure."""
    try:
        from toolbox.lib.providers.groq import _get_client, GROQ_MODEL
        client = _get_client()
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=150,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f'Groq enrichment call failed: {e}')
        return ''


def _parse_json(raw: str) -> dict:
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ── Per-category enrichment ───────────────────────────────────────────────────

def enrich_receipt(plain_summary: str, vendor: str, amount: str, receipt_type: str) -> str:
    """
    Return enriched Telegram summary for a receipt/payment.

    Plain:    Toyota Financial: $584.99 [Payment]
    Enriched: Receipt — Toyota Financial
              Amount: $584.99 | Type: Auto Loan Payment
    """
    if not _is_enabled():
        return plain_summary

    prompt = f"""\
Given this payment email data, return a JSON object with normalized fields.
Return ONLY valid JSON, no explanation.

{{
  "vendor": "<normalized vendor name, e.g. 'Toyota Financial' not 'TOYOTA FIN'>",
  "category": "<one of: Auto Loan, Insurance, Subscription, Utilities, Dining, Ride Share, Other>",
  "summary_line": "<one concise line, max 60 chars>"
}}

VENDOR: {vendor}
AMOUNT: {amount}
TYPE: {receipt_type}"""

    raw = _call_groq(prompt)
    data = _parse_json(raw)
    if not data:
        return plain_summary

    vendor_out = data.get('vendor', vendor)
    category = data.get('category', receipt_type)
    parts = [f'Receipt — {vendor_out}']
    if amount:
        parts.append(f'Amount: {amount} | Type: {category}')
    return '\n'.join(parts)


def enrich_order(plain_summary: str, vendor: str, order_num: str,
                 n_items: int, total: str, status: str) -> str:
    """
    Return enriched Telegram summary for an order.

    Plain:    Amazon #112-345: 2 items — $49.99 [Confirmed]
    Enriched: Order — Amazon
              #112-345 | 2 items — $49.99 | Status: Confirmed
    """
    if not _is_enabled():
        return plain_summary

    prompt = f"""\
Given this order email data, return a JSON object.
Return ONLY valid JSON, no explanation.

{{
  "vendor": "<normalized vendor name>",
  "summary_line": "<one concise line, max 60 chars>"
}}

VENDOR: {vendor}
ORDER: {order_num or 'unknown'}
ITEMS: {n_items}
TOTAL: {total}
STATUS: {status}"""

    raw = _call_groq(prompt)
    data = _parse_json(raw)
    if not data:
        return plain_summary

    vendor_out = data.get('vendor', vendor)
    parts = [f'Order — {vendor_out}']
    detail_parts = []
    if order_num:
        detail_parts.append(f'#{order_num}')
    if n_items:
        detail_parts.append(f'{n_items} item{"s" if n_items != 1 else ""}')
    if total:
        detail_parts.append(total)
    detail_parts.append(f'Status: {status}')
    if detail_parts:
        parts.append(' | '.join(detail_parts))
    return '\n'.join(parts)


def enrich_trip(plain_summary: str, trip_type: str, vendor: str,
                destination: str, status: str, travel_date: str) -> str:
    """
    Return enriched Telegram summary for a travel booking.

    Plain:    Flight: (Delta) [Confirmed] — departs 2026-05-15
    Enriched: Flight — Delta
              Destination: Atlanta | Status: Confirmed | Departs: 2026-05-15
    """
    if not _is_enabled():
        return plain_summary

    prompt = f"""\
Given this travel booking data, return a JSON object.
Return ONLY valid JSON, no explanation.

{{
  "vendor": "<normalized vendor/airline/hotel name>",
  "destination": "<city or destination, normalized>",
  "summary_line": "<one concise line, max 60 chars>"
}}

TYPE: {trip_type}
VENDOR: {vendor}
DESTINATION: {destination or 'unknown'}
STATUS: {status}
TRAVEL_DATE: {travel_date or 'unknown'}"""

    raw = _call_groq(prompt)
    data = _parse_json(raw)
    if not data:
        return plain_summary

    vendor_out = data.get('vendor', vendor)
    dest_out = data.get('destination', destination)
    parts = [f'{trip_type} — {vendor_out}']
    detail_parts = []
    if dest_out:
        detail_parts.append(f'Destination: {dest_out}')
    detail_parts.append(f'Status: {status}')
    if travel_date:
        detail_parts.append(f'Departs: {travel_date}')
    if detail_parts:
        parts.append(' | '.join(detail_parts))
    return '\n'.join(parts)
