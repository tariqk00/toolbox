"""
Google CC daily brief processor.
Extracts tasks (Top of mind) and events (On your calendar) from Google Labs CC emails.
- Creates tasks in Google Tasks ("Daily Brief" list) with due dates
- Writes archive log to Memory/Tasks/Daily Brief.md and Memory/Daily Brief/Daily Brief.md
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

TASKS_LIST_NAME = 'Daily Brief'

EXTRACT_PROMPT = """You are processing a Google CC "Your Day Ahead" daily brief email.
Extract two sections:

1. TASKS — from "Top of mind": action items the user needs to handle.
2. EVENTS — from "On your calendar": scheduled events.

Today's date is {today}.

Return ONLY valid JSON, no other text:
{{
  "tasks": [{{
    "effort": "15 min",
    "text": "...",
    "context": "...",
    "due_date": "YYYY-MM-DD or null"
  }}],
  "events": [{{
    "datetime": "Fri Apr 17 6:00 PM",
    "title": "...",
    "location": "...",
    "notes": "..."
  }}]
}}

Rules:
- effort: time estimate shown (e.g. "5 min", "15 min"), or null if not shown
- context: explanatory blurb below the task, or null
- due_date: parse any date mentioned in the task (e.g. "by Mon, Apr 20" → "{year}-04-20",
  "today" → today's date, "tomorrow" → tomorrow's date). null if no date is mentioned.
- location: null if no location given
- notes: conflict/overlap warnings or other notes, or null

Email:
{{text}}"""


def _call_gemini(text: str, today: str, year: str) -> dict | None:
    from toolbox.lib.gemini import call_gemini
    prompt = EXTRACT_PROMPT.format(today=today, year=year).replace('{text}', text[:6000])
    raw = call_gemini(prompt)
    if not raw:
        return None
    try:
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        logger.error(f'Gemini parse failed: {e}')
        return None


def _push_to_tasks(tasks: list) -> int:
    """Create tasks in Google Tasks. Returns count created."""
    try:
        from toolbox.lib.tasks import get_tasks_service, get_or_create_list, create_task
        service = get_tasks_service()
        list_id = get_or_create_list(service, TASKS_LIST_NAME)
        created = 0
        for t in tasks:
            title = t.get('text', '').strip()
            if not title:
                continue
            effort = t.get('effort')
            if effort:
                title = f'({effort}) {title}'
            notes = t.get('context', '').strip() if t.get('context') else None
            due = t.get('due_date') or None
            create_task(service, list_id, title, due=due, notes=notes)
            created += 1
        return created
    except Exception as e:
        logger.error(f'Google Tasks push failed: {e}')
        return 0


def process(email: dict, state: dict) -> str | None:
    from datetime import date, timedelta
    msg_id = email['id']
    email_date = email['date']
    subject = email['subject']
    today = date.today()

    # Dedup: skip if already processed (guards against same-day reruns)
    processed = state.setdefault('google_brief', {}).setdefault('processed_ids', [])
    if msg_id in processed:
        return None

    html = email.get('html', '')
    plain = email.get('plain', '')
    text, _ = html_to_text(html) if html else (plain, [])

    if not text or len(text) < 100:
        logger.warning(f'Google CC email body too short to process ({email_date})')
        return None

    result = _call_gemini(text, today.isoformat(), str(today.year))
    if not result:
        return None

    tasks = result.get('tasks', [])
    events = result.get('events', [])

    # Push tasks to Google Tasks
    tasks_created = 0
    if tasks:
        tasks_created = _push_to_tasks(tasks)

    # Archive log to Drive
    if tasks:
        lines = [f'## {email_date} — {subject}', '']
        for t in tasks:
            effort = f'({t["effort"]}) ' if t.get('effort') else ''
            due = f' [due: {t["due_date"]}]' if t.get('due_date') else ''
            lines.append(f'- [ ] {effort}{t.get("text", "").strip()}{due}')
            if t.get('context'):
                lines.append(f'  *{t["context"].strip()}*')
        lines += ['', '---']
        append_to_memory('Tasks', 'Daily Brief.md', '\n'.join(lines))

    if events:
        lines = [f'## {email_date} — {subject}', '']
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
    logger.info(f'Google CC: {tasks_created}/{len(tasks)} tasks created, {len(events)} events from {email_date}')
    return f'Google CC: {tasks_created} tasks created, {len(events)} events'
