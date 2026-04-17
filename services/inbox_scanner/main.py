"""
General inbox scanner — scans inbox since last run, classifies unhandled emails,
alerts on action items and inquiries.

Usage: python -m toolbox.services.inbox_scanner.main [mailbox_id]
Default mailbox_id: primary
"""
import json
import logging
import os
import re
import sys
import time
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
logger = logging.getLogger('InboxScanner')

from toolbox.lib.google_api import GoogleAuth
from toolbox.services.email_extractor.scanner import get_full_email, html_to_text
from toolbox.services.inbox_scanner.classifier import classify_email
from toolbox.services.inbox_scanner.categories.action_required import ActionRequiredProcessor
from toolbox.services.inbox_scanner.categories.inquiry import InquiryProcessor
from toolbox.services.inbox_scanner import actions

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CONFIG_DIR = os.path.join(BASE_DIR, 'config', 'inbox_scanner')
EXTRACTOR_CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'email_extractor_config.json')

# Rate limit between Gemini calls (free tier: ~10 req/min)
GEMINI_DELAY_SECONDS = 7

PROCESSORS = {
    'action_required': ActionRequiredProcessor(),
    'inquiry': InquiryProcessor(),
}


def load_mailbox_config(mailbox_id: str) -> dict:
    path = os.path.join(CONFIG_DIR, mailbox_id, 'config.json')
    with open(path) as f:
        config = json.load(f)
    # Expand ~ in paths
    for key in ('token_base_dir', 'credentials_path'):
        if key in config:
            config[key] = os.path.expanduser(config[key])
    return config


