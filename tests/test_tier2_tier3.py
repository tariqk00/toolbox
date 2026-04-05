"""
Regression tests for Tier 2 & 3 optimizations — all offline.

Covers:
- ai_engine: genai.Client singleton, image resize (Pillow)
- backfill: Drive Changes API delta queue (build_delta_queue)
- backfill: completed_ids removed from state
- backfill: --count-cached reads from local state

Run from repo root:
  python3 -m pytest toolbox/tests/test_tier2_tier3.py -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


# ---------------------------------------------------------------------------
# #11 — genai.Client singleton
# ---------------------------------------------------------------------------

class TestClientSingleton(unittest.TestCase):

    def test_same_client_returned_on_second_call(self):
        from toolbox.lib import ai_engine
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, '_client', None), \
             patch('google.genai.Client', return_value=MagicMock()) as mock_cls:
            c1 = ai_engine._get_client()
            c2 = ai_engine._get_client()
        self.assertIs(c1, c2)
        mock_cls.assert_called_once()  # constructed only once

    def test_client_uses_api_key(self):
        from toolbox.lib import ai_engine
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'test-api-key'), \
             patch.object(ai_engine, '_client', None), \
             patch('google.genai.Client', return_value=MagicMock()) as mock_cls:
            ai_engine._get_client()
        mock_cls.assert_called_once_with(api_key='test-api-key')


# ---------------------------------------------------------------------------
# #13 — Image resize with Pillow
# ---------------------------------------------------------------------------

class TestImageResize(unittest.TestCase):

    def _make_jpeg(self, width=2000, height=2000):
        """Create a real minimal JPEG in memory at the given size."""
        from PIL import Image as PILImage
        img = PILImage.new('RGB', (width, height), color=(128, 64, 32))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=90)
        return buf.getvalue()

    def _make_fake_response(self):
        resp = MagicMock()
        resp.text = '{"doc_date":"2026-01-01","entity":"Test","folder_path":"01 - Second Brain","summary":"T","confidence":"High"}'
        usage = MagicMock()
        usage.total_token_count = 50
        usage.prompt_token_count = 40
        usage.candidates_token_count = 10
        resp.usage_metadata = usage
        return resp

    def test_large_image_resized_before_send(self):
        from toolbox.lib import ai_engine
        large_jpeg = self._make_jpeg(2000, 2000)
        original_size = len(large_jpeg)

        captured = {}
        def fake_generate(model, contents, config=None):
            captured['data'] = contents[1].inline_data.data
            return self._make_fake_response()

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = fake_generate

        with patch.object(ai_engine, 'GEMINI_API_KEY', 'k'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}), \
             patch.object(ai_engine, '_client', None), \
             patch('google.genai.Client', return_value=fake_client):
            ai_engine.analyze_with_gemini(large_jpeg, 'image/jpeg', 'photo.jpg', 'paths')

        sent_size = len(captured['data'])
        self.assertLess(sent_size, original_size,
                        "Large image should be smaller after resize")

    def test_pillow_unavailable_falls_back_gracefully(self):
        """If Pillow isn't importable, the function should still work."""
        from toolbox.lib import ai_engine
        small_jpeg = self._make_jpeg(100, 100)

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = self._make_fake_response()

        with patch.object(ai_engine, 'GEMINI_API_KEY', 'k'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}), \
             patch.object(ai_engine, '_client', None), \
             patch.object(ai_engine, '_PILLOW_AVAILABLE', False), \
             patch('google.genai.Client', return_value=fake_client):
            result, tokens = ai_engine.analyze_with_gemini(
                small_jpeg, 'image/jpeg', 'photo.jpg', 'paths'
            )
        self.assertEqual(result['confidence'], 'High')


# ---------------------------------------------------------------------------
# #12 — Drive Changes API: build_delta_queue
# ---------------------------------------------------------------------------

