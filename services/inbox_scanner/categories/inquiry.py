"""
Inquiry category processor.
Handles emails from real people that need a response.
"""
from .base import CategoryProcessor


class InquiryProcessor(CategoryProcessor):
    def category_name(self) -> str:
        return 'inquiry'

    def process(self, email: dict, classification: dict) -> dict | None:
        return {
            'category': 'inquiry',
            'date': email['date'],
            'sender': email['from'],
            'subject': email['subject'],
            'reason': classification.get('reason', ''),
        }