def load_state(mailbox_id: str) -> dict:
    path = os.path.join(CONFIG_DIR, mailbox_id, 'state.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(mailbox_id: str, state: dict) -> None:
    path = os.path.join(CONFIG_DIR, mailbox_id, 'state.json')
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def get_gmail_service(config: dict):
    auth = GoogleAuth(base_dir=config['token_base_dir'])
    creds = auth.get_credentials(
        token_filename='token.json',
        credentials_filename=config.get('credentials_path', os.path.join(BASE_DIR, 'config', 'credentials.json')),
        scopes=GMAIL_SCOPES,
    )
    from googleapiclient.discovery import build
    return build('gmail', 'v1', credentials=creds)


def collect_known_senders(extractor_config: dict) -> set:
    """Build set of sender emails/domains already handled by email_extractor."""
    known = set()
    for cat in ('orders', 'receipts', 'trips', 'google_brief'):
        for s in extractor_config.get(cat, {}).get('senders', {}):
            known.add(s.lower())
        for domain in extractor_config.get(cat, {}).get('sender_domains', {}):
            known.add('@' + domain.lower())
    for s in extractor_config.get('digests', {}).get('known_senders', {}):
        known.add(s.lower())
    for s in extractor_config.get('digests', {}).get('raw_senders', {}):
        known.add(s.lower())
    return known


def _sender_email(from_header: str) -> str:
    m = re.search(r'<([^>]+)>', from_header)
    return m.group(1).lower() if m else from_header.lower().strip()


def _is_known_sender(email: str, known: set) -> bool:
    if email in known:
        return True
    domain = email.split('@')[-1] if '@' in email else ''
    return bool(domain and ('@' + domain) in known)


def fetch_inbox_since(service, after_date: str | None) -> list:
    """Fetch all inbox message IDs since after_date (YYYY/MM/DD), or full inbox if None."""
    if after_date:
        query = f'in:inbox after:{after_date}'
    else:
        query = 'in:inbox'

    messages = []
    page_token = None
    while True:
        params = {'userId': 'me', 'q': query}
        if page_token:
            params['pageToken'] = page_token
        result = service.users().messages().list(**params).execute()
        messages.extend(result.get('messages', []))
        page_token = result.get('nextPageToken')
        if not page_token:
            break
    return messages


def run(mailbox_id: str = 'primary') -> None:
    config = load_mailbox_config(mailbox_id)
    state = load_state(mailbox_id)
    telegram_service = config.get('telegram_service', 'inbox-scanner')
    mailbox_email = config.get('email', mailbox_id)

    today = date.today().isoformat()
    last_run = state.get('last_run')

    # Per-day dedup: reset processed_ids when date changes (cache persists across days)
    if state.get('state_date') != today:
        state['processed_ids'] = []
        state['state_date'] = today
    processed_ids = set(state.get('processed_ids', []))
    classification_cache: dict = state.get('classification_cache', {})

    logger.info(f'=== Inbox Scanner [{mailbox_id}] {"(first run)" if not last_run else f"(since {last_run})"} ===')

    service = get_gmail_service(config)

    try:
        with open(EXTRACTOR_CONFIG_PATH) as f:
            extractor_config = json.load(f)
    except Exception:
        extractor_config = {}
    known_senders = collect_known_senders(extractor_config)

    after_date = last_run.replace('-', '/') if last_run else None
    raw_messages = fetch_inbox_since(service, after_date)
    logger.info(f'Found {len(raw_messages)} inbox messages to evaluate')

    results: dict[str, list] = {cat: [] for cat in PROCESSORS}
    errors = 0
    skipped_known = 0
    skipped_seen = 0
    classified = 0

    for m in raw_messages:
        msg_id = m['id']

        if msg_id in processed_ids:
            skipped_seen += 1
            continue

        # Fetch metadata: sender, subject, and Gmail category labels
        try:
            meta = service.users().messages().get(
                userId='me', id=msg_id,
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date'],
            ).execute()
            headers = {h['name']: h['value'] for h in meta['payload']['headers']}
            from_h = headers.get('From', '')
            subject = headers.get('Subject', '')
            sender = _sender_email(from_h)
            label_ids = meta.get('labelIds', [])
        except Exception as e:
            logger.warning(f'Metadata fetch failed {msg_id}: {e}')
            continue

        if _is_known_sender(sender, known_senders):
            processed_ids.add(msg_id)
            skipped_known += 1
            continue

        # Gmail auto-label pre-filter: promotions and social are never actionable
        auto_skip_labels = {'CATEGORY_PROMOTIONS', 'CATEGORY_SOCIAL'}
        if auto_skip_labels.intersection(label_ids):
            processed_ids.add(msg_id)
            skipped_known += 1
            logger.debug(f'  [skip/label] {sender} — {subject[:60]}')
            continue

        # Cache hit: reconstruct result from stored data, no full email fetch needed
        if msg_id in classification_cache:
            cached = classification_cache[msg_id]
            category = cached.get('category', 'skip')
            logger.info(f'  [{category}] {sender} — {subject[:60]} (cached)')
            classified += 1
            processed_ids.add(msg_id)
            if category in PROCESSORS:
                fake_email = {
                    'from': cached.get('_from_header', from_h),
                    'subject': cached.get('_subject', subject),
                    'date': cached.get('_date', ''),
                }
                result = PROCESSORS[category].process(fake_email, cached)
                if result:
                    results[category].append(result)
                    if category == 'action_required' and cached.get('priority') == 'high':
                        actions.send_immediate_alert(result, telegram_service)
            continue

        # Cache miss: fetch full email, classify, store
        try:
            # Rate-limit Gemini calls
            if classified > 0:
                time.sleep(GEMINI_DELAY_SECONDS)

            full = get_full_email(service, msg_id)
            html = full.get('html', '')
            plain = full.get('plain', '')
            body, _ = html_to_text(html) if html else (plain, [])
            body_clean = '\n'.join(line.strip() for line in body.splitlines() if line.strip())

            classification = classify_email(sender, full['subject'], body_clean)
            classification['_sender'] = sender
            classification['_from_header'] = from_h
            classification['_subject'] = full['subject']
            classification['_date'] = full['date']
            classification_cache[msg_id] = classification
            category = classification.get('category', 'skip')
            classified += 1
            logger.info(f'  [{category}] {sender} — {full["subject"][:60]} ({classification.get("reason","")[:60]})')

            processed_ids.add(msg_id)

            if category in PROCESSORS:
                result = PROCESSORS[category].process(full, classification)
                if result:
                    results[category].append(result)
                    if category == 'action_required' and classification.get('priority') == 'high':
                        actions.send_immediate_alert(result, telegram_service)
        except Exception as e:
            logger.error(f'Processing failed {msg_id}: {e}')
            errors += 1
            processed_ids.add(msg_id)

    logger.info(
        f'Done: {classified} classified, {skipped_known} skipped (known), '
        f'{skipped_seen} skipped (already seen), {errors} errors'
    )

    # Write Drive logs
    if results.get('action_required'):
        try:
            actions.write_action_required(results['action_required'])
        except Exception as e:
            logger.error(f'Drive write failed (action_required): {e}')
            errors += 1

    if results.get('inquiry'):
        try:
            actions.write_inquiries(results['inquiry'])
        except Exception as e:
            logger.error(f'Drive write failed (inquiry): {e}')
            errors += 1

    # Update state
    state['last_run'] = today
    state['state_date'] = today
    state['processed_ids'] = list(processed_ids)
    state['classification_cache'] = classification_cache
    save_state(mailbox_id, state)

    # Telegram summary
    actions.send_run_summary(results, errors, mailbox_email, telegram_service)


if __name__ == '__main__':
    mailbox = sys.argv[1] if len(sys.argv) > 1 else 'primary'
    run(mailbox)