class TestBuildDeltaQueue(unittest.TestCase):

    def _make_service(self, start_token='tok0', change_pages=None):
        """Build a mock Drive service for changes API calls."""
        svc = MagicMock()
        svc.changes().getStartPageToken().execute.return_value = {'startPageToken': start_token}

        pages = change_pages or [{'changes': [], 'newStartPageToken': 'tok1'}]
        svc.changes().list().execute.side_effect = pages
        return svc

    def _base_state(self, token=None, extra_map=None):
        return {
            'pending': [],
            'last_run': None,
            'total_processed': 0,
            'changes_page_token': token,
            'extra_folder_map': extra_map or {},
            'extra_map_built_at': None,
        }

    def test_no_token_initialises_and_returns_none(self):
        """First call: records start token, signals full crawl needed."""
        from toolbox.services.drive_organizer import backfill
        state = self._base_state(token=None)
        svc = self._make_service(start_token='initial_token')

        with patch.object(backfill, 'save_state'):
            result = backfill.build_delta_queue(svc, state)

        self.assertIsNone(result)
        self.assertEqual(state['changes_page_token'], 'initial_token')

    def test_token_present_calls_changes_list(self):
        """With a token, changes().list() should be called."""
        from toolbox.services.drive_organizer import backfill
        state = self._base_state(token='existing_token')

        svc = MagicMock()
        svc.changes().list().execute.return_value = {
            'changes': [], 'newStartPageToken': 'tok_next'
        }

        with patch.object(backfill, 'CACHE_PATH', _empty_cache()), \
             patch.object(backfill, 'save_state'):
            result = backfill.build_delta_queue(svc, state)

        self.assertIsNotNone(result)
        self.assertEqual(result, [])

    def test_new_file_in_tracked_folder_added_to_pending(self):
        """A new file in a tracked folder should appear in the returned list."""
        from toolbox.services.drive_organizer import backfill
        from toolbox.lib.drive_utils import ID_TO_PATH

        # Pick a real folder ID from the drive tree
        if not ID_TO_PATH:
            self.skipTest("drive_tree.json not present")

        tracked_id = next(iter(ID_TO_PATH.keys()))  # first folder ID
        state = self._base_state(token='tok')

        change = {
            'removed': False,
            'file': {
                'id': 'new_file_id',
                'name': 'New Document.pdf',
                'mimeType': 'application/pdf',
                'createdTime': '2026-04-01T10:00:00Z',
                'parents': [tracked_id],
            }
        }
        svc = MagicMock()
        svc.changes().list().execute.return_value = {
            'changes': [change], 'newStartPageToken': 'tok2'
        }

        with patch.object(backfill, 'CACHE_PATH', _empty_cache()), \
             patch.object(backfill, 'save_state'):
            result = backfill.build_delta_queue(svc, state)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'new_file_id')
        self.assertEqual(result[0]['folder_id'], tracked_id)

    def test_already_cached_file_skipped(self):
        """Files already in gemini_cache.json should not appear in delta queue."""
        from toolbox.services.drive_organizer import backfill
        from toolbox.lib.drive_utils import ID_TO_PATH
        if not ID_TO_PATH:
            self.skipTest("drive_tree.json not present")

        tracked_id = next(iter(ID_TO_PATH.keys()))
        state = self._base_state(token='tok')

        change = {
            'removed': False,
            'file': {
                'id': 'cached_file_id',
                'name': 'Already Done.pdf',
                'mimeType': 'application/pdf',
                'createdTime': '2026-01-01T00:00:00Z',
                'parents': [tracked_id],
            }
        }
        svc = MagicMock()
        svc.changes().list().execute.return_value = {
            'changes': [change], 'newStartPageToken': 'tok2'
        }

        cache_path = _cache_with({'cached_file_id': {'entity': 'Cached'}})
        with patch.object(backfill, 'CACHE_PATH', cache_path), \
             patch.object(backfill, 'save_state'):
            result = backfill.build_delta_queue(svc, state)

        self.assertEqual(result, [])

    def test_removed_change_ignored(self):
        """Files marked removed in a change should not be queued."""
        from toolbox.services.drive_organizer import backfill
        from toolbox.lib.drive_utils import ID_TO_PATH
        if not ID_TO_PATH:
            self.skipTest("drive_tree.json not present")

        tracked_id = next(iter(ID_TO_PATH.keys()))
        state = self._base_state(token='tok')

        change = {'removed': True, 'file': {'id': 'deleted_id', 'parents': [tracked_id],
                  'name': 'Gone.pdf', 'mimeType': 'application/pdf', 'createdTime': ''}}
        svc = MagicMock()
        svc.changes().list().execute.return_value = {
            'changes': [change], 'newStartPageToken': 'tok2'
        }

        with patch.object(backfill, 'CACHE_PATH', _empty_cache()), \
             patch.object(backfill, 'save_state'):
            result = backfill.build_delta_queue(svc, state)

        self.assertEqual(result, [])

    def test_file_outside_tracked_folders_ignored(self):
        """Changes to files not in tracked folders should be skipped."""
        from toolbox.services.drive_organizer import backfill
        state = self._base_state(token='tok')

        change = {
            'removed': False,
            'file': {
                'id': 'external_file',
                'name': 'Random.pdf',
                'mimeType': 'application/pdf',
                'createdTime': '',
                'parents': ['some_untracked_folder_id'],
            }
        }
        svc = MagicMock()
        svc.changes().list().execute.return_value = {
            'changes': [change], 'newStartPageToken': 'tok2'
        }

        with patch.object(backfill, 'CACHE_PATH', _empty_cache()), \
             patch.object(backfill, 'save_state'):
            result = backfill.build_delta_queue(svc, state)

        self.assertEqual(result, [])

    def test_page_token_updated_after_consuming_changes(self):
        """state['changes_page_token'] should be updated to newStartPageToken."""
        from toolbox.services.drive_organizer import backfill
        state = self._base_state(token='old_token')

        svc = MagicMock()
        svc.changes().list().execute.return_value = {
            'changes': [], 'newStartPageToken': 'new_token'
        }

        with patch.object(backfill, 'CACHE_PATH', _empty_cache()), \
             patch.object(backfill, 'save_state'):
            backfill.build_delta_queue(svc, state)

        self.assertEqual(state['changes_page_token'], 'new_token')


