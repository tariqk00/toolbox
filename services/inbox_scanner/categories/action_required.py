"""
Action Required category processor.
Handles bills due, payment deadlines, form completions, appointment confirmations, legal notices.
"""
from .base import CategoryProcessor


class ActionRequiredProcessor(CategoryProcessor):
    def category_name(self) -> str:
        return 'action_required'

    def process(self, email: dict, classification: dict) -> dict | None:
        return {
            'category': 'action_required',
            'date': email['date'],
            'sender': email['from'],
            'subject': email['subject'],
            'reason': classification.get('reason', ''),
            'priority': classification.get('priority', 'normal'),
        }
