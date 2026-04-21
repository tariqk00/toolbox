"""
Tests for email_extractor writers.py — Drive read/write operations.
All tests are offline; google.googleapiclient and Drive service are mocked.

Covers:
  - _resolve_path: single and multi-level path resolution, folder creation
  - append_to_memory: file exists (append) and file doesn't exist (create)
  - update_in_memory: text found (replace+upload), text absent (no upload), file missing
"""
import io
import unittest
from unittest.mock import MagicMock, patch, call


def _make_service(folder_ids=None, file_id=None, file_content=b''):
    """
    Build a mock Drive service.

    folder_ids: dict mapping (parent_id, name) → folder_id returned by files().list()
    file_id: if set, _get_file_in_folder returns this ID; else None (new file)
    file_content: bytes returned by files().get_media().execute()
    """
    folder_ids = folder_ids or {}
    service = MagicMock()

    def files_list_side_effect(q=None, fields=None):
        execute_mock = MagicMock()
        # Detect folder lookup vs file lookup by presence of mimeType in query
        if 'mimeType' in (q or ''):
            # Folder lookup — extract name and parent from query string
            # q = "'<parent>' in parents and name = '<name>' and mimeType=... and trashed = false"
            import re
            parent_match = re.search(r"'([^']+)' in parents", q)
            name_match = re.search(r"name = '([^']+)'", q)
            parent = parent_match.group(1) if parent_match else None
            name = name_match.group(1) if name_match else None
            fid = folder_ids.get((parent, name))
            execute_mock.execute.return_value = {'files': [{'id': fid}] if fid else []}
        else:
            # File lookup
            execute_mock.execute.return_value = {'files': [{'id': file_id}] if file_id else []}
        return execute_mock

    service.files().list.side_effect = files_list_side_effect

    # files().create().execute() returns {'id': 'new_id'}
    service.files().create.return_value.execute.return_value = {'id': 'created_id'}

    # files().get_media().execute() returns file_content
    service.files().get_media.return_value.execute.return_value = file_content

    # files().update() — just needs to not error
    service.files().update.return_value.execute.return_value = {}

    return service


class TestResolvePath(unittest.TestCase):

    def setUp(self):
        # Clear folder cache before each test
        from toolbox.services.email_extractor import writers
        writers._folder_cache.clear()

    def test_single_level_found(self):
        """Root → 'Folder' resolves using existing folder."""
        from toolbox.services.email_extractor import writers
        svc = _make_service(folder_ids={('root', '01 - Second Brain'): 'id_sb'})
        with patch.object(writers, 'get_drive_service', return_value=svc):
            fid = writers._resolve_path(svc, '01 - Second Brain')
        self.assertEqual(fid, 'id_sb')

    def test_multi_level_path_chains(self):
        """Root → A → B → C — each step uses previous result as parent."""
        from toolbox.services.email_extractor import writers
        folder_ids = {
            ('root', '01 - Second Brain'): 'id_sb',
            ('id_sb', 'Memory'): 'id_mem',
            ('id_mem', 'Orders'): 'id_orders',
        }
        svc = _make_service(folder_ids=folder_ids)
        fid = writers._resolve_path(svc, '01 - Second Brain/Memory/Orders')
        self.assertEqual(fid, 'id_orders')

    def test_missing_folder_creates(self):
        """If folder not found, create is called and returned ID is used."""
        from toolbox.services.email_extractor import writers
        svc = _make_service(folder_ids={})  # no folders found — triggers create
        fid = writers._resolve_path(svc, '01 - Second Brain')
        # create was called; returns 'created_id'
        self.assertEqual(fid, 'created_id')
        svc.files().create.assert_called()

    def test_cache_prevents_second_lookup(self):
        """Repeated resolve of same path uses cache, no extra Drive calls."""
        from toolbox.services.email_extractor import writers
        folder_ids = {('root', 'Inbox'): 'id_inbox'}
        svc = _make_service(folder_ids=folder_ids)
        writers._resolve_path(svc, 'Inbox')
        list_call_count = svc.files().list.call_count
        writers._resolve_path(svc, 'Inbox')  # second call — should use cache
        self.assertEqual(svc.files().list.call_count, list_call_count)