# ---------------------------------------------------------------------------
# #14 — completed_ids removed from state
# ---------------------------------------------------------------------------

class TestCompletedIdsRemoved(unittest.TestCase):

    def test_default_state_has_no_completed_ids(self):
        from toolbox.services.drive_organizer.backfill import load_state
        with tempfile.TemporaryDirectory() as tmp:
            import toolbox.services.drive_organizer.backfill as bf
            orig = bf.STATE_PATH
            bf.STATE_PATH = os.path.join(tmp, 'backfill_state.json')
            try:
                state = bf.load_state()
                self.assertNotIn('completed_ids', state)
            finally:
                bf.STATE_PATH = orig

    def test_run_does_not_append_completed_ids(self):
        """Verify no reference to completed_ids in run() processing path."""
        import inspect
        import toolbox.services.drive_organizer.backfill as bf
        src = inspect.getsource(bf.run)
        self.assertNotIn("completed_ids", src)


# ---------------------------------------------------------------------------
# #15 — --count-cached reads from local state, no Drive call
# ---------------------------------------------------------------------------

class TestCountCached(unittest.TestCase):

    def test_count_cached_prints_queue_size(self):
        import toolbox.services.drive_organizer.backfill as bf
        state = {
            'pending': [{'id': 'f1'}, {'id': 'f2'}, {'id': 'f3'}],
            'total_processed': 42,
        }
        args = MagicMock()
        args.count_cached = True
        args.count_only   = False
        args.dry_run      = False
        args.limit        = 0

        with patch.object(bf, 'load_state', return_value=state), \
             patch.object(bf, 'get_drive_service') as mock_svc, \
             patch('builtins.print') as mock_print:
            bf.run(args)

        mock_svc.assert_not_called()  # no Drive API
        output = ' '.join(str(c) for c in mock_print.call_args_list)
        self.assertIn('3', output)   # 3 pending
        self.assertIn('42', output)  # 42 processed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_cache():
    """Write an empty gemini_cache.json to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump({}, f)
    f.close()
    return f.name


def _cache_with(data: dict):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    json.dump(data, f)
    f.close()
    return f.name


if __name__ == '__main__':
    unittest.main(verbosity=2)
