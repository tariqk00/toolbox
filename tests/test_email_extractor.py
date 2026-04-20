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


if __name__ == '__main__':
    unittest.main()