class TestAppendToMemory(unittest.TestCase):

    def setUp(self):
        from toolbox.services.email_extractor import writers
        writers._folder_cache.clear()

    def _run_append(self, category, filename, new_content, file_id=None, existing_content=b''):
        from toolbox.services.email_extractor import writers
        folder_ids = {
            ('root', '01 - Second Brain'): 'id_sb',
            ('id_sb', 'Memory'): 'id_mem',
            ('id_mem', category): 'id_cat',
        }
        svc = _make_service(folder_ids=folder_ids, file_id=file_id, file_content=existing_content)
        with patch.object(writers, 'get_drive_service', return_value=svc):
            writers.append_to_memory(category, filename, new_content)
        return svc

    def test_new_file_created_when_not_found(self):
        svc = self._run_append('Orders', 'Amazon.md', '## entry', file_id=None)
        # create should have been called
        svc.files().create.assert_called()
        # get_media should NOT have been called (no existing file)
        svc.files().get_media.assert_not_called()

    def test_existing_file_appended(self):
        existing = b'## old entry\n'
        svc = self._run_append('Orders', 'Amazon.md', '## new entry',
                               file_id='id_existing', existing_content=existing)
        # get_media should have been called
        svc.files().get_media.assert_called()
        # update should have been called (not create)
        svc.files().update.assert_called()
        svc.files().create.assert_not_called()

    def test_append_separator(self):
        """Content is separated from existing text by double newline."""
        existing = b'## old\n'

        from toolbox.services.email_extractor import writers

        folder_ids = {
            ('root', '01 - Second Brain'): 'id_sb',
            ('id_sb', 'Memory'): 'id_mem',
            ('id_mem', 'Receipts'): 'id_rec',
        }
        svc = _make_service(folder_ids=folder_ids, file_id='id_file', file_content=existing)

        with patch.object(writers, 'get_drive_service', return_value=svc):
            writers.append_to_memory('Receipts', 'Toyota.md', '## new entry')

        # Inspect the media_body that was passed to update()
        call_kwargs = svc.files().update.call_args.kwargs
        media_body = call_kwargs['media_body']
        media_body._fd.seek(0)
        full = media_body._fd.read().decode()
        self.assertIn('\n\n## new entry', full)
        self.assertTrue(full.startswith('## old'))

    def test_no_category_uses_memory_root(self):
        """category=None writes directly to Memory/, not a subfolder."""
        from toolbox.services.email_extractor import writers
        folder_ids = {
            ('root', '01 - Second Brain'): 'id_sb',
            ('id_sb', 'Memory'): 'id_mem',
        }
        svc = _make_service(folder_ids=folder_ids, file_id=None)
        with patch.object(writers, 'get_drive_service', return_value=svc):
            writers.append_to_memory(None, 'Travel.md', '## trip')
        svc.files().create.assert_called()


