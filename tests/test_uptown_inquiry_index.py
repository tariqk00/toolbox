import unittest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

# Mock Google dependencies
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['googleapiclient.http'] = MagicMock()
sys.modules['googleapiclient.errors'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.credentials'] = MagicMock()

# Mock internal lib dependencies that import google modules
sys.modules['toolbox.lib.google_api'] = MagicMock()
sys.modules['toolbox.lib.drive_utils'] = MagicMock()
sys.modules['dotenv'] = MagicMock()

from toolbox.services.inbox_scanner import actions


class TestUptownInquiryIndex(unittest.TestCase):
    def test_upsert_inquiry_entry_includes_thread_id_and_pending_status(self):
        content = ''
        item = {
            'date': '2026-04-20',
            'subject': 'Availability',
            'tenant': 'Tiffany Craig',
            'platform': 'Direct',
            'sender': 'tiffany@example.com',
            'questions': ['How do I apply?'],
            'thread_id': 'thread-123',
        }
        updated = actions.upsert_uptown_inquiry_entry(content, item)
        self.assertIn('**Thread ID:** thread-123', updated)
        self.assertIn('**KB File:** Pending', updated)
        self.assertIn('**Response:** Pending', updated)

    def test_upsert_replaces_existing_thread_block(self):
        original = (
            '## 2026-04-20 — Availability\n'
            '**From:** tiffany@example.com (Direct)\n'
            '**Thread ID:** thread-123\n'
            '**KB File:** Pending\n'
            '**Response:** Pending\n'
            '---\n'
        )
        item = {
            'date': '2026-04-20',
            'subject': 'Availability',
            'tenant': 'Tiffany Craig',
            'platform': 'Direct',
            'sender': 'tiffany@example.com',
            'unit_interest': 'studio',
            'thread_id': 'thread-123',
        }
        updated = actions.upsert_uptown_inquiry_entry(original, item)
        self.assertEqual(updated.count('**Thread ID:** thread-123'), 1)
        self.assertIn('**Interested in:** studio', updated)

    @patch('toolbox.services.email_extractor.writers.set_memory_content')
    @patch('toolbox.services.email_extractor.writers.get_memory_content')
    def test_sync_marks_responded_and_sets_kb_filename(self, mock_get_content, mock_set_content):
        mock_get_content.return_value = (
            '## 2026-04-20 — Availability\n'
            '**From:** tiffany@example.com (Direct)\n'
            '**Thread ID:** thread-123\n'
            '**KB File:** Pending\n'
            '**Response:** Pending\n'
            '---\n'
        )
        actions.sync_uptown_inquiry_index([
            {'thread_id': 'thread-123', '_kb_filename': '2026-04-20 -- Tiffany-Craig -- Availability -- thread-123.md'}
        ])
        written = mock_set_content.call_args.args[2]
        self.assertIn('**KB File:** 2026-04-20 -- Tiffany-Craig -- Availability -- thread-123.md', written)
        self.assertIn('**Response:** Responded', written)


if __name__ == '__main__':
    unittest.main()
