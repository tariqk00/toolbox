"""
Plaud category processor for Email Extractor.
Extracts: action items, decisions, transcript, summary.
Writes to: 01 - Second Brain/Plaud/YYYY-MM-DD - <Subject>.md
Pushes to: Google Tasks via task_utils.
"""
import logging
import re
from datetime import datetime
from ..writers import append_to_memory
from toolbox.lib.task_utils import add_task

logger = logging.getLogger('EmailExtractor.Plaud')

EXTRACT_PROMPT = """\
You are extracting actionables from a voice recording.

Subject: {subject}
Date: {date_str}

Content:
{text}

Return ONLY valid JSON, no other text:
{{
  "action_items": [{{"text": "...", "due_date": "YYYY-MM-DD or null", "context": "..."}}],
  "decisions": ["..."],
  "summary": "...",
  "outline": "..."
}}

Rules:
- action_items: concrete tasks with a clear owner or commitment
- decisions: key conclusions or choices made
- due_date: parse if explicitly mentioned, null otherwise
- context: one sentence explaining the task, or null
- summary: a concise paragraph summarizing the recording
- outline: a structured markdown outline of the key points
- Return empty arrays/nulls if nothing found
"""

def _extract_details_llm(subject: str, date_str: str, text: str) -> dict:
    """Use LLM to extract summary, outline, and actionables."""
    from toolbox.lib.llm import call_json
    prompt = EXTRACT_PROMPT.format(
        subject=subject,
        date_str=date_str,
        text=text[:5000]
    )
    return call_json(prompt, max_tokens=1000)

def _build_markdown(subject: str, date_str: str, details: dict, original_text: str) -> str:
    lines = [f'# {subject}', '']
    lines.append(f'**Date:** {date_str}')
    lines.append(f'**Source:** Plaud Email Ingestion')
    lines.append('')
    lines.append('---')
    lines.append('')

    if details.get('outline'):
        lines.append('## Outline')
        lines.append('')
        lines.append(details['outline'])
        lines.append('')
        lines.append('---')
        lines.append('')

    if details.get('summary'):
        lines.append('## Summary')
        lines.append('')
        lines.append(details['summary'].strip())
        lines.append('')
        lines.append('---')
        lines.append('')

    lines.append('## Transcript')
    lines.append('')
    lines.append(original_text)
    
    return '\n'.join(lines)

def process(email: dict, state: dict) -> str | None:
    subject = email['subject']
    # Strip [Plaud-AutoFlow] prefix
    subject = re.sub(r'^\[Plaud-AutoFlow\]\s*', '', subject)
    
    date_str = email['date']
    plain = email.get('plain') or ''
    
    # 1. Extract details via LLM
    details = _extract_details_llm(subject, date_str, plain)
    
    # 2. Build and save markdown
    # Format: 01 - Second Brain/Plaud/YYYY-MM-DD - Subject.md
    safe_subject = re.sub(r'[^\w\s\-\.]', '', subject).strip()
    filename = f"{date_str} - {safe_subject}.md"
    
    content = _build_markdown(subject, date_str, details, plain)
    append_to_memory('Plaud', filename, content)
    
    # 3. Handle Action Items
    action_items = details.get('action_items', [])
    created_tasks = 0
    for item in action_items:
        if add_task(
            subject=item['text'],
            sender=f"Plaud: {subject}",
            reason=item.get('context') or "Extracted from voice recording",
            priority="medium",
            date_str=item.get('due_date') or date_str,
            sync_to_google_tasks=True
        ):
            created_tasks += 1
            
    summary = f"Plaud: {subject}"
    if created_tasks:
        summary += f" ({created_tasks} tasks created)"
        
    logger.info(f"Processed Plaud email: {subject}")
    return summary
