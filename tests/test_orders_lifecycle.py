"""
Tests for orders.py lifecycle format — placeholder fields and stage transitions.
All offline; Drive, Gmail, and Gemini are mocked.
"""
import unittest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
# Add the parent of the repository to sys.path to support 'from toolbox.lib...'
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

# Mock everything before importing reporter_utils or other local modules that import google
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['googleapiclient.http'] = MagicMock()
sys.modules['googleapiclient.errors'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.credentials'] = MagicMock()

# Mock internal lib dependencies that import google modules
sys.modules['toolbox.lib.google_api'] = MagicMock()
sys.modules['toolbox.lib.drive_utils'] = MagicMock()

GOOD_EXTRACT = {'items': [{'name': 'Anker Cable', 'qty': '1', 'price': '$15.99'}],
                'total': '$15.99', 'tracking': '1Z999AA1'}
EMPTY_EXTRACT = {'items': [], 'total': '', 'tracking': ''}
MULTI_QTY_EXTRACT = {'items': [{'name': 'Anker Cable', 'qty': '2', 'price': '$15.99'}],
                     'total': '$31.98', 'tracking': ''}


def _make_email(vendor, subject, plain='', date='2026-04-10'):
    return {'vendor': vendor, 'subject': subject, 'plain': plain,
            'html': None, 'date': date, 'id': f'msg_{vendor}'}


def _run_process(email, state=None, extract_result=None):
    from toolbox.services.email_extractor.categories import orders
    if state is None:
        state = {}
    appended = []
    updated = {}

    def fake_append(category, filename, content):
        appended.append(content)

    def fake_update(category, filename, old, new):
        updated[old] = new
        return True

    with patch('toolbox.services.email_extractor.categories.orders.append_to_memory', side_effect=fake_append), \
         patch('toolbox.services.email_extractor.categories.orders.update_in_memory', side_effect=fake_update), \
         patch('toolbox.services.email_extractor.categories.orders._extract_items_llm', return_value=extract_result or GOOD_EXTRACT):
        summary = orders.process(email, state)
        return summary, appended, updated, state


class TestNewOrderFormat(unittest.TestCase):

    def test_new_order_has_shipped_placeholder(self):
        email = _make_email('Amazon', 'Your order has been confirmed')
        _, appended, _, _ = _run_process(email)
        self.assertIn('**Status:** [Confirmed]', appended[0])
        self.assertIn('**Shipped:** —', appended[0])

    def test_new_order_has_delivered_placeholder(self):
        email = _make_email('Amazon', 'Your order has been confirmed')
        _, appended, _, _ = _run_process(email)
        self.assertIn('**Delivered:** —', appended[0])

    def test_new_order_has_explicit_order_number_field(self):
        email = _make_email('Amazon', 'Your order has been confirmed', plain='Order #112-3456789-0123456')
        _, appended, _, _ = _run_process(email)
        self.assertIn('**Order Number:** 112-3456789-0123456', appended[0])

    def test_new_shipped_order_fills_shipped_placeholder(self):
        """If first email is a Shipped notification, placeholder is pre-filled."""
        email = _make_email('Amazon', 'Your order has shipped', plain='Order Number: 112-3456789-0123456')
        _, appended, _, state = _run_process(email)
        self.assertIn('**Shipped:** 2026-04-10', appended[0])
        self.assertIn('**Status:** [Shipped]', appended[0])
        order = state['order_numbers']['112-3456789-0123456']
        self.assertEqual(order['status'], 'Shipped')

    def test_new_order_falls_back_to_body_items_and_total(self):
        email = _make_email(
            'Amazon',
            'Order Confirmation',
            plain='Order total: $45.67. Items: Widgets, Gadgets.',
        )
        _, appended, _, state = _run_process(email, extract_result=EMPTY_EXTRACT)
        self.assertIn('**Total:** $45.67', appended[0])

    def test_new_order_falls_back_to_payment_method(self):
        email = _make_email(
            'Amazon',
            'Order Confirmation',
            plain='Order total: $45.67. Items: 1 of Widget A. Payment method: Amex ending in 2002.',
        )
        _, appended, _, _ = _run_process(email, extract_result=EMPTY_EXTRACT)
        self.assertIn('**Payment Method:** Amex ending in 2002', appended[0])

    def test_order_fallback_uses_n_a(self):
        email = _make_email(
            'UnknownVendor',
            'Order Confirmation',
            plain='Total: $10.00',
        )
        _, appended, _, _ = _run_process(email, extract_result=EMPTY_EXTRACT)
        self.assertIn('**Order Number:** N/A', appended[0])

    def test_costco_confirmation_fallback(self):
        email = _make_email(
            'Costco',
            'Order Confirmation - Order # 123456789',
            plain='Items: 1234567-Kirkland Coffee',
        )
        _, appended, _, _ = _run_process(email, extract_result=EMPTY_EXTRACT)
        # Verify order number is extracted
        self.assertIn('**Order Number:** 123456789', appended[0])

    def test_state_stores_placeholder_lines(self):
        email = _make_email('Amazon', 'Order Confirmation', plain='Order #112-3456789-0123456')
        _, _, _, state = _run_process(email)
        order = state['order_numbers']['112-3456789-0123456']
        self.assertIn('shipped_line', order)
        self.assertIn('delivered_line', order)

    def test_amazon_pharmacy_state_stores_exact_status_line(self):
        email = _make_email(
            'Amazon Pharmacy',
            'Your PillPack order has shipped',
            plain='Arriving by Apr 25. PillPack order (7 meds).',
            date='2026-04-20',
        )
        _, appended, _, state = _run_process(email, extract_result=EMPTY_EXTRACT)
        self.assertIn('**Status:** [Shipped] 2026-04-20', appended[0])
        self.assertIn('## 2026-04-20 — PillPack 2026-04 [Shipped] 🚚', appended[0])


class TestStatusTransitions(unittest.TestCase):

    def _make_state_with_order(self, order_num='112-3456789', status='Confirmed'):
        return {
            'order_numbers': {
                order_num: {
                    'vendor': 'Amazon',
                    'status': status,
                    'date': '2026-04-10',
                    'product': 'Anker Cable',
                    'status_line': f'**Status:** [{status}] 2026-04-10',
                    'shipped_line': '**Shipped:** —',
                    'delivered_line': '**Delivered:** —',
                    'items': {
                        'anker_cable': {'name': 'Anker Cable', 'status': status, 'date': '2026-04-10'}
                    }
                }
            }
        }

    def test_confirmed_to_shipped_updates_placeholder(self):
        state = self._make_state_with_order()
        email = _make_email('Amazon', 'Your order #112-3456789 has shipped', date='2026-04-12')
        _, _, updated, _ = _run_process(email, state=state)
        # Verify the Shipped line is updated
        self.assertIn('**Shipped:** —', updated)
        self.assertIn('**Shipped:** 2026-04-12', updated['**Shipped:** —'])

    def test_confirmed_to_delivered_updates_delivered_placeholder(self):
        state = self._make_state_with_order()
        email = _make_email('Amazon', 'Your order #112-3456789 has been delivered', date='2026-04-15')
        _, _, updated, _ = _run_process(email, state=state)
        self.assertIn('**Delivered:** —', updated)
        self.assertEqual(updated['**Delivered:** —'], '**Delivered:** 2026-04-15')

    def test_telegram_summary_shows_transition(self):
        state = self._make_state_with_order()
        email = _make_email('Amazon', 'Your order #112-3456789 has shipped')
        result, _, _, _ = _run_process(email, state=state)
        self.assertIn('Confirmed → Shipped', result)

    def test_amazon_pharmacy_status_update(self):
        state = {
            'order_numbers': {
                'pillpack:2026-04': {
                    'vendor': 'Amazon Pharmacy',
                    'status': 'Processing',
                    'date': '2026-04-20',
                    'product': 'PillPack medications',
                    'status_line': '**Status:** [Processing] 2026-04-20',
                }
            }
        }
        email = _make_email(
            'Amazon Pharmacy',
            'Your PillPack order has shipped',
            plain='Arriving by Apr 25.',
            date='2026-04-21',
        )
        summary, _, updated, _ = _run_process(email, state=state, extract_result=EMPTY_EXTRACT)
        self.assertEqual(summary, 'Amazon Pharmacy → Shipped 🚚')
        self.assertIn('## 2026-04-21 — PillPack 2026-04 [Shipped] 🚚', updated.values())


class TestRefundStatus(unittest.TestCase):

    def test_refunded_detected_from_subject(self):
        from toolbox.services.email_extractor.categories.orders import _extract_status
        self.assertEqual(_extract_status('Your refund has been issued'), 'Refunded')

    def test_refund_appends_note(self):
        state = {
            'order_numbers': {
                '112-1234567-1234567': {
                    'vendor': 'Amazon',
                    'status': 'Delivered',
                    'date': '2026-04-01',
                    'product': 'Widget',
                    'status_line': '**Status:** [Delivered] 2026-04-01',
                }
            }
        }
        email = _make_email('Amazon', 'Your refund has been issued for order #112-1234567-1234567', date='2026-04-05')
        _, appended, _, _ = _run_process(email, state=state)
        # For non-pharmacy, refunded appends a line
        self.assertIn('↳ 2026-04-05: **Refunded**', appended[0])


class TestShippingDetailExtraction(unittest.TestCase):

    def test_tracking_number_labeled(self):
        from toolbox.services.email_extractor.categories.orders import _extract_tracking
        self.assertEqual(
            _extract_tracking('Your tracking number is 1Z999AA10123456784'),
            '1Z999AA10123456784',
        )

    def test_estimated_delivery_normalized(self):
        from toolbox.services.email_extractor.categories.orders import _extract_delivery_date
        self.assertEqual(
            _extract_delivery_date('Your package is arriving by Apr 30, 2026', '2026-04-25'),
            '2026-04-30',
        )


if __name__ == '__main__':
    unittest.main()
