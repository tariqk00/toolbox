"""
Tests for Tier 1 cost optimizations.
All tests are offline (no LLM, Drive, or network calls).
Run from repo root: python3 -m pytest toolbox/tests/test_tier1_optimizations.py -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, timezone, datetime
from unittest.mock import patch, MagicMock

# Ensure toolbox is on path when running from repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ---------------------------------------------------------------------------
# 1 & 2 — Quota guard and sorter reservation
# ---------------------------------------------------------------------------

class TestQuotaManager(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Patch QUOTA_PATH and COST_LOG_PATH to use temp files
        import toolbox.lib.quota_manager as qm
        self._qm = qm
        self._orig_quota_path = qm.QUOTA_PATH
        self._orig_cost_path  = qm.COST_LOG_PATH
        qm.QUOTA_PATH    = os.path.join(self.tmpdir, 'quota_state.json')
        qm.COST_LOG_PATH = os.path.join(self.tmpdir, 'cost_log.jsonl')

    def tearDown(self):
        self._qm.QUOTA_PATH    = self._orig_quota_path
        self._qm.COST_LOG_PATH = self._orig_cost_path

    def _write_quota(self, tokens_used, calls_today=0):
        state = {
            "date": datetime.now().strftime('%Y-%m-%d'),
            "total_tokens_used": tokens_used,
            "daily_budget": self._qm.DAILY_BUDGET,
            "sorter_calls_today": calls_today
        }
        with open(self._qm.QUOTA_PATH, 'w') as f:
            json.dump(state, f)

    # --- is_exhausted ---
    def test_budget_not_exhausted_when_empty(self):
        self.assertFalse(self._qm.is_exhausted())

    def test_budget_exhausted_at_limit(self):
        self._write_quota(self._qm.DAILY_BUDGET)
        self.assertTrue(self._qm.is_exhausted())

    def test_budget_not_exhausted_below_limit(self):
        self._write_quota(self._qm.DAILY_BUDGET - 1)
        self.assertFalse(self._qm.is_exhausted())

    def test_remaining_never_negative(self):
        self._write_quota(self._qm.DAILY_BUDGET + 1000)
        self.assertEqual(self._qm.remaining(), 0)

    # --- is_rpd_exhausted ---
    def test_rpd_exhausted_at_1400_calls(self):
        self._write_quota(0, calls_today=1400)
        self.assertTrue(self._qm.is_rpd_exhausted())

    def test_rpd_not_exhausted_below_limit(self):
        self._write_quota(0, calls_today=1399)
        self.assertFalse(self._qm.is_rpd_exhausted())

    # --- log_cost ---
    def test_log_cost_creates_jsonl(self):
        self._qm.log_cost('sorter', 10, 5000)
        with open(self._qm.COST_LOG_PATH) as f:
            record = json.loads(f.readline())
        self.assertEqual(record['run_type'], 'sorter')
        self.assertEqual(record['files_processed'], 10)
        self.assertEqual(record['tokens_used'], 5000)
        self.assertIn('cost_usd_est', record)

    def test_log_cost_appends(self):
        self._qm.log_cost('sorter', 5, 1000)
        self._qm.log_cost('backfill', 20, 8000)
        with open(self._qm.COST_LOG_PATH) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])['run_type'], 'backfill')

    def test_record_llm_usage_appends_source_metadata(self):
        self._qm.record_llm_usage(1234, 0.012345, metadata={
            "source": "openclaw",
            "task_type": "heartbeat",
            "provider": "gemini-free",
            "model": "gemini-3.1-pro-preview",
        })

        with open(self._qm.COST_LOG_PATH) as f:
            record = json.loads(f.readline())

        self.assertEqual(record["source"], "openclaw")
        self.assertEqual(record["task_type"], "heartbeat")
        self.assertEqual(record["provider"], "gemini-free")
        self.assertEqual(record["model"], "gemini-3.1-pro-preview")
        self.assertEqual(record["tokens_used"], 1234)


# ---------------------------------------------------------------------------
# 3, 5, 6, 7 — File size limits and bytes logging
# Tests logic managed by LLMGateway and drive_utils.
# ---------------------------------------------------------------------------

class TestAiEngineFileSizeLimits(unittest.TestCase):
    """
    Tests for text/PDF truncation and max_output_tokens.
    """

    def test_spreadsheet_mime_returns_text_plain(self):
        from toolbox.lib.drive_utils import get_ai_supported_mime
        result = get_ai_supported_mime('application/vnd.google-apps.spreadsheet')
        self.assertEqual(result, 'text/plain')

    def test_document_mime_returns_text_plain(self):
        from toolbox.lib.drive_utils import get_ai_supported_mime
        self.assertEqual(get_ai_supported_mime('application/vnd.google-apps.document'), 'text/plain')

    def test_pdf_mime_returns_application_pdf(self):
        from toolbox.lib.drive_utils import get_ai_supported_mime
        self.assertEqual(get_ai_supported_mime('application/pdf'), 'application/pdf')

    def test_image_mime_returns_image_jpeg(self):
        from toolbox.lib.drive_utils import get_ai_supported_mime
        self.assertEqual(get_ai_supported_mime('image/png'), 'image/jpeg')

    def test_unsupported_mime_returns_none(self):
        from toolbox.lib.drive_utils import get_ai_supported_mime
        self.assertIsNone(get_ai_supported_mime('audio/mpeg'))

    def test_text_truncated_to_cap(self):
        # LLMGateway checks token cap (by dividing by 4) and truncates prompt if too long.
        from toolbox.lib.llm_gateway import LLMGateway
        from toolbox.lib.providers.groq import GroqProvider

        gateway = LLMGateway()
        # Force the cap to be very small for testing (e.g. 5 tokens = 20 chars)
        gateway.config = {
            'tiers': {'automation': {'providers': [{'name': 'groq', 'model': 'test'}]}},
            'routes': {'automation': 'automation'},
            'budgets': {'daily_usd': 5.0, 'per_task_usd': 1.0},
            'token_caps': {'automation': 5},
            'thresholds': {'long_context_tokens': 100000}
        }

        captured = {}
        def fake_groq_analyze(self_inner, cb, mt, p):
            captured['prompt'] = p
            return '{"res":"ok"}', 10

        with patch('toolbox.lib.llm_gateway.quota_manager.get_total_usd_used', return_value=0.0), \
             patch('toolbox.lib.llm_gateway.quota_manager.record_llm_usage'), \
             patch.object(GroqProvider, 'analyze', fake_groq_analyze), \
             patch.object(GroqProvider, 'supports', return_value=True):
             
            # Send 100 characters
            gateway.call('automation', 'A' * 100)
        
        # Should be truncated to 5 tokens * 4 chars = 20 chars
        self.assertEqual(len(captured['prompt']), 20)

    def test_text_under_cap_not_truncated(self):
        from toolbox.lib.llm_gateway import LLMGateway
        from toolbox.lib.providers.groq import GroqProvider

        gateway = LLMGateway()
        # Cap is 500 tokens = 2000 chars
        gateway.config = {
            'tiers': {'automation': {'providers': [{'name': 'groq', 'model': 'test'}]}},
            'routes': {'automation': 'automation'},
            'budgets': {'daily_usd': 5.0, 'per_task_usd': 1.0},
            'token_caps': {'automation': 500},
            'thresholds': {'long_context_tokens': 100000}
        }

        captured = {}
        def fake_groq_analyze(self_inner, cb, mt, p):
            captured['prompt'] = p
            return '{"res":"ok"}', 10

        with patch('toolbox.lib.llm_gateway.quota_manager.get_total_usd_used', return_value=0.0), \
             patch('toolbox.lib.llm_gateway.quota_manager.record_llm_usage'), \
             patch.object(GroqProvider, 'analyze', fake_groq_analyze), \
             patch.object(GroqProvider, 'supports', return_value=True):
             
            # Send 100 characters
            prompt = 'A' * 100
            gateway.call('automation', prompt)
        
        # Should not be truncated
        self.assertEqual(len(captured['prompt']), 100)
        self.assertEqual(captured['prompt'], prompt)


if __name__ == '__main__':
    unittest.main()
