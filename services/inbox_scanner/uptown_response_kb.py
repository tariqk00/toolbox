"""
Uptown response knowledge-base sync and retrieval helpers.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date

from toolbox.services.email_extractor.scanner import html_to_text, parse_gmail_message
from toolbox.services.email_extractor.writers import list_memory_files, set_memory_content
from toolbox.services.inbox_scanner.categories.uptown_inquiry import LISTING_PLATFORMS

logger = logging.getLogger('InboxScanner.UptownResponseKB')

KB_CATEGORY = 'Properties/Uptown Response KB'
MAILBOX_EMAIL = 'operations@uptownedenton.com'
CC_TARGET = 'takhan@gmail.com'
CHRISTINA_NAME = 'christina manzella'
MAX_PROMPT_EXAMPLES = 3

LEAD_KEYWORDS = {
    'availability', 'available', 'apartment', 'application', 'apply', 'bedroom',
    'call', 'community', 'income', 'lease', 'leasing', 'move in', 'move-in',
    'pet', 'pricing', 'prospect', 'rent', 'rental', 'schedule', 'showing',
    'tour', 'unit',
}
SUBSTANTIVE_HINTS = {
    'application', 'apply', 'call', 'community', 'contact', 'income', 'lease',
    'move in', 'move-in', 'next step', 'pet', 'pricing', 'schedule', 'showing',
    'tour', 'visit', 'welcome',
}
EXCLUDED_TOPIC_HINTS = {
    'invoice', 'maintenance', 'owner', 'vendor', 'statement', 'payment', 'bill',
    'repair', 'insurance', 'hoa', 'utility', 'banquet', 'chamber', 'church',
    'powerpoint', 'slideshow', 'event',
}
SCHEDULING_ONLY_HINTS = {
    'available to talk', 'call you', 'give me a call', 'let us know what time',
    'please call', 'schedule a time', 'what time works', 'when are you available',
}


def _sender_email(from_header: str) -> str:
    m = re.search(r'<([^>]+)>', from_header or '')
    return m.group(1).lower() if m else (from_header or '').lower().strip()


def _sender_name(from_header: str) -> str:
    if '<' in (from_header or ''):
        return (from_header or '').split('<', 1)[0].strip().strip('"')
    return (from_header or '').strip()


def _normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def _clean_body_text(text: str) -> str:
    text = text or ''
    split_patterns = [
        r'(?:^|\n)On .+?wrote:(?:\n|\Z)',
        r'(?:^|\n)From: .+\nSent: .+\n',
        r'(?:^|\n)-{2,}\s*Original Message\s*-{2,}\n',
        r'(?:^|\n)Begin forwarded message:\n',
    ]
    for pattern in split_patterns:
        parts = re.split(pattern, text, maxsplit=1, flags=re.IGNORECASE | re.DOTALL)
        text = parts[0]
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if cleaned and cleaned[-1]:
                cleaned.append('')
            continue
        if stripped.startswith('On '):
            break
        if stripped.startswith('From:') or stripped.startswith('Begin forwarded message:'):
            break
        if 'Original Message' in stripped:
            break
        if stripped.startswith('>'):
            continue
        cleaned.append(stripped)
    return '\n'.join(cleaned).strip()


def _message_body(message: dict) -> str:
    plain = message.get('plain', '') or ''
    html = message.get('html', '') or ''
    if plain and not re.search(r'<[a-zA-Z]+[\s>]', plain[:500]):
        return _clean_body_text(plain)
    if html:
        text, _ = html_to_text(html)
        return _clean_body_text(text)
    return _clean_body_text(plain)


def _subject_base(subject: str) -> str:
    base = (subject or '').strip()
    while True:
        updated = re.sub(r'^(re|fw|fwd):\s*', '', base, flags=re.IGNORECASE)
        if updated == base:
            break
        base = updated.strip()
    return base


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r'[a-z0-9]+', (text or '').lower()) if len(tok) > 2}


def _contains_hint(text: str, hints: set[str]) -> bool:
    lower = (text or '').lower()
    tokens = _tokenize(lower)
    for hint in hints:
        if ' ' in hint:
            if hint in lower:
                return True
            continue
        if hint in tokens:
            return True
        if any(token.startswith(hint) for token in tokens if len(hint) >= 4):
            return True
    return False


def _is_identity_match(message: dict) -> bool:
    sender_email = _sender_email(message.get('from', ''))
    sender_name = _sender_name(message.get('from', '')).lower()
    cc = (message.get('cc', '') or '').lower()
    return (
        sender_email == MAILBOX_EMAIL
        or CHRISTINA_NAME in sender_name
        or CC_TARGET in cc
        or 'SENT' in message.get('label_ids', [])
    )


def _is_lead_message(message: dict) -> bool:
    sender = _sender_email(message.get('from', ''))
    subject = _subject_base(message.get('subject', ''))
    body = _message_body(message)
    combined = f'{subject}\n{body}'
    if sender in LISTING_PLATFORMS:
        return True
    if _contains_hint(combined, EXCLUDED_TOPIC_HINTS):
        return False
    return _contains_hint(combined, LEAD_KEYWORDS)


def _is_substantive_response(text: str) -> bool:
    text = _normalize_whitespace(text)
    if len(text) < 40:
        return False
    lower = text.lower()
    if _contains_hint(lower, SCHEDULING_ONLY_HINTS) and len(lower.split()) < 35:
        return False
    if _contains_hint(lower, SUBSTANTIVE_HINTS):
        return True
    return len(lower.split()) >= 30 and len(re.findall(r'[.!?]', lower)) >= 2


def _source_label(message: dict) -> str:
    sender = _sender_email(message.get('from', ''))
    return LISTING_PLATFORMS.get(sender, 'Direct')


def _lead_name_from_text(text: str) -> str:
    for pattern in (
        r'(?:my name is|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*$',
    ):
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            return m.group(1).strip()
    return ''


def _filename_slug(text: str) -> str:
    slug = re.sub(r'[^A-Za-z0-9]+', '-', text or '').strip('-')
    return slug[:60] or 'inquiry'


def build_kb_entry(thread: dict) -> dict | None:
    raw_messages = thread.get('messages', [])
    if not raw_messages:
        return None

    messages = sorted(
        (parse_gmail_message(m) for m in raw_messages),
        key=lambda m: m.get('date_str', ''),
    )
    outbound = [m for m in messages if _is_identity_match(m)]
    if not outbound:
        return None

    inbound_leads = [m for m in messages if not _is_identity_match(m) and _is_lead_message(m)]
    if not inbound_leads:
        return None

    inquiry = inbound_leads[0]

    responses = []
    for message in outbound:
        body = _message_body(message)
        if not _is_substantive_response(body):
            continue
        responses.append({
            'date': message.get('date', ''),
            'from': message.get('from', ''),
            'body': body,
            'forwarded': _subject_base(message.get('subject', '')) != (message.get('subject', '') or '').strip(),
        })

    if not responses:
        return None

    inquiry_body = _message_body(inquiry)
    if not inquiry_body:
        return None
    lead_name = _lead_name_from_text(inquiry_body) or _sender_name(inquiry.get('from', '')) or 'Unknown Lead'
    subject = _subject_base(inquiry.get('subject', '') or messages[0].get('subject', ''))

    return {
        'date': inquiry.get('date', '') or messages[0].get('date', ''),
        'lead_name': lead_name,
        'source': _source_label(inquiry),
        'subject': subject,
        'thread_id': thread.get('id', '') or messages[0].get('thread_id', ''),
        'inquiry_text': inquiry_body,
        'responses': responses,
        'notes': [],
    }


def kb_filename(entry: dict, existing_filenames: list[str] | None = None) -> str:
    existing_filenames = existing_filenames or []
    thread_id = entry.get('thread_id', '')
    suffix = f'-- {thread_id}.md'
    for filename in existing_filenames:
        if filename.endswith(suffix):
            return filename

    lead = _filename_slug(entry.get('lead_name', 'Unknown Lead'))
    subject = _filename_slug(entry.get('subject', 'inquiry'))
    return f"{entry.get('date', date.today().isoformat())} -- {lead} -- {subject} -- {thread_id}.md"


def render_kb_markdown(entry: dict) -> str:
    lines = ['# Uptown Response KB', '']
    lines.append(f"**Date:** {entry.get('date', '')}")
    lines.append(f"**Lead:** {entry.get('lead_name', '')}")
    lines.append(f"**Source:** {entry.get('source', 'Direct')}")
    lines.append(f"**Subject:** {entry.get('subject', '')}")
    lines.append(f"**Thread ID:** {entry.get('thread_id', '')}")
    lines.append('')
    lines.append('## Original Inquiry')
    lines.append(entry.get('inquiry_text', ''))
    lines.append('')
    lines.append('## Substantive Responses')
    for idx, response in enumerate(entry.get('responses', []), start=1):
        lines.append(f"### Response {idx} — {response.get('date', '')}")
        if response.get('forwarded'):
            lines.append('*Forwarded response*')
        lines.append(response.get('body', ''))
        lines.append('')
    return '\n'.join(lines).strip() + '\n'


def _parse_kb_markdown(content: str) -> dict:
    def _field(name: str) -> str:
        m = re.search(rf'^\*\*{re.escape(name)}:\*\*\s*(.+)$', content, re.MULTILINE)
        return m.group(1).strip() if m else ''

    inquiry_match = re.search(
        r'## Original Inquiry\n(.*?)\n## Substantive Responses\n',
        content,
        re.DOTALL,
    )
    inquiry_text = inquiry_match.group(1).strip() if inquiry_match else ''
    responses = []
    for match in re.finditer(r'### Response \d+ — ([^\n]+)\n(.*?)(?=\n### Response \d+ — |\Z)', content, re.DOTALL):
        body = match.group(2).strip()
        body = re.sub(r'^\*Forwarded response\*\n', '', body)
        responses.append({'date': match.group(1).strip(), 'body': body})
    return {
        'date': _field('Date'),
        'lead_name': _field('Lead'),
        'source': _field('Source') or 'Direct',
        'subject': _field('Subject'),
        'thread_id': _field('Thread ID'),
        'inquiry_text': inquiry_text,
        'responses': responses,
    }


def _candidate_thread_ids(service, after_date: str | None) -> list[str]:
    if after_date:
        query = f'in:sent after:{after_date}'
    else:
        query = 'in:sent newer_than:30d'
    thread_ids: list[str] = []
    seen: set[str] = set()
    page_token = None
    while True:
        params = {'userId': 'me', 'q': query}
        if page_token:
            params['pageToken'] = page_token
        result = service.users().messages().list(**params).execute()
        for message in result.get('messages', []):
            thread_id = message.get('threadId')
            if thread_id and thread_id not in seen:
                seen.add(thread_id)
                thread_ids.append(thread_id)
        page_token = result.get('nextPageToken')
        if not page_token:
            break
    return thread_ids


def sync_response_kb(service, state: dict) -> int:
    after_date = state.get('uptown_response_kb_last_run')
    existing = list_memory_files(KB_CATEGORY)
    synced = 0
    synced_entries: list[dict] = []
    for thread_id in _candidate_thread_ids(service, after_date):
        try:
            thread = service.users().threads().get(userId='me', id=thread_id).execute()
            entry = build_kb_entry(thread)
            if not entry:
                continue
            filename = kb_filename(entry, list(existing.keys()))
            set_memory_content(KB_CATEGORY, filename, render_kb_markdown(entry))
            existing[filename] = existing.get(filename, '')
            entry['_kb_filename'] = filename
            synced_entries.append(entry)
            synced += 1
        except Exception as e:
            logger.warning(f'Uptown response KB sync failed for thread {thread_id}: {e}')
    state['uptown_response_kb_last_run'] = date.today().strftime('%Y/%m/%d')
    state['uptown_response_kb_synced_entries'] = synced_entries
    return synced


def load_kb_entries() -> list[dict]:
    from toolbox.services.email_extractor.writers import get_memory_content

    entries = []
    for filename in sorted(list_memory_files(KB_CATEGORY)):
        try:
            content = get_memory_content(KB_CATEGORY, filename)
            if content:
                entries.append(_parse_kb_markdown(content))
        except Exception as e:
            logger.warning(f'Failed to load KB file {filename}: {e}')
    return entries


def _score_entry(entry: dict, inquiry: dict) -> int:
    score = 0
    inquiry_tokens = _tokenize(' '.join([
        inquiry.get('subject', ''),
        inquiry.get('unit_interest', ''),
        ' '.join(inquiry.get('questions', []) or []),
        inquiry.get('body', ''),
    ]))
    entry_tokens = _tokenize(' '.join([
        entry.get('subject', ''),
        entry.get('inquiry_text', ''),
        ' '.join(r.get('body', '') for r in entry.get('responses', [])),
    ]))
    overlap = inquiry_tokens & entry_tokens
    score += len(overlap) * 2
    if entry.get('source') == inquiry.get('platform'):
        score += 5
    if inquiry.get('platform') == 'Direct' and entry.get('source') == 'Direct':
        score += 2
    topic_counts = Counter(tok for tok in overlap if tok in {'tour', 'call', 'pricing', 'application', 'pet', 'move', 'bedroom'})
    score += sum(topic_counts.values()) * 3
    return score


def build_prompt_examples(inquiry: dict, limit: int = MAX_PROMPT_EXAMPLES) -> str:
    entries = load_kb_entries()
    ranked = sorted(
        (
            (entry, _score_entry(entry, inquiry))
            for entry in entries
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    chosen = [entry for entry, score in ranked if score > 0][:limit]
    if not chosen:
        return ''

    sections = []
    for idx, entry in enumerate(chosen, start=1):
        response_preview = '\n\n'.join(r.get('body', '') for r in entry.get('responses', [])[:2])
        sections.append(
            f"Example {idx} — {entry.get('source', 'Direct')} lead\n"
            f"Inquiry: {entry.get('inquiry_text', '')[:500]}\n"
            f"Response style:\n{response_preview[:900]}"
        )
    return '\n\n'.join(sections)