class TestUpdateInMemory(unittest.TestCase):

    def setUp(self):
        from toolbox.services.email_extractor import writers
        writers._folder_cache.clear()

    def _run_update(self, category, filename, old_text, new_text, file_id=None, existing_content=b''):
        from toolbox.services.email_extractor import writers
        folder_ids = {
            ('root', '01 - Second Brain'): 'id_sb',
            ('id_sb', 'Memory'): 'id_mem',
            ('id_mem', category): 'id_cat',
        }
        svc = _make_service(folder_ids=folder_ids, file_id=file_id, file_content=existing_content)
        with patch.object(writers, 'get_drive_service', return_value=svc):
            result = writers.update_in_memory(category, filename, old_text, new_text)
        return result, svc

    def test_text_found_returns_true_and_uploads(self):
        existing = b'Status: [Pending]\nDetails: something'
        result, svc = self._run_update(
            'Orders', 'Amazon.md', 'Status: [Pending]', 'Status: [Delivered]',
            file_id='id_file', existing_content=existing
        )
        self.assertTrue(result)
        svc.files().update.assert_called()

    def test_text_not_found_returns_false_no_upload(self):
        existing = b'Status: [Delivered]\n'
        result, svc = self._run_update(
            'Orders', 'Amazon.md', 'Status: [Pending]', 'Status: [Delivered]',
            file_id='id_file', existing_content=existing
        )
        self.assertFalse(result)
        svc.files().update.assert_not_called()

    def test_file_not_found_returns_false(self):
        result, svc = self._run_update(
            'Orders', 'Nonexistent.md', 'old', 'new', file_id=None
        )
        self.assertFalse(result)
        svc.files().get_media.assert_not_called()

    def test_replacement_is_first_occurrence_only(self):
        """update_in_memory replaces only the first occurrence."""
        existing = b'## A\nfoo\n---\n## B\nfoo\n---\n'

        from toolbox.services.email_extractor import writers

        folder_ids = {
            ('root', '01 - Second Brain'): 'id_sb',
            ('id_sb', 'Memory'): 'id_mem',
            ('id_mem', 'Trips'): 'id_trips',
        }
        svc = _make_service(folder_ids=folder_ids, file_id='id_file', file_content=existing)

        with patch.object(writers, 'get_drive_service', return_value=svc):
            writers.update_in_memory('Trips', 'Travel.md', 'foo', 'bar')

        call_kwargs = svc.files().update.call_args.kwargs
        media_body = call_kwargs['media_body']
        media_body._fd.seek(0)
        content = media_body._fd.read().decode()
        self.assertEqual(content.count('bar'), 1)  # only one replacement
        self.assertEqual(content.count('foo'), 1)  # second foo still present


class TestBlockExists(unittest.TestCase):

    def test_match_with_confirmation(self):
        from toolbox.services.email_extractor.writers import block_exists
        content = (
            '## 2026-04-15 — Flight\n**Vendor:** Delta\n**Confirmation:** HXXKJD\n---\n'
            '## 2026-04-20 — Hotel\n**Vendor:** Marriott\n---\n'
        )
        self.assertTrue(block_exists(content, '2026-04-15', 'HXXKJD'))

    def test_no_match_different_date(self):
        from toolbox.services.email_extractor.writers import block_exists
        content = '## 2026-04-15 — Flight\n**Confirmation:** HXXKJD\n---\n'
        self.assertFalse(block_exists(content, '2026-04-20', 'HXXKJD'))

    def test_no_match_missing_identifier(self):
        from toolbox.services.email_extractor.writers import block_exists
        content = '## 2026-04-15 — Flight\n**Vendor:** Delta\n---\n'
        self.assertFalse(block_exists(content, '2026-04-15', 'HXXKJD'))

    def test_match_multiple_identifiers(self):
        from toolbox.services.email_extractor.writers import block_exists
        content = '## 2026-04-15 — Flight\n**Vendor:** Delta\n---\n'
        self.assertTrue(block_exists(content, '2026-04-15', 'Delta', 'Flight'))

    def test_empty_content_returns_false(self):
        from toolbox.services.email_extractor.writers import block_exists
        self.assertFalse(block_exists('', '2026-04-15', 'Delta'))

    def test_empty_identifier_ignored(self):
        """Empty identifiers are skipped — only date match required."""
        from toolbox.services.email_extractor.writers import block_exists
        content = '## 2026-04-15 — Flight\n**Vendor:** Delta\n---\n'
        self.assertTrue(block_exists(content, '2026-04-15', ''))

    def test_second_block_matches(self):
        """Match can be in any block, not just the first."""
        from toolbox.services.email_extractor.writers import block_exists
        content = (
            '## 2026-04-10 — Hotel\n**Vendor:** Marriott\n---\n'
            '## 2026-04-15 — Flight\n**Vendor:** Delta\n**Confirmation:** HXXKJD\n---\n'
        )
        self.assertTrue(block_exists(content, '2026-04-15', 'HXXKJD'))
        self.assertFalse(block_exists(content, '2026-04-10', 'HXXKJD'))


