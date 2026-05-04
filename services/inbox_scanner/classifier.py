"""
LLM-based email classifier for inbox_scanner.
Returns one of: action_required, inquiry, skip.
"""
import json
import logging
import re

logger = logging.getLogger('InboxScanner.Classifier')

CLASSIFY_PROMPT = """Classify this email for a personal inbox scanner.

Sender: {sender}
Subject: {subject}
Body excerpt:
{body}

Categories:
- action_required: bills due, payment deadlines, form completions, appointment confirmations requiring action, legal/financial notices needing response
- inquiry: from a real human (not automated) asking a question or starting a conversation that needs a reply
- skip: newsletters, promotions, automated notifications, order/shipping updates, marketing, social alerts, anything not requiring action

Rules:
- If automated or system-generated, prefer skip over action_required unless there is a clear deadline or required action
- If from a real person asking something, prefer inquiry
- Government renewal deadlines (passport, driver's license, REAL ID, visa, registration) → action_required regardless of whether the sender looks automated
- Bank/credit card fraud or security alerts ("card not present", "unusual activity", "suspicious charge", "verify your identity") → action_required regardless of sender
- When in doubt, use skip

Return ONLY valid JSON: {{"category": "...", "reason": "one sentence", "priority": "high|normal"}}"""


def classify_email(sender: str, subject: str, body: str) -> dict:
    from toolbox.lib.llm_gateway import call_llm, _parse_json
    try:
        res = call_llm(
            task_type='automation',
            prompt=CLASSIFY_PROMPT.format(
                sender=sender,
                subject=subject,
                body=body[:2000],
            )
        )
        raw = res.get('text', '')
    except Exception as e:
        logger.warning(f'LLM Gateway call failed for {sender}: {e}')
        return {'category': 'skip', 'reason': f'LLM Gateway error: {e}', 'priority': 'normal'}

    if not raw:
        return {'category': 'skip', 'reason': 'LLM Gateway unavailable', 'priority': 'normal'}
    try:
        return _parse_json(raw)
    except Exception as e:
        logger.warning(f'Classify parse failed for {sender}: {e}')
        return {'category': 'skip', 'reason': str(e)[:80], 'priority': 'normal'}
