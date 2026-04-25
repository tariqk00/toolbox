"""
Tests for richer financial receipt extraction.
Offline: Drive writes and optional enrichment are mocked.
"""
import unittest
from unittest.mock import patch


def _make_email(vendor, subject, plain='', date='2026-04-25'):
    return {
        'vendor': vendor,
        'subject': subject,
        'plain': plain,
        'date': date,
        'id': f'msg_{vendor}',
    }


def _run_receipt(email, state=None):
    from toolbox.services.email_extractor.categories import receipts
    if state is None:
        state = {}
    appended = []

    def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
        appended.append(content)
        return True

    with patch.object(receipts, 'append_to_memory', fake_append), \
         patch.object(receipts, 'update_in_memory', return_value=True), \
         patch.object(receipts, 'enrich_receipt', side_effect=lambda s, *a, **kw: s):
        result = receipts.process(email, state)

    return result, appended, state


class TestFinancialReceiptExtraction(unittest.TestCase):

    def test_capital_one_payment_due_fields(self):
        email = _make_email(
            'Capital One',
            'Upcoming Minimum Payment due alert',
            plain=(
                'Your minimum payment of $40.00 is due on May 15, 2026. '
                'Card ending in 1234.'
            ),
            date='2026-04-25',
        )

        summary, appended, _ = _run_receipt(email)

        self.assertEqual(len(appended), 1)
        block = appended[0]
        self.assertIn('**Institution:** Capital One', block)
        self.assertIn('**Type:** [Payment Due] 2026-04-25', block)
        self.assertIn('**Amount:** $40.00', block)
        self.assertIn('**Account:** ...1234', block)
        self.assertIn('**Due Date:** 2026-05-15', block)
        self.assertIn('Capital One: $40.00 [Payment Due] — ...1234 | due 2026-05-15', summary)

    def test_chase_payment_confirmation_fields(self):
        email = _make_email(
            'Chase',
            'Your payment has posted',
            plain=(
                'Payment amount: $250.00. Posted on 04/24/2026. '
                'Payment method: checking account ending in 6789.'
            ),
            date='2026-04-25',
        )

        summary, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Institution:** Chase', block)
        self.assertIn('**Type:** [Payment] 2026-04-25', block)
        self.assertIn('**Amount:** $250.00', block)
        self.assertIn('**Account:** ...6789', block)
        self.assertIn('**Payment Method:** checking account ending in 6789', block)
        self.assertIn('**Payment Date:** 2026-04-24', block)
        self.assertIn('Chase: $250.00 [Payment] — ...6789 | 2026-04-24', summary)

    def test_citi_statement_fields(self):
        email = _make_email(
            'Citi / Costco Visa',
            'Your statement is ready',
            plain='Statement balance: $1,234.56. Statement Date: Apr 20, 2026. Account ending in 4321.',
            date='2026-04-25',
        )

        summary, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Institution:** Citi / Costco Visa', block)
        self.assertIn('**Type:** [Statement] 2026-04-25', block)
        self.assertIn('**Amount:** $1,234.56', block)
        self.assertIn('**Account:** ...4321', block)
        self.assertIn('**Statement Date:** 2026-04-20', block)
        self.assertIn('Citi / Costco Visa: $1,234.56 [Statement] — ...4321', summary)


if __name__ == '__main__':
    unittest.main()
