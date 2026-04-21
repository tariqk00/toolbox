"""
Tests for orders.py lifecycle format — placeholder fields and stage transitions.
All offline; Drive, Gmail, and Gemini are mocked.
"""
import unittest
from unittest.mock import patch, MagicMock


GOOD_EXTRACT = {'items': [{'name': 'Anker Cable', 'qty': '1', 'price': '$15.99'}],
                'total': '$15.99', 'tracking': '1Z999AA1'}
EMPTY_EXTRACT = {'items': [], 'total': '', 'tracking': ''}


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

    def fake_update(category, filename, old_text, new_text):
        updated[old_text] = new_text
        return old_text in '\n'.join(appended)  # True if placeholder exists

    extract = extract_result if extract_result is not None else GOOD_EXTRACT

    with patch.object(orders, 'append_to_memory', fake_append), \
         patch.object(orders, 'update_in_memory', fake_update), \
         patch.object(orders, '_extract_items_llm', return_value=extract), \
         patch.object(orders, 'enrich_order', side_effect=lambda s, *a, **kw: s):
        result = orders.process(email, state)

    return result, appended, updated, state


class TestNewOrderFormat(unittest.TestCase):

    def test_new_order_has_shipped_placeholder(self):
        email = _make_email('Amazon', 'Your order has been confirmed', date='2026-04-10')
        _, appended, _, _ = _run_process(email)
        self.assertEqual(len(appended), 1)
        self.assertIn('**Shipped:** —', appended[0])

    def test_new_order_has_delivered_placeholder(self):
        email = _make_email('Amazon', 'Your order has been confirmed', date='2026-04-10')
        _, appended, _, _ = _run_process(email)
        self.assertIn('**Delivered:** —', appended[0])

    def test_new_order_has_status_field(self):
        email = _make_email('Amazon', 'Your order has been confirmed', date='2026-04-10')
        _, appended, _, _ = _run_process(email)
        self.assertIn('**Status:** [Confirmed]', appended[0])

    def test_new_shipped_order_fills_shipped_placeholder(self):
        """If first email is a Shipped notification, placeholder is pre-filled."""
        email = _make_email('Amazon', 'Your order has shipped', date='2026-04-11')
        _, appended, _, state = _run_process(email)
        self.assertNotIn('**Shipped:** —', appended[0])
        self.assertIn('**Shipped:** 2026-04-11', appended[0])

    def test_state_stores_placeholder_lines(self):
        email = _make_email('Amazon', 'Your order has been confirmed', date='2026-04-10')
        email['subject'] = 'Your order #112-3456789 has been confirmed'
        _, _, _, state = _run_process(email)
        known = state.get('order_numbers', {})
        order = known.get('112-3456789', {})
        self.assertIn('shipped_line', order)
        self.assertEqual(order['shipped_line'], '**Shipped:** —')
        self.assertIn('delivered_line', order)
        self.assertEqual(order['delivered_line'], '**Delivered:** —')


class TestStatusTransitions(unittest.TestCase):

    def _make_state_with_order(self, order_num='112-3456789', status='Confirmed'):
        return {
            'order_numbers': {
                order_num: {
                    'vendor': 'Amazon', 'date': '2026-04-10', 'status': status,
                    'items': {
                        'anker_cable': {'name': 'Anker Cable', 'price': '$15.99',
                                        'status': status, 'date': '2026-04-10'},
                    },
                    'shipped_line': '**Shipped:** —',
                    'delivered_line': '**Delivered:** —',
                }
            }
        }

    def test_confirmed_to_shipped_updates_placeholder(self):
        state = self._make_state_with_order()
        email = _make_email('Amazon', 'Your order #112-3456789 has shipped', date='2026-04-11')
        _, _, updated, _ = _run_process(email, state=state)
        self.assertIn('**Shipped:** —', updated)
        new_val = updated['**Shipped:** —']
        self.assertIn('2026-04-11', new_val)

    def test_shipped_includes_carrier_when_detected(self):
        state = self._make_state_with_order()
        email = _make_email('Amazon', 'Your order #112-3456789 has shipped',
                            plain='Shipped via UPS Ground', date='2026-04-11')
        _, _, updated, _ = _run_process(email, state=state)
        shipped_val = updated.get('**Shipped:** —', '')
        self.assertIn('UPS', shipped_val)

    def test_shipped_includes_tracking_from_llm(self):
        state = self._make_state_with_order()
        email = _make_email('Amazon', 'Your order #112-3456789 has shipped', date='2026-04-11')
        _, _, updated, _ = _run_process(email, state=state,
                                         extract_result={'items': [], 'total': '', 'tracking': '1Z999AA1'})
        shipped_val = updated.get('**Shipped:** —', '')
        self.assertIn('1Z999AA1', shipped_val)

    def test_confirmed_to_delivered_updates_delivered_placeholder(self):
        state = self._make_state_with_order(status='Shipped')
        state['order_numbers']['112-3456789']['shipped_line'] = '**Shipped:** 2026-04-11'
        email = _make_email('Amazon', 'Your order #112-3456789 has been delivered', date='2026-04-12')
        _, _, updated, _ = _run_process(email, state=state)
        self.assertIn('**Delivered:** —', updated)
        self.assertIn('2026-04-12', updated['**Delivered:** —'])

    def test_telegram_summary_shows_transition(self):
        state = self._make_state_with_order()
        email = _make_email('Amazon', 'Your order #112-3456789 has shipped', date='2026-04-11')
        result, _, _, _ = _run_process(email, state=state)
        self.assertIn('Confirmed → Shipped', result)
        self.assertIn('Amazon #112-3456789', result)

    def test_same_status_no_action(self):
        state = self._make_state_with_order(status='Shipped')
        email = _make_email('Amazon', 'Your order #112-3456789 has shipped', date='2026-04-11')
        result, appended, updated, _ = _run_process(email, state=state)
        self.assertIsNone(result)
        self.assertEqual(len(appended), 0)


class TestRefundStatus(unittest.TestCase):

    def test_refunded_detected_from_subject(self):
        from toolbox.services.email_extractor.categories.orders import _extract_status
        self.assertEqual(_extract_status('Your refund has been issued'), 'Refunded')
        self.assertEqual(_extract_status('Return approved for order'), 'Refunded')
        self.assertEqual(_extract_status('Credit issued to your account'), 'Refunded')

    def test_refund_appends_refunded_field(self):
        state = {
            'order_numbers': {
                '112-3456789': {
                    'vendor': 'Amazon', 'date': '2026-04-10', 'status': 'Delivered',
                    'items': {}, 'shipped_line': '**Shipped:** 2026-04-11',
                    'delivered_line': '**Delivered:** 2026-04-12',
                }
            }
        }
        email = _make_email('Amazon', 'Your refund for order #112-3456789 has been issued',
                            date='2026-04-15')
        _, appended, _, _ = _run_process(email, state=state)
        self.assertTrue(any('Refunded' in a for a in appended))


if __name__ == '__main__':
    unittest.main()
