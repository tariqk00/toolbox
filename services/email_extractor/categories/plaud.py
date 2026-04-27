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
from ..scanner import get_attachment
from toolbox.lib.task_utils import add_task

logger = logging.getLogger('EmailExtractor.Plaud')

EXTRACT_PROMPT = """\
You are extracting actionables from a voice recording.

Subject: {subject}
Date: {date_str}

Content (Transcript/Summary):
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


def _parse_date_and_subject(date_str, raw_subject):
    """Robust date and subject parsing from Plaud emails."""
    # Base date from email date header
    try:
        # Expected: 2026-04-26 (from scanner's email['date'])
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        dt = datetime.now()
        
    year = dt.strftime("%Y")
    doc_date = dt.strftime("%Y-%m-%d")
    
    # Check for explicit date in subject like 02-13 or 02/13
    match = re.search(r'\b(\d{2})[-/](\d{2})\b', raw_subject)
    if match:
        doc_date = f"{year}-{match.group(1)}-{match.group(2)}"
        
    # Clean subject
    safe_subject = re.sub(r'^(Fwd:\s*|Re:\s*)+', '', raw_subject, flags=re.IGNORECASE)
    safe_subject = re.sub(r'^\[Plaud-AutoFlow\]\s*', '', safe_subject, flags=re.IGNORECASE)
    safe_subject = re.sub(r'\[plaud.*?\]', '', safe_subject, flags=re.IGNORECASE)
    safe_subject = re.sub(r'\b\d{2}[-/]\d{2}\b', '', safe_subject)
    safe_subject = re.sub(r'[\\/:*?"<>|]', '-', safe_subject)
    safe_subject = safe_subject.strip()
    safe_subject = re.sub(r'^[- \t]+', '', safe_subject).strip()
    
    if not safe_subject:
        safe_subject = "Meeting Recording"
        
    return doc_date, safe_subject


def _extract_details_llm(subject: str, date_str: str, text: str) -> dict:
    """Use LLM to extract summary, outline, and actionables."""
    from toolbox.lib.llm import call_json
    prompt = EXTRACT_PROMPT.format(
        subject=subject,
        date_str=date_str,
        text=text[:8000] # Increased context window slightly
    )
    return call_json(prompt, max_tokens=1500)


def _build_markdown(subject: str, date_str: str, details: dict, original_text: str) -> str:
    lines = [f'# {subject}', '']
    lines.append(f'**Date:** {date_str}')
    lines.append(f'**Source:** Plaud Email Ingestion')
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

    if details.get('outline'):
        lines.append('## Outline')
        lines.append('')
        lines.append(details['outline'])
        lines.append('')
        lines.append('---')
        lines.append('')

    if details.get('decisions'):
        lines.append('## Key Decisions')
        lines.append('')
        for dec in details['decisions']:
            lines.append(f'- {dec}')
        lines.append('')
        lines.append('---')
        lines.append('')

    lines.append('## Transcript')
    lines.append('')
    lines.append(original_text)
    
    return '\n'.join(lines)


def process(email: dict, state: dict, service=None) -> str | None:
    raw_subject = email['subject']
    date_header = email['date']
    
    doc_date, subject = _parse_date_and_subject(date_header, raw_subject)
    
    # Combine plain text body with text attachments
    full_text = email.get('plain', '')
    
    if service and email.get('attachments'):
        for att in email['attachments']:
            if att['mimeType'] in ('text/plain', 'text/markdown') or att['filename'].endswith(('.txt', '.md')):
                try:
                    raw_bytes = get_attachment(service, email['id'], att['attachmentId'])
                    att_text = raw_bytes.decode('utf-8', errors='replace')
                    full_text += f"\n\n--- Attachment: {att['filename']} ---\n\n" + att_text
                except Exception as e:
                    logger.warning(f"Failed to fetch attachment {att['filename']}: {e}")

    # 1. Extract details via LLM
    details = _extract_details_llm(subject, doc_date, full_text)
    
    # 2. Build and save markdown
    # Format: 01 - Second Brain/Plaud/YYYY-MM-DD - Subject.md
    filename = f"{doc_date} - {subject}.md"
    
    content = _build_markdown(subject, doc_date, details, full_text)
    # Using 'Plaud' folder as target under Memory root
    append_to_memory('Plaud', filename, content)
    
    # 3. Handle Action Items
    action_items = details.get('action_items', [])
    created_tasks = 0
    for item in action_items:
        # Use task_utils to add to Google Tasks if sync_to_google_tasks=True
        if add_task(
            subject=item['text'],
            sender=f"Plaud: {subject}",
            reason=item.get('context') or "Extracted from voice recording",
            priority="medium",
            date_str=item.get('due_date') or doc_date,
            sync_to_google_tasks=True
        ):
            created_tasks += 1
            
    summary = f"Plaud: {subject}"
    if created_tasks:
        summary += f" ({created_tasks} tasks created)"
        
    logger.info(f"Processed Plaud email: {subject}")
    return summary
