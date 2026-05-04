"""
Google CC Daily Brief processor.
Extracts: tasks (Action Required) and events (Calendar).
Writes to: Daily Brief/Daily Brief.md.
Pushes tasks to Google Tasks via task_utils.
"""
import logging
import re
import json
from datetime import datetime
from ..writers import append_to_memory
from toolbox.lib.task_utils import add_task

logger = logging.getLogger('EmailExtractor.GoogleBrief')

BRIEF_EXTRACT_PROMPT = """\
You are extracting items from a Daily Brief email.

Return ONLY valid JSON:
{{
  "tasks": [{{"text": "...", "context": "..."}}],
  "events": [{{"title": "...", "time": "HH:MM", "location": "...", "notes": "..."}}]
}}

Email Body:
{body}"""

def _extract_brief_details(body: str) -> dict:
    from toolbox.lib.llm_gateway import call_llm, _parse_json
    res = call_llm(task_type='automation', prompt=BRIEF_EXTRACT_PROMPT.format(body=body[:5000]))
    try:
        return _parse_json(res.get('text', ''))
    except Exception as e:
        logger.warning(f"  [Brief] LLM extraction failed: {e}")
        return {}

def _push_to_tasks(tasks: list) -> int:
    created = 0
    for t in tasks:
        if add_task(
            subject=t['text'],
            sender="Google Daily Brief",
            reason=t.get('context') or "From your daily assistant",
            priority="medium",
            sync_to_google_tasks=True
        ):
            created += 1
    return created

def process(email: dict, state: dict) -> dict | None:
    from datetime import date, timedelta
    msg_id = email['id']
    email_date = email['date']
    subject = email['subject']
    today = date.today()
    
    # Avoid processing the same brief multiple times
    processed = state.setdefault('processed_briefs', [])
    if msg_id in processed:
        return None

    body = email.get('plain') or ''
    details = _extract_brief_details(body)
    
    tasks = details.get('tasks', [])
    events = details.get('events', [])

    if not tasks and not events:
        return None

    tasks_created = 0
    if tasks:
        tasks_created = _push_to_tasks(tasks)

    # Archive log to Drive
    if tasks or events:
        lines = [f'## {email_date} — Daily Brief']
        if tasks:
            lines.append('### Action Required')
            for t in tasks:
                lines.append(f'- {t["text"]}')
        
        if events:
            lines.append('### Schedule')
            for e in events:
                time_str = e.get('time') or "All Day"
                title_str = e.get('title') or "Untitled Event"
                line = f'- **{time_str}** — {title_str}'
                
                location = e.get('location')
                if location:
                    line += f' @ {str(location).strip()}'
                lines.append(line)
                
                notes = e.get('notes')
                if notes:
                    lines.append(f'  *{str(notes).strip()}*')
        lines += ['', '---']
        append_to_memory('Daily Brief', 'Daily Brief.md', '\n'.join(lines))

    processed.append(msg_id)
    # Keep the list manageable
    if len(processed) > 50:
        state['processed_briefs'] = processed[-50:]
        
    summary = f'Google CC: {tasks_created} tasks created, {len(events)} events'
    logger.info(f'Google CC: {tasks_created}/{len(tasks)} tasks created, {len(events)} events from {email_date}')
    
    return {
        'summary': summary,
        'confidence': 1.0,
        'category': 'google_brief'
    }
