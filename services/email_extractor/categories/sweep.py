"""
Weekly email sweep — discovers new senders not covered by existing categories.
Fetches past 7 days of mail (metadata only), filters known senders, classifies
the top unknowns with Gemini, and writes a report to Drive/Digests/Email Sweep.md.
"""
import json
import logging
import os
import re
import sys
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from ..scanner import html_to_text, get_full_email, save_state

logger = logging.getLogger('EmailExtractor.Sweep')

GEMINI_FREE_SECRET = os.path.join(BASE_DIR, 'config', 'gemini_ai_studio_secret')
GEMINI_FREE_MODEL = os.getenv('GEMINI_FREE_MODEL', 'gemini-2.5-flash-lite')
SWEEP_INTERVAL_DAYS = 7
TOP_SENDERS_TO_CLASSIFY = 15
PERSONAL_DOMAINS = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'me.com'}

CLASSIFY_PROMPT = """Classify this email to determine if it should be auto-processed by a personal finance/life pipeline.

Sender: {sender}
Subject: {subject}
Body excerpt:
{body}

Categories:
- order: order confirmation, shipping notification, delivery update
- receipt: bill, payment confirmation, invoice, bank/card statement, subscription charge
- trip: flight, hotel, car rental, restaurant/event reservation
- digest: newsletter, daily summary, curated article/content list
- skip: marketing, promotional, social notification, spam-like, not worth tracking

Return ONLY valid JSON: {{"category": "...", "reason": "one sentence", "vendor": "short vendor name"}}"""


def _get_gemini_client():
    try:
        from google import genai
        key = open(GEMINI_FREE_SECRET).read().strip()
        return genai.Client(api_key=key)
    except Exception as e:
        logger.error(f'Gemini client init failed: {e}')
        return None


def _classify_email(sender: str, subject: str, body: str) -> dict:
    client = _get_gemini_client()
    if not client:
        return {'category': 'unknown', 'reason': 'Gemini unavailable', 'vendor': sender}
    try:
        prompt = CLASSIFY_PROMPT.format(sender=sender, subject=subject, body=body[:1500])
        resp = client.models.generate_content(model=GEMINI_FREE_MODEL, contents=prompt)
        raw = resp.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        logger.warning(f'Classify failed for {sender}: {e}')
        return {'category': 'unknown', 'reason': str(e)[:80], 'vendor': sender}


def _collect_known_senders(config: dict) -> set:
    known = set()
    for cat in ('orders', 'receipts', 'trips'):
        for s in config.get(cat, {}).get('senders', {}):
            known.add(s.lower())
        for domain in config.get(cat, {}).get('sender_domains', {}):
            known.add('@' + domain.lower())
    for s in config.get('digests', {}).get('known_senders', {}):
        known.add(s.lower())
    for s in config.get('digests', {}).get('raw_senders', {}):
        known.add(s.lower())
    return known


def _sender_email(from_header: str) -> str:
    m = re.search(r'<([^>]+)>', from_header)
    return m.group(1).lower() if m else from_header.lower().strip()


def _is_known(email: str, known: set) -> bool:
    if email in known:
        return True
    domain = email.split('@')[-1] if '@' in email else ''
    return bool(domain and ('@' + domain) in known)