class TestTripsDedup(unittest.TestCase):

    def _run_trip(self, email, state=None, existing_content=''):
        from toolbox.services.email_extractor.categories import trips
        from toolbox.services.email_extractor import writers

        if state is None:
            state = {}

        appended = []

        def fake_append(category, filename, content):
            appended.append(content)

        with patch.object(writers, 'get_drive_service'), \
             patch.object(trips, 'append_to_memory', fake_append), \
             patch.object(trips, 'update_in_memory', return_value=True), \
             patch.object(trips, 'get_memory_content', return_value=existing_content):
            result = trips.process(email, state)

        return result, appended, state

    def _make_email(self, vendor, subject, plain='', date='2026-04-15'):
        return {'vendor': vendor, 'subject': subject, 'plain': plain, 'date': date,
                'html': None, 'id': f'msg_{vendor}_{date}'}

    def test_first_email_creates_entry(self):
        email = self._make_email('Delta', 'Your flight confirmation HXXKJD', plain='')
        result, appended, state = self._run_trip(email)
        self.assertIsNotNone(result)
        self.assertEqual(len(appended), 1)
        self.assertIn('HXXKJD', appended[0])

    def test_same_confirmation_second_email_no_new_append(self):
        """Same confirmation on a second run (state already set) → no new entry."""
        email = self._make_email('Delta', 'Your flight confirmation HXXKJD')
        state = {'trip_confirmations': {
            'HXXKJD': {
                'vendor': 'Delta', 'status': 'Confirmed',
                'status_line': '**Status:** [Confirmed] 2026-04-15',
                'date': '2026-04-15', 'destination': '',
            }
        }}
        result, appended, _ = self._run_trip(email, state=state)
        self.assertEqual(len(appended), 0, "Should not append when status unchanged")

    def test_no_confirmation_uses_fallback_key(self):
        """Without a confirmation number the state key is vendor:type:YYYY-MM."""
        email = self._make_email('Delta', 'Time to check in for your flight')
        _, _, state = self._run_trip(email)
        # State should have an entry keyed by vendor:type:YYYY-MM
        keys = list(state.get('trip_confirmations', {}).keys())
        self.assertEqual(len(keys), 1)
        self.assertIn('Delta:Flight:2026-04', keys[0])

    def test_content_based_dedup_skips_duplicate(self):
        """If block already in file and state was reset, no new append."""
        existing = (
            '## 2026-04-15 — Flight\n'
            '**Vendor:** Delta\n'
            '**Status:** [Confirmed] 2026-04-15\n'
            '**Confirmation:** HXXKJD\n---\n'
        )
        email = self._make_email('Delta', 'Your flight confirmation HXXKJD')
        result, appended, _ = self._run_trip(email, existing_content=existing)
        self.assertEqual(len(appended), 0, "Content-based dedup should skip duplicate")
        self.assertIsNone(result)

    def test_travel_date_extracted_for_flight(self):
        """Departure date from email body is written as Travel date field."""
        plain = 'Departs May 15, 2026 at 07:30 from JFK'
        email = self._make_email('Delta', 'Flight confirmation HXXKJD', plain=plain)
        _, appended, _ = self._run_trip(email)
        self.assertTrue(any('Travel date' in a for a in appended),
                        "Expected Travel date field in entry")


class TestCarrierExtraction(unittest.TestCase):

    def test_fedex_detected(self):
        from toolbox.services.email_extractor.categories.orders import _extract_carrier
        self.assertEqual(_extract_carrier('Your FedEx package is on its way'), 'FedEx')

    def test_ups_detected(self):
        from toolbox.services.email_extractor.categories.orders import _extract_carrier
        self.assertEqual(_extract_carrier('Shipped via UPS Ground'), 'UPS')

    def test_usps_detected(self):
        from toolbox.services.email_extractor.categories.orders import _extract_carrier
        self.assertEqual(_extract_carrier('Delivered by USPS'), 'USPS')

    def test_dhl_detected(self):
        from toolbox.services.email_extractor.categories.orders import _extract_carrier
        self.assertEqual(_extract_carrier('DHL Express shipment'), 'DHL')

    def test_amazon_logistics_detected(self):
        from toolbox.services.email_extractor.categories.orders import _extract_carrier
        self.assertEqual(_extract_carrier('amazon logistics is delivering your package'), 'Amazon')

    def test_unknown_returns_empty(self):
        from toolbox.services.email_extractor.categories.orders import _extract_carrier
        self.assertEqual(_extract_carrier('Your package has shipped'), '')


if __name__ == '__main__':
    unittest.main()
