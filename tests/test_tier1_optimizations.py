"""
Tests for Tier 1 cost optimizations.
All tests are offline (no Gemini, Drive, or network calls).
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

    def _write_quota(self, tokens_used):
        state = {
            "date": date.today().isoformat(),
            "total_tokens_used": tokens_used,
            "daily_budget": self._qm.DAILY_BUDGET,
        }
        with open(self._qm.QUOTA_PATH, 'w') as f:
            json.dump(state, f)

    # --- is_budget_exhausted ---
    def test_budget_not_exhausted_when_empty(self):
        self.assertFalse(self._qm.is_budget_exhausted())

    def test_budget_exhausted_at_limit(self):
        self._write_quota(self._qm.DAILY_BUDGET)
        self.assertTrue(self._qm.is_budget_exhausted())

    def test_budget_not_exhausted_below_limit(self):
        self._write_quota(self._qm.DAILY_BUDGET - 1)
        self.assertFalse(self._qm.is_budget_exhausted())

    # --- sorter reservation ---
    def test_backfill_exhausted_when_within_reserved_band(self):
        # DAILY_BUDGET - SORTER_RESERVED tokens used → backfill should stop, sorter should not
        self._write_quota(self._qm.DAILY_BUDGET - self._qm.SORTER_RESERVED)
        self.assertTrue(self._qm.is_backfill_budget_exhausted())
        self.assertFalse(self._qm.is_budget_exhausted())

    def test_backfill_not_exhausted_with_room(self):
        self._write_quota(self._qm.DAILY_BUDGET - self._qm.SORTER_RESERVED - 1)
        self.assertFalse(self._qm.is_backfill_budget_exhausted())

    def test_backfill_remaining_never_negative(self):
        self._write_quota(self._qm.DAILY_BUDGET)  # fully exhausted
        self.assertEqual(self._qm.backfill_remaining(), 0)

    # --- log_cost ---
    def test_log_cost_creates_jsonl(self):
        self._qm.log_cost('sorter', 10, 5000)
        with open(self._qm.COST_LOG_PATH) as f:
            record = json.loads(f.readline())
        self.assertEqual(record['run_type'], 'sorter')
        self.assertEqual(record['files_processed'], 10)
        self.assertEqual(record['tokens_used'], 5000)
        self.assertAlmostEqual(record['cost_usd_est'], 5000 * 0.10 / 1_000_000, places=9)

    def test_log_cost_appends(self):
        self._qm.log_cost('sorter', 5, 1000)
        self._qm.log_cost('backfill', 20, 8000)
        with open(self._qm.COST_LOG_PATH) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])['run_type'], 'backfill')


# ---------------------------------------------------------------------------
# 3, 5, 6, 7 — File size limits and bytes logging in ai_engine
# (patch genai so we don't need the SDK; test the truncation/cap logic only)
# ---------------------------------------------------------------------------

class TestAiEngineFileSizeLimits(unittest.TestCase):
    """
    Tests for text/PDF truncation and max_output_tokens.
    We test get_ai_supported_mime directly (no network) and verify that
    analyze_with_gemini truncates content before calling generate_content.
    """

    def test_spreadsheet_mime_returns_text_plain(self):
        # Change #3: sheets now map to text/plain (was application/pdf)
        from toolbox.lib.ai_engine import get_ai_supported_mime
        result = get_ai_supported_mime('application/vnd.google-apps.spreadsheet')
        self.assertEqual(result, 'text/plain')

    def test_document_mime_returns_text_plain(self):
        from toolbox.lib.ai_engine import get_ai_supported_mime
        self.assertEqual(get_ai_supported_mime('application/vnd.google-apps.document'), 'text/plain')

    def test_pdf_mime_returns_application_pdf(self):
        from toolbox.lib.ai_engine import get_ai_supported_mime
        self.assertEqual(get_ai_supported_mime('application/pdf'), 'application/pdf')

    def test_image_mime_returns_image_jpeg(self):
        from toolbox.lib.ai_engine import get_ai_supported_mime
        self.assertEqual(get_ai_supported_mime('image/png'), 'image/jpeg')

    def test_unsupported_mime_returns_none(self):
        from toolbox.lib.ai_engine import get_ai_supported_mime
        self.assertIsNone(get_ai_supported_mime('audio/mpeg'))

    def _make_fake_response(self, text='{"doc_date":"2026-01-01","entity":"Test","folder_path":"01 - Second Brain","summary":"Test","confidence":"High"}'):
        resp = MagicMock()
        resp.text = text
        usage = MagicMock()
        usage.total_token_count = 100
        usage.prompt_token_count = 80
        usage.candidates_token_count = 20
        resp.usage_metadata = usage
        return resp

    def _call_analyze(self, content_bytes, mime_type, filename='test.pdf', folder_paths_str='01 - Second Brain'):
        """Call analyze_with_gemini with a mocked genai client."""
        from toolbox.lib import ai_engine
        captured = {}

        def fake_generate_content(model, contents, config=None):
            captured['content_part'] = contents[1]
            captured['config'] = config
            return self._make_fake_response()

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = fake_generate_content

        # Reset singleton so the mock is picked up cleanly
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}), \
             patch.object(ai_engine, '_client', None), \
             patch('google.genai.Client', return_value=fake_client):
            result, tokens = ai_engine.analyze_with_gemini(
                content_bytes, mime_type, filename, folder_paths_str
            )
        return result, tokens, captured

    def _sent_bytes(self, captured):
        """Extract raw bytes from the captured Part object (google-genai SDK stores at .inline_data.data)."""
        part = captured['content_part']
        return part.inline_data.data

    def test_text_truncated_to_10kb(self):
        # Change #5: 100KB → 10KB for text
        large_text = b'A' * (1024 * 50)  # 50KB
        result, tokens, captured = self._call_analyze(large_text, 'text/plain', 'big.txt')
        self.assertLessEqual(len(self._sent_bytes(captured)), 1024 * 10 + 1)

    def test_text_under_10kb_not_truncated(self):
        small_text = b'Hello world ' * 100  # ~1.2KB
        result, tokens, captured = self._call_analyze(small_text, 'text/plain', 'small.txt')
        self.assertEqual(len(self._sent_bytes(captured)), len(small_text))

    def test_pdf_truncated_to_200kb(self):
        # Change #4: PDFs capped at 200KB
        large_pdf = b'%PDF' + b'X' * (500 * 1024)  # 500KB
        result, tokens, captured = self._call_analyze(large_pdf, 'application/pdf', 'big.pdf')
        self.assertLessEqual(len(self._sent_bytes(captured)), 200 * 1024 + 1)

    def test_pdf_under_200kb_not_truncated(self):
        small_pdf = b'%PDF' + b'X' * (50 * 1024)  # 50KB
        result, tokens, captured = self._call_analyze(small_pdf, 'application/pdf', 'small.pdf')
        self.assertEqual(len(self._sent_bytes(captured)), len(small_pdf))

    def test_max_output_tokens_set(self):
        # Change #6: max_output_tokens=512 passed in config
        content = b'Hello'
        result, tokens, captured = self._call_analyze(content, 'text/plain', 'note.txt')
        cfg = captured.get('config')
        self.assertIsNotNone(cfg, "GenerateContentConfig not passed")
        self.assertEqual(cfg.max_output_tokens, 512)


# ---------------------------------------------------------------------------
# 8 — ID_TO_PATH reverse lookup
# ---------------------------------------------------------------------------

class TestIdToPath(unittest.TestCase):

    def test_id_to_path_is_inverse_of_path_to_id(self):
        from toolbox.lib.drive_utils import ID_TO_PATH, DRIVE_TREE
        path_to_id = DRIVE_TREE.get('path_to_id', {})
        if not path_to_id:
            self.skipTest("drive_tree.json not present; skip on dev machine")
        for path, fid in path_to_id.items():
            self.assertIn(fid, ID_TO_PATH)
            self.assertEqual(ID_TO_PATH[fid], path)

    def test_id_to_path_no_duplicate_ids(self):
        # Every ID should map to exactly one path
        from toolbox.lib.drive_utils import ID_TO_PATH, DRIVE_TREE
        path_to_id = DRIVE_TREE.get('path_to_id', {})
        if not path_to_id:
            self.skipTest("drive_tree.json not present")
        self.assertEqual(len(ID_TO_PATH), len(set(path_to_id.values())))


# ---------------------------------------------------------------------------
# 9 — Extra folder map caching in backfill state
# ---------------------------------------------------------------------------

class TestExtraFolderMapCache(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _make_state(self, extra_map=None, built_at=None):
        return {
            "pending": [],
            "completed_ids": [],
            "last_run": None,
            "total_processed": 0,
            "extra_folder_map": extra_map or {},
            "extra_map_built_at": built_at,
        }

    def test_fresh_state_triggers_build(self):
        """Empty extra_folder_map should call build_extra_folder_map."""
        from toolbox.services.drive_organizer import backfill
        state = self._make_state()
        fake_map = {"05 - Media": "id_media"}

        with patch.object(backfill, 'build_extra_folder_map', return_value=fake_map) as mock_build, \
             patch.object(backfill, 'save_state'):
            result = backfill._get_extra_folder_map(MagicMock(), state)

        mock_build.assert_called_once()
        self.assertEqual(result, fake_map)

    def test_fresh_cache_skips_build(self):
        """A cache built minutes ago should be returned without a Drive crawl."""
        from toolbox.services.drive_organizer import backfill
        recent = datetime.now(timezone.utc).isoformat()
        existing_map = {"05 - Media": "id_media", "09 - Archive": "id_arch"}
        state = self._make_state(extra_map=existing_map, built_at=recent)

        with patch.object(backfill, 'build_extra_folder_map') as mock_build:
            result = backfill._get_extra_folder_map(MagicMock(), state)

        mock_build.assert_not_called()
        self.assertEqual(result, existing_map)

    def test_stale_cache_triggers_rebuild(self):
        """A cache older than 24h should be rebuilt."""
        from toolbox.services.drive_organizer import backfill
        old_time = "2020-01-01T00:00:00+00:00"
        state = self._make_state(extra_map={"stale": "id"}, built_at=old_time)
        new_map = {"05 - Media": "id_media_new"}

        with patch.object(backfill, 'build_extra_folder_map', return_value=new_map) as mock_build, \
             patch.object(backfill, 'save_state'):
            result = backfill._get_extra_folder_map(MagicMock(), state)

        mock_build.assert_called_once()
        self.assertEqual(result, new_map)


if __name__ == '__main__':
    unittest.main(verbosity=2)