def run(service, config: dict, state: dict) -> str | None:
    today = date.today()
    last_sweep = state.get('last_sweep_run')

    if last_sweep:
        days_since = (today - date.fromisoformat(last_sweep)).days
        if days_since < SWEEP_INTERVAL_DAYS:
            return None

    week_ago = (today - timedelta(days=SWEEP_INTERVAL_DAYS)).strftime('%Y/%m/%d')
    known_senders = _collect_known_senders(config)

    logger.info(f'Sweep: scanning emails since {week_ago}...')

    # Fetch all message IDs from the past week (metadata only — fast)
    query = f'after:{week_ago} -in:spam -in:trash'
    message_ids = []
    page_token = None
    while True:
        params = {'userId': 'me', 'q': query}
        if page_token:
            params['pageToken'] = page_token
        result = service.users().messages().list(**params).execute()
        message_ids.extend(result.get('messages', []))
        page_token = result.get('nextPageToken')
        if not page_token or len(message_ids) >= 500:
            break

    logger.info(f'Sweep: {len(message_ids)} messages found, fetching headers...')

    # Fetch headers only for each message
    unknown_by_sender: dict[str, dict] = {}
    for m in message_ids:
        try:
            meta = service.users().messages().get(
                userId='me', id=m['id'],
                format='metadata',
                metadataHeaders=['From', 'Subject'],
            ).execute()
            headers = {h['name']: h['value'] for h in meta['payload']['headers']}
            from_h = headers.get('From', '')
            subject = headers.get('Subject', '')
            sender = _sender_email(from_h)

            if _is_known(sender, known_senders):
                continue

            # Skip personal domains (replies, personal email)
            domain = sender.split('@')[-1] if '@' in sender else ''
            if domain in PERSONAL_DOMAINS:
                continue

            if sender not in unknown_by_sender:
                unknown_by_sender[sender] = {
                    'from_header': from_h,
                    'subjects': [],
                    'sample_id': m['id'],
                    'count': 0,
                }
            unknown_by_sender[sender]['subjects'].append(subject)
            unknown_by_sender[sender]['count'] += 1
        except Exception as e:
            logger.warning(f'Metadata fetch failed {m["id"]}: {e}')

    logger.info(f'Sweep: {len(unknown_by_sender)} unknown senders after filtering')

    state['last_sweep_run'] = today.isoformat()
    save_state(state)

    if not unknown_by_sender:
        return 'Sweep: no new senders found'

    # Sort by frequency, classify top N
    top_senders = sorted(unknown_by_sender.items(), key=lambda x: -x[1]['count'])[:TOP_SENDERS_TO_CLASSIFY]

    classified = []
    for i, (sender, info) in enumerate(top_senders):
        if i > 0:
            import time
            time.sleep(7)  # stay under 10 req/min free tier limit
        try:
            full = get_full_email(service, info['sample_id'])
            html = full.get('html', '')
            plain = full.get('plain', '')
            body, _ = html_to_text(html) if html else (plain, [])
            # Light cleanup for LLM
            body_lines = [l.strip() for l in body.splitlines() if l.strip()]
            body_clean = '\n'.join(body_lines)
            result = _classify_email(sender, info['subjects'][0], body_clean)
        except Exception as e:
            logger.warning(f'Full fetch/classify failed for {sender}: {e}')
            result = {'category': 'unknown', 'reason': str(e)[:80], 'vendor': sender}

        if result.get('category') == 'skip':
            continue

        classified.append({
            'sender': sender,
            'from_header': info['from_header'],
            'count': info['count'],
            'subjects': info['subjects'][:3],
            'category': result.get('category', 'unknown'),
            'vendor': result.get('vendor', sender),
            'reason': result.get('reason', ''),
        })

    # Write Drive report
    from ..writers import append_to_memory
    lines = [f'## Sweep {today.isoformat()} — {len(classified)} new senders\n']
    for item in classified:
        lines.append(f'### {item["vendor"]} (`{item["sender"]}`)')
        lines.append(f'**Category:** {item["category"]}  ')
        lines.append(f'**Volume:** {item["count"]} emails/week  ')
        lines.append(f'**Reason:** {item["reason"]}  ')
        lines.append(f'**Sample subjects:** ' + '; '.join(f'"{s}"' for s in item["subjects"]))
        lines.append('')
    lines.append('---')
    append_to_memory('Digests', 'Email Sweep.md', '\n'.join(lines))
    logger.info(f'Sweep report written: {len(classified)} senders classified')

    # Telegram summary
    by_cat: dict[str, list] = {}
    for item in classified:
        by_cat.setdefault(item['category'], []).append(item['vendor'])

    parts = [f'Sweep: {len(classified)} new senders']
    for cat in ('order', 'receipt', 'trip', 'digest', 'unknown'):
        if cat in by_cat:
            vendors = by_cat[cat]
            parts.append(f'  {cat}: {", ".join(vendors[:4])}{"…" if len(vendors) > 4 else ""}')
    return '\n'.join(parts)
