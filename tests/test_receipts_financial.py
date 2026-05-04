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
        self.assertIn('**Merchant:** Capital One', block)
        self.assertIn('**Institution:** Capital One', block)
        self.assertIn('**Category:** Financial Notice', block)
        self.assertIn('**Type:** [Payment Due] 2026-04-25', block)
        self.assertIn('**Amount:** $40.00', block)
        self.assertIn('**Account:** ...1234', block)
        self.assertIn('**Due Date:** 2026-05-15', block)
        self.assertIn('Capital One: $40.00 [Payment Due] — ...1234 | due 2026-05-15', summary['summary'])

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
        self.assertIn('**Merchant:** Chase', block)
        self.assertIn('**Category:** Financial Notice', block)
        self.assertIn('**Institution:** Chase', block)
        self.assertIn('**Type:** [Payment] 2026-04-25', block)
        self.assertIn('**Amount:** $250.00', block)
        self.assertIn('**Account:** ...6789', block)
        self.assertIn('**Transaction Date:** 2026-04-24', block)
        self.assertIn('**Payment Method:** checking account ending in 6789', block)
        self.assertIn('**Payment Date:** 2026-04-24', block)
        self.assertIn('Chase: $250.00 [Payment] — ...6789 | 2026-04-24', summary['summary'])

    def test_chase_due_alert_fields(self):
        email = _make_email(
            'Chase',
            'Your payment due alert',
            plain='Amount due: $95.00. Payment due on May 2, 2026. Card ending in 6789.',
            date='2026-04-25',
        )

        _, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Type:** [Payment Due] 2026-04-25', block)
        self.assertIn('**Amount:** $95.00', block)
        self.assertIn('**Due Date:** 2026-05-02', block)
        self.assertIn('**Account:** ...6789', block)

    def test_citi_statement_fields(self):
        email = _make_email(
            'Citi / Costco Visa',
            'Your statement is ready',
            plain='Statement balance: $1,234.56. Statement Date: Apr 20, 2026. Account ending in 4321.',
            date='2026-04-25',
        )

        summary, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Merchant:** Citi / Costco Visa', block)
        self.assertIn('**Category:** Financial Notice', block)
        self.assertIn('**Institution:** Citi / Costco Visa', block)
        self.assertIn('**Type:** [Statement] 2026-04-25', block)
        self.assertIn('**Amount:** $1,234.56', block)
        self.assertIn('**Account:** ...4321', block)
        self.assertIn('**Transaction Date:** 2026-04-20', block)
        self.assertIn('**Statement Date:** 2026-04-20', block)
        self.assertIn('Citi / Costco Visa: $1,234.56 [Statement] — ...4321', summary['summary'])

    def test_uber_receipt_adds_category_and_transaction_time(self):
        email = _make_email(
            'Uber',
            '[Personal] Your trip receipt',
            plain='Thanks for riding, Tariq. Trip date Apr 25, 2026 at 7:41 PM. Total: $18.42.',
            date='2026-04-25',
        )

        _, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Merchant:** Uber', block)
        self.assertIn('**Category:** Ride Share', block)
        self.assertIn('**Transaction Date:** 2026-04-25', block)
        self.assertIn('**Transaction Time:** 7:41 PM', block)

    def test_capital_one_autopay_scheduled_fields(self):
        email = _make_email(
            'Capital One',
            'Your AutoPay Reminder',
            plain='Automatic payment of $300.00 will withdraw on Apr 30, 2026 from checking account ending in 7956.',
            date='2026-04-27',
        )

        _, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Type:** [Autopay Scheduled] 2026-04-27', block)
        self.assertIn('**Amount:** $300.00', block)
        self.assertIn('**Payment Date:** 2026-04-30', block)
        self.assertIn('**Account:** ...7956', block)
        self.assertIn('**Payment Method:** checking account ending in 7956', block)

    def test_apple_receipt_extracts_amount_and_type(self):
        email = _make_email(
            'Apple',
            'Your receipt from Apple',
            plain='You paid $10.81 for iCloud+ on Apr 27, 2026 using card ending in 4242.',
            date='2026-04-27',
        )

        _, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Merchant:** Apple', block)
        self.assertIn('**Category:** Technology', block)
        self.assertIn('**Type:** [Receipt] 2026-04-27', block)
        self.assertIn('**Amount:** $10.81', block)
        self.assertIn('**Account:** ...4242', block)
        self.assertIn('**Transaction Date:** 2026-04-27', block)

    def test_ezpass_receipt_extracts_amount_and_date(self):
        email = _make_email(
            'E-ZPass NY',
            'E-ZPass replenishment receipt',
            plain='Toll amount $25.00 charged on Apr 24, 2026. Account ending in 1234.',
            date='2026-04-25',
        )

        _, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Merchant:** E-ZPass NY', block)
        self.assertIn('**Category:** Transportation', block)
        self.assertIn('**Amount:** $25.00', block)
        self.assertIn('**Account:** ...1234', block)
        self.assertIn('**Transaction Date:** 2026-04-24', block)

    def test_pseg_due_notice_fields(self):
        email = _make_email(
            'PSEG Long Island',
            'Your bill is due soon',
            plain='Amount due $530.00. Due date May 3, 2026. Account ending in 7452.',
            date='2026-04-25',
        )

        _, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Type:** [Payment Due] 2026-04-25', block)
        self.assertIn('**Amount:** $530.00', block)
        self.assertIn('**Due Date:** 2026-05-03', block)
        self.assertIn('**Account:** ...7452', block)

    def test_toyota_financial_scheduled_payment_fields(self):
        email = _make_email(
            'Toyota Financial',
            'Your automatic payment is scheduled',
            plain='Payment amount $584.99. Autopay date Apr 18, 2026. Account ending in 9373.',
            date='2026-04-15',
        )

        _, appended, _ = _run_receipt(email)

        block = appended[0]
        self.assertIn('**Type:** [Autopay Scheduled] 2026-04-15', block)
        self.assertIn('**Amount:** $584.99', block)
        self.assertIn('**Payment Date:** 2026-04-18', block)
        self.assertIn('**Account:** ...9373', block)


if __name__ == '__main__':
    unittest.main()
