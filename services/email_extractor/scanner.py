"""
Gmail scanner for the email extraction pipeline.
Handles auth, per-category queries, full message fetch, and last_run state.
"""
import base64
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLAUD_DIR = os.path.join(os.path.dirname(BASE_DIR), 'plaud')
STATE_PATH = os.path.join(BASE_DIR, 'config', 'email_extractor_state.json')
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'email_extractor_config.json')

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from toolbox.lib.google_api import GoogleAuth

logger = logging.getLogger('EmailExtractor.Scanner')

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def get_gmail_service():
    auth = GoogleAuth(base_dir=PLAUD_DIR)
    creds = auth.get_credentials(
        token_filename='token.json',
        credentials_filename='config/credentials.json',
        scopes=GMAIL_SCOPES
    )
    from googleapiclient.discovery import build
    return build('gmail', 'v1', credentials=creds)


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def _build_sender_query(senders: dict, sender_domains: dict = None) -> str:
    """Build a Gmail from: query for a set of senders and optional domains."""
    parts = list(senders.keys())
    if sender_domains:
        parts += [f'@{d}' for d in sender_domains.keys()]
    escaped = ' OR '.join(f'from:{s}' for s in parts)
    return f'({escaped})'


def _fetch_messages(service, query: str, after_date: str = None,
                    first_run: bool = False, include_spam_trash: bool = False) -> list:
    """Fetch all messages matching query + date constraint, with pagination."""
    if after_date:
        full_query = f'{query} after:{after_date}'
    else:
        full_query = query

    if first_run:
        today = date.today().strftime('%Y/%m/%d')
        full_query = f'({query} in:inbox) OR ({query} after:{today})'

    logger.debug(f'Gmail query: {full_query}')
    messages = []
    page_token = None
    while True:
        params = {'userId': 'me', 'q': full_query, 'includeSpamTrash': include_spam_trash}
        if page_token:
            params['pageToken'] = page_token
        result = service.users().messages().list(**params).execute()
        messages.extend(result.get('messages', []))
        page_token = result.get('nextPageToken')
        if not page_token:
            break
    return messages


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML tags, preserve links as [url], add newlines at block elements."""
    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = False
        self._links = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head'):
            self._skip = True
        if tag == 'a':
            for name, val in attrs:
                if name == 'href' and val and val.startswith('http'):
                    self._links.append(val)
        if tag in ('p', 'br', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'tr'):
            self._parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        import re
        text = ''.join(self._parts)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def get_links(self) -> list:
        return self._links


def html_to_text(html: str):
    """Returns (plain_text, links_list)."""
    p = _HTMLTextExtractor()
    try:
        p.feed(html)
    except Exception:
        pass
    return p.get_text(), p.get_links()


def _extract_body(payload: dict):
    """Recursively extract plain text and HTML from a message payload."""
    plain = ''
    html = ''

    def _decode(data):
        if not data:
            return ''
        try:
            return base64.urlsafe_b64decode(data + '==').decode('utf-8', errors='replace')
        except Exception:
            return ''

    mime = payload.get('mimeType', '')
    parts = payload.get('parts', [])

    if not parts:
        data = payload.get('body', {}).get('data', '')
        if 'html' in mime:
            html = _decode(data)
        else:
            plain = _decode(data)
        return plain, html

    for part in parts:
        p_mime = part.get('mimeType', '')
        if p_mime == 'text/plain':
            plain += _decode(part.get('body', {}).get('data', ''))
        elif p_mime == 'text/html':
            html += _decode(part.get('body', {}).get('data', ''))
        elif part.get('parts'):
            sub_plain, sub_html = _extract_body(part)
            plain += sub_plain
            html += sub_html

    return plain, html


def get_full_email(service, message_id: str) -> dict:
    """Fetch and parse a full email message."""
    msg = service.users().messages().get(userId='me', id=message_id).execute()
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    plain, html = _extract_body(msg['payload'])

    date_str = headers.get('Date', '')
    try:
        date_dt = parsedate_to_datetime(date_str)
    except Exception:
        date_dt = datetime.now(timezone.utc)

    return {
        'id': message_id,
        'subject': headers.get('Subject', ''),
        'from': headers.get('From', ''),
        'date_str': date_str,
        'date_dt': date_dt,
        'date': date_dt.strftime('%Y-%m-%d'),
        'plain': plain,
        'html': html,
        'label_ids': msg.get('labelIds', []),
    }


def _sender_email(from_header: str) -> str:
    """Extract bare email from 'Name <email>' or plain email."""
    import re
    m = re.search(r'<([^>]+)>', from_header)
    return m.group(1).lower() if m else from_header.lower().strip()


def _match_sender(from_header: str, senders: dict, sender_domains: dict = None) -> str | None:
    """Return vendor name if sender matches, else None."""
    email = _sender_email(from_header)
    if email in {k.lower() for k in senders}:
        for k, v in senders.items():
            if k.lower() == email:
                return v
    if sender_domains:
        for domain, vendor in sender_domains.items():
            if email.endswith('@' + domain.lower()):
                return vendor
    return None


def fetch_category_emails(service, category: str, config: dict,
                          after_date: str = None, first_run: bool = False) -> list:
    """
    Fetch and parse emails for a given category.
    Returns list of dicts: email metadata + body + matched vendor name.
    """
    cat_config = config.get(category, {})
    senders = cat_config.get('senders', {})
    sender_domains = cat_config.get('sender_domains', {})

    if not senders and not sender_domains:
        return []

    sender_query = _build_sender_query(senders, sender_domains)
    raw = _fetch_messages(
        service, sender_query,
        after_date=after_date,
        first_run=first_run,
        include_spam_trash=first_run,
    )

    results = []
    seen_ids = set()
    for m in raw:
        if m['id'] in seen_ids:
            continue
        seen_ids.add(m['id'])
        try:
            full = get_full_email(service, m['id'])
            vendor = _match_sender(full['from'], senders, sender_domains)
            if vendor:
                full['vendor'] = vendor
                results.append(full)
        except Exception as e:
            logger.warning(f'Failed to fetch message {m["id"]}: {e}')

    return results
