"""
Tests for bin/dedup_memory.py — block parsing and dedup logic.
No Drive calls; only the pure functions are tested.
"""
import unittest
from toolbox.bin.dedup_memory import (
    _split_blocks, _rejoin, dedup_content,
    _travel_key, _order_key, _receipt_key,
)

TRAVEL_BLOCK_A = (
    '## 2026-04-15 — Flight\n'
    '**Vendor:** Delta\n'
    '**Status:** [Confirmed] 2026-04-15\n'
    '**Confirmation:** HXXKJD'
)
TRAVEL_BLOCK_B = (
    '## 2026-04-20 — Hotel\n'
    '**Vendor:** Marriott\n'
    '**Status:** [Confirmed] 2026-04-20'
)

ORDER_BLOCK_A = (
    '## 2026-04-10 — Order #112-3456789 [Confirmed]\n'
    '**Vendor:** Amazon\n'
    '**Total:** $49.99'
)
ORDER_BLOCK_B = (
    '## 2026-04-11 — Order #112-3456789 [Shipped]\n'
    '**Vendor:** Amazon\n'
    '**Tracking:** 1Z999AA1'
)

RECEIPT_BLOCK_A = (
    '## 2026-04-10 — Receipt\n'
    '**Vendor:** Toyota Financial\n'
    '**Amount:** $584.99'
)
RECEIPT_BLOCK_B = (
    '## 2026-04-15 — Receipt\n'
    '**Vendor:** Netflix\n'
    '**Amount:** $17.99'
)


def _content(*blocks):
    return '\n---\n'.join(blocks) + '\n---\n'


class TestSplitBlocks(unittest.TestCase):

    def test_single_block(self):
        content = '## 2026-04-15 — Flight\n**Vendor:** Delta\n---\n'
        blocks = _split_blocks(content)
        self.assertEqual(len(blocks), 1)
        self.assertIn('Delta', blocks[0])

    def test_two_blocks(self):
        content = _content(TRAVEL_BLOCK_A, TRAVEL_BLOCK_B)
        blocks = _split_blocks(content)
        self.assertEqual(len(blocks), 2)

    def test_empty_content(self):
        self.assertEqual(_split_blocks(''), [])
        self.assertEqual(_split_blocks('---'), [])

    def test_whitespace_only_blocks_ignored(self):
        content = '## Block A\n---\n   \n---\n## Block B\n---\n'
        blocks = _split_blocks(content)
        self.assertEqual(len(blocks), 2)


class TestTravelKey(unittest.TestCase):

    def test_extracts_date_vendor_type(self):
        key = _travel_key(TRAVEL_BLOCK_A)
        self.assertIn('2026-04-15', key)
        self.assertIn('Delta', key)
        self.assertIn('Flight', key)

    def test_different_types_produce_different_keys(self):
        self.assertNotEqual(_travel_key(TRAVEL_BLOCK_A), _travel_key(TRAVEL_BLOCK_B))

    def test_identical_blocks_same_key(self):
        self.assertEqual(_travel_key(TRAVEL_BLOCK_A), _travel_key(TRAVEL_BLOCK_A))


class TestOrderKey(unittest.TestCase):

    def test_extracts_order_number(self):
        key = _order_key(ORDER_BLOCK_A)
        self.assertIn('112-3456789', key)

    def test_same_order_different_status_same_key(self):
        """Two emails for the same order# (Confirmed + Shipped) have the same key."""
        self.assertEqual(_order_key(ORDER_BLOCK_A), _order_key(ORDER_BLOCK_B))

    def test_no_order_number_falls_back_to_date_vendor(self):
        block = '## 2026-04-10 — Order\n**Vendor:** Amazon\n'
        key = _order_key(block)
        self.assertIn('2026-04-10', key)
        self.assertIn('Amazon', key)


class TestReceiptKey(unittest.TestCase):

    def test_extracts_date_and_amount(self):
        key = _receipt_key(RECEIPT_BLOCK_A)
        self.assertIn('2026-04-10', key)
        self.assertIn('584.99', key)

    def test_different_receipts_different_keys(self):
        self.assertNotEqual(_receipt_key(RECEIPT_BLOCK_A), _receipt_key(RECEIPT_BLOCK_B))

    def test_no_amount_falls_back_to_vendor(self):
        block = '## 2026-04-10 — Receipt\n**Vendor:** Netflix\n'
        key = _receipt_key(block)
        self.assertIn('Netflix', key)


class TestDedupContent(unittest.TestCase):

    def test_no_duplicates_unchanged(self):
        content = _content(TRAVEL_BLOCK_A, TRAVEL_BLOCK_B)
        cleaned, removed = dedup_content(content, _travel_key)
        self.assertEqual(removed, 0)
        blocks = _split_blocks(cleaned)
        self.assertEqual(len(blocks), 2)

    def test_exact_duplicate_removed(self):
        content = _content(TRAVEL_BLOCK_A, TRAVEL_BLOCK_A)
        cleaned, removed = dedup_content(content, _travel_key)
        self.assertEqual(removed, 1)
        blocks = _split_blocks(cleaned)
        self.assertEqual(len(blocks), 1)

    def test_three_copies_two_removed(self):
        content = _content(TRAVEL_BLOCK_A, TRAVEL_BLOCK_A, TRAVEL_BLOCK_A)
        cleaned, removed = dedup_content(content, _travel_key)
        self.assertEqual(removed, 2)
        self.assertEqual(len(_split_blocks(cleaned)), 1)

    def test_first_occurrence_kept(self):
        """The FIRST block is kept, not the last."""
        block_v1 = TRAVEL_BLOCK_A  # status Confirmed
        block_v2 = TRAVEL_BLOCK_A.replace('Confirmed', 'Check-in')
        content = _content(block_v1, block_v2)
        cleaned, removed = dedup_content(content, _travel_key)
        self.assertEqual(removed, 1)
        self.assertIn('Confirmed', cleaned)
        self.assertNotIn('Check-in', cleaned)

    def test_mixed_unique_and_duplicate(self):
        content = _content(TRAVEL_BLOCK_A, TRAVEL_BLOCK_B, TRAVEL_BLOCK_A)
        cleaned, removed = dedup_content(content, _travel_key)
        self.assertEqual(removed, 1)
        self.assertEqual(len(_split_blocks(cleaned)), 2)

    def test_orders_same_order_number_deduped(self):
        content = _content(ORDER_BLOCK_A, ORDER_BLOCK_B)
        cleaned, removed = dedup_content(content, _order_key)
        self.assertEqual(removed, 1)

    def test_receipts_different_amounts_kept(self):
        content = _content(RECEIPT_BLOCK_A, RECEIPT_BLOCK_B)
        cleaned, removed = dedup_content(content, _receipt_key)
        self.assertEqual(removed, 0)
        self.assertEqual(len(_split_blocks(cleaned)), 2)


if __name__ == '__main__':
    unittest.main()
