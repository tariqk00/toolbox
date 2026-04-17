"""
Google CC daily brief processor.
Extracts tasks (Top of mind) and events (On your calendar) from Google Labs CC emails.
Writes tasks to Memory/Tasks/Daily Brief.md and events to Memory/Daily Brief/Daily Brief.md.
"""
import json
import logging
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from ..scanner import html_to_text
from ..writers import append_to_memory

logger = logging.getLogger('EmailExtractor.GoogleBrief')

EXTRACT_PROMPT = """You are processing a Google CC "Your Day Ahead" daily brief email.
Extract two sections:

1. TASKS — from "Top of mind": action items the user needs to handle.
2. EVENTS — from "On your calendar": scheduled events.

Return ONLY valid JSON, no other text:
{{
  "tasks": [{{"effort": "15 min", "text": "...", "context": "..."}}],
  "events": [{{"datetime": "Fri Apr 17 6:00 PM", "title": "...", "location": "...", "notes": "..."}}]
}}

Rules:
- effort: time estimate shown (e.g. "5 min", "15 min"), or null if not shown
- context: explanatory blurb below the task, or null
- location: null if no location given
- notes: conflict/overlap warnings or other notes, or null

Email:
{text}"""


def _call_gemini(text: str) -> dict | None:
    from toolbox.lib.gemini import call_gemini
    raw = call_gemini(EXTRACT_PROMPT.format(text=text[:6000]))
    if not raw:
        return None
    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        logger.error(f'Gemini parse failed: {e}')
        return None


def process(email: dict, state: dict) -> str | None:
    msg_id = email['id']
    date = email['date']
    subject = email['subject']

    # Dedup: skip if already processed (guards against same-day reruns)
    processed = state.setdefault('google_brief', {}).setdefault('processed_ids', [])
    if msg_id in processed:
        return None

    html = email.get('html', '')
    plain = email.get('plain', '')
    text, _ = html_to_text(html) if html else (plain, [])

    if not text or len(text) < 100:
        logger.warning(f'Google CC email body too short to process ({date})')
        return None

    result = _call_gemini(text)
    if not result:
        return None

    tasks = result.get('tasks', [])
    events = result.get('events', [])

    if tasks:
        lines = [f'## {date} — {subject}', '']
        for t in tasks:
            effort = f'({t["effort"]}) ' if t.get('effort') else ''
            lines.append(f'- [ ] {effort}{t.get("text", "").strip()}')
            if t.get('context'):
                lines.append(f'  *{t["context"].strip()}*')
        lines += ['', '---']
        append_to_memory('Tasks', 'Daily Brief.md', '\n'.join(lines))

    if events:
        lines = [f'## {date} — {subject}', '']
        for e in events:
            line = f'- {e.get("datetime", "").strip()} — {e.get("title", "").strip()}'
            if e.get('location'):
                line += f' @ {e["location"].strip()}'
            lines.append(line)
            if e.get('notes'):
                lines.append(f'  *{e["notes"].strip()}*')
        lines += ['', '---']
        append_to_memory('Daily Brief', 'Daily Brief.md', '\n'.join(lines))

    processed.append(msg_id)
    logger.info(f'Google CC: {len(tasks)} tasks, {len(events)} events from {date}')
    return f'Google CC: {len(tasks)} tasks, {len(events)} events'
