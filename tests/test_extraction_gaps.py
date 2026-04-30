
"""
Reproduction tests for extraction gaps identified in #104, #97, and #96.
"""
import unittest
from unittest.mock import patch, MagicMock

def _make_email(vendor, subject, plain='', date='2026-04-25'):
    return {
        'vendor': vendor,
        'subject': subject,
        'plain': plain,
        'date': date,
        'id': f'msg_{vendor}',
    }

class TestExtractionGaps(unittest.TestCase):

    # --- #104: Receipts (Telecom, Utility, Healthcare) ---

    def test_tmobile_extraction(self):
        from toolbox.services.email_extractor.categories import receipts
        email = _make_email(
            'T-Mobile',
            'Your T-Mobile Bill is Ready',
            plain='Your autopay of $120.45 will be processed on May 02, 2026. Account number: xxxxxx7890.',
            date='2026-04-25'
        )
        
        appended = []
        def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
            appended.append(content)
            return True

        with patch.object(receipts, 'append_to_memory', fake_append), \
             patch.object(receipts, 'update_in_memory', return_value=True), \
             patch.object(receipts, 'enrich_receipt', side_effect=lambda s, *a, **kw: s):
            receipts.process(email, {})

        self.assertEqual(len(appended), 1)
        block = appended[0]
        # Current logic should catch amount and account, but maybe not due date or payment date reliably
        self.assertIn('**Amount:** $120.45', block)
        self.assertIn('**Account:** ...7890', block)
        # These might fail currently
        self.assertIn('**Payment Date:** 2026-05-02', block)

    def test_pseg_extraction(self):
        from toolbox.services.email_extractor.categories import receipts
        email = _make_email(
            'PSEG Long Island',
            'Your PSEG Long Island Bill',
            plain='Amount Due: $156.78. Payment Due Date: 05/10/2026. Account: 1234-5678-90. Service at: 123 Main St.',
            date='2026-04-25'
        )
        
        appended = []
        def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
            appended.append(content)
            return True

        with patch.object(receipts, 'append_to_memory', fake_append), \
             patch.object(receipts, 'update_in_memory', return_value=True), \
             patch.object(receipts, 'enrich_receipt', side_effect=lambda s, *a, **kw: s):
            receipts.process(email, {})

        self.assertEqual(len(appended), 1)
        block = appended[0]
        self.assertIn('**Amount:** $156.78', block)
        # Account might fail due to hyphens or length
        self.assertIn('**Account:** ...7890', block)
        self.assertIn('**Due Date:** 2026-05-10', block)

    def test_allied_physicians_extraction(self):
        from toolbox.services.email_extractor.categories import receipts
        email = _make_email(
            'Allied Physicians Group',
            'Payment Receipt from Allied Physicians Group',
            plain='Thank you for your payment of $35.00 on 04/24/2026. Transaction ID: 987654321.',
            date='2026-04-25'
        )
        
        appended = []
        def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
            appended.append(content)
            return True

        with patch.object(receipts, 'append_to_memory', fake_append), \
             patch.object(receipts, 'update_in_memory', return_value=True), \
             patch.object(receipts, 'enrich_receipt', side_effect=lambda s, *a, **kw: s):
            receipts.process(email, {})

        self.assertEqual(len(appended), 1)
        block = appended[0]
        # Currently Allied is NOT in FINANCIAL_VENDORS, so it uses generic extraction
        self.assertIn('**Amount:** $35.00', block)
        # Generic extraction doesn't have Payment Date
        self.assertIn('**Payment Date:** 2026-04-24', block)

    # --- #97: Orders (Fallback Extraction) ---

    def test_amazon_fallback_extraction(self):
        from toolbox.services.email_extractor.categories import orders
        email = {
            'vendor': 'Amazon',
            'subject': 'Your Amazon.com order #114-1234567-1234567',
            'plain': 'Order Total: $45.99. Items: 1 of Widget A. Delivery: Wednesday, Apr 29.',
            'date': '2026-04-25',
            'id': 'msg_amazon'
        }
        
        # Mock LLM to return empty
        with patch('toolbox.lib.llm.call_json', return_value={}):
            appended = []
            def fake_append(category, filename, content):
                appended.append(content)
                return True
            
            with patch.object(orders, 'append_to_memory', fake_append), \
                 patch.object(orders, 'update_in_memory', return_value=True):
                orders.process(email, {})
            
        self.assertEqual(len(appended), 1)
        block = appended[0]
        self.assertIn('Order #114-1234567-1234567', block)
        # Fallback regex should catch "Widget A"
        self.assertIn('- Widget A [Update] 2026-04-25', block)
        self.assertIn('**Total:** $45.99', block)

    def test_costco_fallback_extraction(self):
        from toolbox.services.email_extractor.categories import orders
        email = {
            'vendor': 'Costco',
            'subject': 'Order Confirmation - Order #1275228829',
            'plain': 'Total: $1,234.56. Items: 1 of Laptop Computer.',
            'date': '2026-04-25',
            'id': 'msg_costco'
        }
        with patch('toolbox.lib.llm.call_json', return_value={}):
            appended = []
            def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
                appended.append(content)
                return True
            with patch.object(orders, 'append_to_memory', fake_append), \
                 patch.object(orders, 'update_in_memory', return_value=True):
                orders.process(email, {})
        self.assertEqual(len(appended), 1)
        block = appended[0]
        self.assertIn('Order #1275228829', block)
        self.assertIn('- Laptop Computer [Confirmed] 2026-04-25', block)
        self.assertIn('**Total:** $1,234.56', block)

    def test_costco_section_layout_fallback_extraction(self):
        from toolbox.services.email_extractor.categories import orders
        email = {
            'vendor': 'Costco',
            'subject': 'Order Confirmation - Order #1275228830',
            'plain': (
                'Items Ordered\n'
                '1799472 - Kirkland Signature Coffee Beans\n'
                'Qty 2\n'
                '$14.99\n'
                'Grand Total: $29.98\n'
            ),
            'date': '2026-04-25',
            'id': 'msg_costco_section'
        }
        with patch('toolbox.lib.llm.call_json', return_value={}):
            appended = []
            def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
                appended.append(content)
                return True
            with patch.object(orders, 'append_to_memory', fake_append), \
                 patch.object(orders, 'update_in_memory', return_value=True):
                orders.process(email, {})
        block = appended[0]
        self.assertIn('Order #1275228830', block)
        self.assertIn('- Kirkland Signature Coffee Beans ×2 — $14.99 [Confirmed] 2026-04-25', block)
        self.assertIn('**Total:** $29.98', block)

    def test_lululemon_fallback_extraction(self):
        from toolbox.services.email_extractor.categories import orders
        email = {
            'vendor': 'lululemon',
            'subject': 'Order Confirmation #c177512979471524',
            'plain': 'Grand Total: $128.00. 1 of ABC Jogger 32".',
            'date': '2026-04-25',
            'id': 'msg_lulu'
        }
        with patch('toolbox.lib.llm.call_json', return_value={}):
            appended = []
            def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
                appended.append(content)
                return True
            with patch.object(orders, 'append_to_memory', fake_append), \
                 patch.object(orders, 'update_in_memory', return_value=True):
                orders.process(email, {})
        self.assertEqual(len(appended), 1)
        block = appended[0]
        self.assertIn('Order #c177512979471524', block)
        self.assertIn('- ABC Jogger 32" [Confirmed] 2026-04-25', block)
        self.assertIn('**Total:** $128.00', block)

    def test_lululemon_section_layout_fallback_extraction(self):
        from toolbox.services.email_extractor.categories import orders
        email = {
            'vendor': 'lululemon',
            'subject': 'Order Confirmation #c177512979471525',
            'plain': (
                'Your gear\n'
                'ABC Classic-Fit Jogger 32"\n'
                'Quantity: 1\n'
                '$128.00\n'
                'Grand Total: $128.00\n'
                'Visa ending in 1001\n'
            ),
            'date': '2026-04-25',
            'id': 'msg_lulu_section'
        }
        with patch('toolbox.lib.llm.call_json', return_value={}):
            appended = []
            def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
                appended.append(content)
                return True
            with patch.object(orders, 'append_to_memory', fake_append), \
                 patch.object(orders, 'update_in_memory', return_value=True):
                orders.process(email, {})
        block = appended[0]
        self.assertIn('Order #c177512979471525', block)
        self.assertIn('- ABC Classic-Fit Jogger 32" — $128.00 [Confirmed] 2026-04-25', block)
        self.assertIn('**Payment Method:** Visa ending in 1001', block)

    # --- #96: Toyota Financial ---

    def test_toyota_financial_extraction(self):
        from toolbox.services.email_extractor.categories import receipts
        email = _make_email(
            'Toyota Financial',
            'Payment Confirmation',
            plain='Your payment of $584.99 has been received for account ending in 5555. Posted on Apr 24, 2026.',
            date='2026-04-25'
        )
        
        appended = []
        def fake_append(category, filename, content, dedup_date='', dedup_ids=()):
            appended.append(content)
            return True

        with patch.object(receipts, 'append_to_memory', fake_append), \
             patch.object(receipts, 'update_in_memory', return_value=True), \
             patch.object(receipts, 'enrich_receipt', side_effect=lambda s, *a, **kw: s):
            receipts.process(email, {})

        self.assertEqual(len(appended), 1)
        block = appended[0]
        self.assertIn('**Amount:** $584.99', block)
        self.assertIn('**Account:** ...5555', block)
        self.assertIn('**Payment Date:** 2026-04-24', block)
