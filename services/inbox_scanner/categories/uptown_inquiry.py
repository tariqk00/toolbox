"""
Uptown Edenton inquiry processor.

Handles rental inquiries landing in operations@uptownedenton.com:
- Extracts tenant details, unit interest, questions
- Generates a shadow response draft (NOT sent — forwarded to Tariq via Telegram)
- Returns structured dict for Drive logging and response tracking

Only runs for cache-miss path (full email body available).
Cache-hit reconstructions (no body) return None to avoid re-alerting on old emails.
"""
import logging
import re

from .base import CategoryProcessor

logger = logging.getLogger('InboxScanner.UptownInquiry')

# Known listing platform senders → friendly label
LISTING_PLATFORMS = {
    'rentalclientservices@zillowrentals.com': 'Zillow',
    'rentalrequest@move.com': 'Move.com / Realtor.com',
    'leads@apartments.com': 'Apartments.com',
    'inquiry@trulia.com': 'Trulia',
    'noreply@hotpads.com': 'HotPads',
}

INQUIRY_EXTRACT_PROMPT = """\
Extract rental inquiry details from this email sent to a property management company.

Return ONLY valid JSON:
{{
  "tenant_name": "full name or empty string",
  "unit_interest": "unit type/size they want, or empty string",
  "move_in": "desired move-in date or timeframe, or empty string",
  "questions": ["list of specific questions they asked"],
  "contact_phone": "phone number if provided, or empty string",
  "notes": "any other relevant detail, or empty string"
}}

Use "" for missing fields. Use [] for questions if none.

Email subject: {subject}
Email body:
{body}"""

SHADOW_RESPONSE_PROMPT = """\
Draft a warm, professional response to this rental inquiry on behalf of Uptown Edenton, a residential apartment community in Edenton, NC.

Guidelines:
- Address the prospect by first name if known
- Thank them for their interest
- If they asked specific questions, acknowledge them briefly — say you'd love to go over details on a call or showing
- Invite them to schedule a tour or call
- Keep it 2-3 short paragraphs, conversational tone
- Do NOT invent specific pricing, unit availability, or amenity details
- Sign off as: Christina | Uptown Edenton

Reference examples from prior real responses:
{examples}

Prospect name: {name}
Their questions: {questions}
Original message:
{body}

Return ONLY the response body text. No subject line. No extra formatting."""


def _sender_email(from_header: str) -> str:
    m = re.search(r'<([^>]+)>', from_header)
    return m.group(1).lower() if m else from_header.lower().strip()


def _get_plain_body(email: dict) -> str:
    from toolbox.services.email_extractor.scanner import html_to_text
    plain = email.get('plain') or ''
    html = email.get('html') or ''
    if plain and not re.search(r'<[a-zA-Z]+[\s>]', plain[:500]):
        return plain
    if html:
        text, _ = html_to_text(html)
        return text
    return plain


class UptownInquiryProcessor(CategoryProcessor):
    def category_name(self) -> str:
        return 'inquiry'

    def process(self, email: dict, classification: dict) -> dict | None:
        from toolbox.lib.llm import call, call_json
        from toolbox.services.inbox_scanner.uptown_response_kb import build_prompt_examples

        body = _get_plain_body(email)
        if not body:
            # Cache-hit reconstruction — fake_email has no body, skip re-alerting
            return None

        sender = _sender_email(email.get('from', ''))
        platform = LISTING_PLATFORMS.get(sender, 'Direct')
        subject = email.get('subject', '')
        date = email.get('date', '')
        thread_id = classification.get('_thread_id', '')

        # Extract inquiry details
        extracted = {}
        try:
            extracted = call_json(INQUIRY_EXTRACT_PROMPT.format(
                subject=subject,
                body=body[:5000],
            ))
        except Exception as e:
            logger.warning(f'Inquiry extraction failed: {e}')

        tenant = (extracted.get('tenant_name') or '').strip()
        unit_interest = (extracted.get('unit_interest') or '').strip()
        move_in = (extracted.get('move_in') or '').strip()
        questions = [q for q in (extracted.get('questions') or []) if q]
        contact_phone = (extracted.get('contact_phone') or '').strip()
        notes = (extracted.get('notes') or '').strip()

        # Generate shadow response
        shadow = ''
        try:
            examples = build_prompt_examples({
                'platform': platform,
                'subject': subject,
                'unit_interest': unit_interest,
                'questions': questions,
                'body': body[:1500],
            })
            shadow = call(SHADOW_RESPONSE_PROMPT.format(
                examples=examples or 'No closely matching examples available.',
                name=tenant or 'there',
                questions=', '.join(questions) if questions else 'none specified',
                body=body[:3000],
            ), max_tokens=400)
        except Exception as e:
            logger.warning(f'Shadow response generation failed: {e}')

        return {
            'category': 'inquiry',
            'date': date,
            'sender': email.get('from', ''),
            'subject': subject,
            'reason': classification.get('reason', ''),
            'platform': platform,
            'tenant': tenant,
            'unit_interest': unit_interest,
            'move_in': move_in,
            'questions': questions,
            'contact_phone': contact_phone,
            'notes': notes,
            'shadow_response': shadow,
            'thread_id': thread_id,
        }
