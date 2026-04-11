"""
Digests category processor.
Uses Gemini free tier to extract title + link + summary per article.
Unknown senders trigger a Telegram ask before processing.
"""
import json
import logging
import os
import sys
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from toolbox.lib.telegram import send_message, escape
from ..scanner import html_to_text, load_state, save_state
from ..writers import append_to_memory

logger = logging.getLogger('EmailExtractor.Digests')


EXTRACT_PROMPT = """You are processing a newsletter/digest email. Extract every article, paper, or item mentioned.
For each item return:
- title: the article or item title
- link: the URL if present, otherwise null
- summary: 1-2 sentence description of what it covers

Return ONLY a valid JSON array, no other text:
[{{"title": "...", "link": "...", "summary": "..."}}, ...]

Email content:
{text}"""


def _call_gemini(text: str) -> list[dict]:
    from toolbox.lib.gemini import call_gemini
    raw = call_gemini(EXTRACT_PROMPT.format(text=text[:8000]))
    if not raw:
        return []
    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        logger.error(f'Gemini extraction failed: {e}')
        return []


def _is_known_sender(from_header: str, known_senders: dict) -> str | None:
    """Return source name if known, else None."""
    email = from_header.lower()
    m = re.search(r'<([^>]+)>', email)
    bare = m.group(1) if m else email.strip()
    for sender, name in known_senders.items():
        if sender.lower() == bare:
            return name
    return None


def process(email: dict, known_senders: dict, raw_senders: dict = None) -> bool:
    raw_senders = raw_senders or {}
    from_header = email['from']
    subject = email['subject']
    date = email['date']
    html = email.get('html', '')
    plain = email.get('plain', '')

    source_name = _is_known_sender(from_header, raw_senders)
    if source_name:
        # Raw senders: store body verbatim, no LLM extraction
        text, _ = html_to_text(html) if html else (plain, [])
        # Light cleanup: collapse whitespace, drop blank lines
        lines_clean = [l.strip() for l in text.splitlines() if l.strip()]
        body = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines_clean)).strip()
        content = f'## {date} — {subject}\n\n{body}\n\n---'
        filename = f'{source_name}.md'
        append_to_memory('Digests', filename, content)
        logger.info(f'Digests/{filename}: stored verbatim from {date}')
        return f'{source_name}: daily brief'

    source_name = _is_known_sender(from_header, known_senders)

    if not source_name:
        # Unknown sender — ask via Telegram and skip for now
        state = load_state()
        pending = state.get('pending_digest_senders', [])
        sender_email = re.search(r'<([^>]+)>', from_header)
        sender_email = sender_email.group(1) if sender_email else from_header

        if sender_email not in pending:
            pending.append(sender_email)
            state['pending_digest_senders'] = pending
            save_state(state)
            send_message(
                f'<b>New digest sender found:</b> <code>{escape(sender_email)}</code>\n'
                f'From: {escape(from_header)}\n'
                f'Subject: {escape(subject)}\n\n'
                f'Reply with the source name to add it to the pipeline, or ignore to skip.',
                service='email-extractor'
            )
            logger.info(f'Unknown digest sender, flagged: {from_header}')
        return False

    # Extract text from HTML (preferred) or plain
    if html:
        text, _ = html_to_text(html)
    else:
        text = plain

    articles = _call_gemini(text)
    if not articles:
        logger.warning(f'No articles extracted from {source_name} ({subject})')
        return False

    lines = [f'## {date} — {subject}', '']
    for art in articles:
        title = art.get('title', '').strip()
        link = art.get('link', '')
        summary = art.get('summary', '').strip()
        if not title:
            continue
        if link:
            lines.append(f'### [{title}]({link})')
        else:
            lines.append(f'### {title}')
        if summary:
            lines.append(f'*{summary}*')
        lines.append('')
    lines.append('---')

    content = '\n'.join(lines)
    filename = f'{source_name}.md'
    append_to_memory('Digests', filename, content)
    summary_lines = [f'{source_name}: {len(articles)} articles']
    for art in articles[:3]:
        title = art.get('title', '').strip()
        link = art.get('link', '').strip()
        if not title:
            continue
        line = f'  → {title}'
        if link:
            line += f'\n    {link}'
        summary_lines.append(line)
    summary = '\n'.join(summary_lines)
    logger.info(f'Digests/{filename}: {len(articles)} articles from {date}')
    return summary
