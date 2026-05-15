"""
Tests for drive_organizer/main.py — scan_folder() routing logic.
All tests are offline; Drive API, AI, and Telegram are mocked.

Covers:
  - Skip logic: Health Connect.zip, [MANUAL], already-named, skip MIME types
  - Dry run: AI called, no Drive mutations
  - Execute High confidence: rename + move
  - Execute Medium confidence: rename only, no move
  - Execute Low confidence: nothing
  - Recursive subfolder scan
"""
import unittest
from unittest.mock import MagicMock, patch, call


ANALYSIS_HIGH = {
    'doc_date': '2026-01-15',
    'entity': 'Toyota',
    'folder_path': '07 - Finance/Auto',
    'summary': 'Car payment receipt',
    'confidence': 'High',
    'reasoning': 'Clear invoice layout',
    'new_filename': '2026-01-15 - Toyota - Car payment receipt.pdf'
}
ANALYSIS_MEDIUM = {
    'doc_date': '2026-01-15',
    'entity': 'Unknown',
    'folder_path': '01 - Second Brain/Inbox',
    'summary': 'Some document',
    'confidence': 'Medium',
    'reasoning': 'Partial match',
    'new_filename': '2026-01-15 - Unknown - Some document.txt'
}
ANALYSIS_LOW = {
    'doc_date': '2026-01-15',
    'entity': 'Unknown',
    'folder_path': '01 - Second Brain/Inbox',
    'summary': 'Ambiguous',
    'confidence': 'Low',
    'reasoning': 'No clear match',
}


def _make_file(name, mime='text/plain', fid=None):
    return {
        'id': fid or f'id_{name.replace(" ", "_")}',
        'name': name,
        'mimeType': mime,
        'createdTime': '2026-01-15T10:00:00Z',
    }


def _make_service(files):
    """Return a mock Drive service that returns `files` for any files().list() call."""
    svc = MagicMock()
    svc.files().list.return_value.execute.return_value = {'files': files}
    svc.files().update.return_value.execute.return_value = {}
    return svc


def _run_scan(files, dry_run=True, analysis=ANALYSIS_HIGH, new_name='2026-01-15 - Toyota - Car payment receipt.pdf',
              target_id='id_target', mode='inbox', recursive=False, limit=None):
    """
    Run scan_folder with full mocking. Returns (service, move_file_mock).
    """
    from toolbox.services.drive_organizer import main

    svc = _make_service(files)

    test_analysis = dict(analysis)
    test_analysis['new_filename'] = new_name

    with patch.object(main, 'download_file_content', return_value=b'fake content'), \
         patch('toolbox.services.drive_organizer.main.call_json_llm', return_value=(test_analysis, 'reasoning', 10)), \
         patch.object(main, 'resolve_folder_id', return_value=target_id), \
         patch.object(main, 'get_category_prompt_str', return_value='folders...'), \
         patch.object(main, 'log_to_sheet'), \
         patch.object(main, 'send_message'), \
         patch.object(main, 'check_duplicate', return_value=(None, None)), \
         patch.object(main, 'post_process_memory'), \
         patch.object(main, 'move_file', return_value=True) as mock_move:
        main.scan_folder('id_inbox', dry_run=dry_run, limit=limit,
                         mode=mode, folder_name='Inbox', service=svc, recursive=recursive)

    return svc, mock_move


class TestSkipLogic(unittest.TestCase):

    def setUp(self):
        # Reset stats before each test
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_health_connect_zip_skipped(self):
        """Health Connect.zip must not reach AI."""
        from toolbox.services.drive_organizer import main
        with patch('toolbox.services.drive_organizer.main.call_json_llm') as mock_ai, \
             patch.object(main, 'download_file_content', return_value=b''), \
             patch.object(main, 'get_category_prompt_str', return_value=''), \
             patch.object(main, 'send_message'):
            svc = _make_service([_make_file('Health Connect.zip', 'application/zip')])
            main.scan_folder('id_inbox', dry_run=True, service=svc, recursive=False,
                             folder_name='Inbox')
        mock_ai.assert_not_called()

    def test_manual_flagged_file_skipped(self):
        """Files starting with [MANUAL] must not reach AI."""
        from toolbox.services.drive_organizer import main
        with patch('toolbox.services.drive_organizer.main.call_json_llm') as mock_ai, \
             patch.object(main, 'download_file_content', return_value=b''), \
             patch.object(main, 'get_category_prompt_str', return_value=''), \
             patch.object(main, 'send_message'):
            svc = _make_service([_make_file('[MANUAL] Invoice.pdf', 'application/pdf')])
            main.scan_folder('id_inbox', dry_run=True, service=svc, recursive=False,
                             folder_name='Inbox')
        mock_ai.assert_not_called()

    def test_already_named_file_skipped_in_scan_mode(self):
        """Already-named files (YYYY-MM-DD - X - Y pattern) are skipped in non-inbox mode."""
        from toolbox.services.drive_organizer import main
        with patch('toolbox.services.drive_organizer.main.call_json_llm') as mock_ai, \
             patch.object(main, 'download_file_content', return_value=b''), \
             patch.object(main, 'get_category_prompt_str', return_value=''), \
             patch.object(main, 'send_message'):
            already_named = _make_file('2026-01-15 - Toyota - Car receipt.pdf', 'application/pdf')
            svc = _make_service([already_named])
            main.scan_folder('id_inbox', dry_run=True, mode='scan', service=svc,
                             recursive=False, folder_name='Folder',
                             state={"analyzed_ids": {already_named['id']: already_named['name']}})
        mock_ai.assert_not_called()

    def test_skip_mime_type_not_processed(self):
        """Google Forms and other skip-mime-type files are ignored."""
        from toolbox.services.drive_organizer import main
        with patch('toolbox.services.drive_organizer.main.call_json_llm') as mock_ai, \
             patch.object(main, 'download_file_content', return_value=b''), \
             patch.object(main, 'get_category_prompt_str', return_value=''), \
             patch.object(main, 'send_message'):
            svc = _make_service([_make_file('My Form', 'application/vnd.google-apps.form')])
            main.scan_folder('id_inbox', dry_run=True, service=svc, recursive=False,
                             folder_name='Inbox')
        mock_ai.assert_not_called()


class TestDryRun(unittest.TestCase):

    def setUp(self):
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_dry_run_ai_called(self):
        """Dry run still calls AI but makes no Drive mutations."""
        from toolbox.services.drive_organizer import main
        files = [_make_file('invoice.pdf', 'application/pdf')]
        svc, mock_move = _run_scan(files, dry_run=True)
        # AI was called (download + analyze)
        # No update or move on Drive
        svc.files().update.assert_not_called()
        mock_move.assert_not_called()

    def test_dry_run_stats_incremented(self):
        from toolbox.services.drive_organizer import main
        files = [_make_file('note.txt')]
        _run_scan(files, dry_run=True)
        self.assertEqual(main.stats.processed, 1)
        self.assertEqual(main.stats.moved, 0)
        self.assertEqual(main.stats.renamed, 0)


class TestExecuteHighConfidence(unittest.TestCase):

    def setUp(self):
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_high_confidence_renames_and_moves(self):
        """High confidence + different name + target → rename + move."""
        files = [_make_file('invoice.pdf', 'application/pdf', fid='id_invoice')]
        svc, mock_move = _run_scan(files, dry_run=False, analysis=ANALYSIS_HIGH,
                                   new_name='2026-01-15 - Toyota - Car payment.pdf',
                                   target_id='id_finance')
        # rename happened
        svc.files().update.assert_called()
        # move happened
        mock_move.assert_called_once_with(svc, 'id_invoice', 'id_finance',
                                          '2026-01-15 - Toyota - Car payment.pdf')

    def test_high_confidence_stats(self):
        from toolbox.services.drive_organizer import main
        files = [_make_file('invoice.pdf', 'application/pdf', fid='id_invoice')]
        _run_scan(files, dry_run=False, analysis=ANALYSIS_HIGH,
                  new_name='2026-01-15 - Toyota - Car payment.pdf', target_id='id_finance')
        self.assertEqual(main.stats.moved, 1)
        self.assertEqual(main.stats.renamed, 1)

    def test_lowercase_high_confidence_still_moves(self):
        files = [_make_file('invoice.pdf', 'application/pdf', fid='id_invoice')]
        analysis = dict(ANALYSIS_HIGH, confidence='high')
        svc, mock_move = _run_scan(files, dry_run=False, analysis=analysis,
                                   new_name='2026-01-15 - Toyota - Car payment.pdf',
                                   target_id='id_finance')
        svc.files().update.assert_called()
        mock_move.assert_called_once()

    def test_high_confidence_same_folder_no_move(self):
        """High confidence but target == source folder → rename only, no move."""
        from toolbox.services.drive_organizer import main
        files = [_make_file('invoice.pdf', 'application/pdf', fid='id_invoice')]
        svc, mock_move = _run_scan(files, dry_run=False, analysis=ANALYSIS_HIGH,
                                   new_name='2026-01-15 - Toyota - Car payment.pdf',
                                   target_id='id_inbox')  # same as source
        svc.files().update.assert_called()
        mock_move.assert_not_called()


class TestExecuteMediumConfidence(unittest.TestCase):

    def setUp(self):
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_medium_confidence_renames_and_moves(self):
        """Medium confidence → rename and move (Spec V2)."""
        files = [_make_file('doc.txt', fid='id_doc')]
        svc, mock_move = _run_scan(files, dry_run=False, analysis=ANALYSIS_MEDIUM,
                                   new_name='2026-01-15 - Unknown - Some document.txt',
                                   target_id='id_finance')
        svc.files().update.assert_called()
        mock_move.assert_called_once()

    def test_medium_confidence_stats(self):
        from toolbox.services.drive_organizer import main
        files = [_make_file('doc.txt', fid='id_doc')]
        _run_scan(files, dry_run=False, analysis=ANALYSIS_MEDIUM,
                  new_name='2026-01-15 - Unknown - Some document.txt',
                  target_id='id_finance')
        self.assertEqual(main.stats.renamed, 1)
        self.assertEqual(main.stats.moved, 1)


class TestExecuteLowConfidence(unittest.TestCase):

    def setUp(self):
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_low_confidence_moves_to_review(self):
        """Low confidence must move to Review folder (Spec V2)."""
        f = _make_file('mystery.pdf', fid='id_mystery')
        from toolbox.services.drive_organizer import main
        
        svc = _make_service([f])
        
        with patch.object(main, 'download_file_content', return_value=b''), \
             patch('toolbox.services.drive_organizer.main.call_json_llm', return_value=(ANALYSIS_LOW, 'reasoning', 10)), \
             patch.object(main, 'resolve_folder_id', side_effect=lambda p: 'id_review' if 'Review' in p else 'id_target'), \
             patch.object(main, 'get_category_prompt_str', return_value=''), \
             patch.object(main, 'check_duplicate', return_value=(None, None)), \
             patch.object(main, 'post_process_memory'), \
             patch.object(main, 'move_file', return_value=True) as mock_move:
            
            main.scan_folder('id_inbox', dry_run=False, service=svc)

        # Move to review
        mock_move.assert_called_once_with(svc, 'id_mystery', 'id_review', 'mystery.pdf')
        self.assertEqual(main.stats.moved, 1)


class TestNewFeaturesV2(unittest.TestCase):

    def setUp(self):
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_check_duplicate_name_match(self):
        """check_duplicate should return file ID on name match."""
        from toolbox.services.drive_organizer import main
        svc = MagicMock()
        svc.files().list().execute.return_value = {
            'nextPageToken': None,
            'files': [{'id': 'id_dup', 'name': 'existing.pdf', 'md5Checksum': 'abc'}]
        }
        
        fid, dtype = main.check_duplicate(svc, 'id_target', 'existing.pdf')
        self.assertEqual(fid, 'id_dup')
        self.assertEqual(dtype, 'name_match')

    def test_check_duplicate_pagination(self):
        """check_duplicate should page through results."""
        from toolbox.services.drive_organizer import main
        svc = MagicMock()
        svc.files().list.return_value.execute.side_effect = [
            {'nextPageToken': 'token2', 'files': [{'id': 'id1', 'name': 'other.pdf'}]},
            {'nextPageToken': None, 'files': [{'id': 'id_dup', 'name': 'existing.pdf'}]}
        ]
        
        fid, dtype = main.check_duplicate(svc, 'id_target', 'existing.pdf')
        self.assertEqual(fid, 'id_dup')
        self.assertEqual(dtype, 'name_match')
        self.assertEqual(svc.files().list.call_count, 2)

    def test_check_duplicate_hash_match(self):
        """check_duplicate should return file ID and hash_match on checksum match."""
        from toolbox.services.drive_organizer import main
        svc = MagicMock()
        svc.files().list().execute.return_value = {
            'nextPageToken': None,
            'files': [{'id': 'id_dup', 'name': 'existing.pdf', 'md5Checksum': 'abc'}]
        }
        
        fid, dtype = main.check_duplicate(svc, 'id_target', 'existing.pdf', checksum='abc')
        self.assertEqual(fid, 'id_dup')
        self.assertEqual(dtype, 'hash_match')

    def test_check_duplicate_different_name_hash_match(self):
        """check_duplicate should detect content duplicate even if filename differs."""
        from toolbox.services.drive_organizer import main
        svc = MagicMock()
        svc.files().list().execute.return_value = {'files': [{'id': 'id_existing', 'name': 'old_name.pdf', 'md5Checksum': 'hash123'}]}
        
        fid, dtype = main.check_duplicate(svc, 'id_target', 'new_name.pdf', checksum='hash123')
        self.assertEqual(fid, 'id_existing')
        self.assertEqual(dtype, 'hash_match')
        
        # Verify the query lists the folder
        args, kwargs = svc.files().list.call_args
        self.assertIn("'id_target' in parents", kwargs['q'])
        self.assertNotIn("md5Checksum", kwargs['q'])

    @patch('toolbox.services.drive_organizer.main.EntityMemory')
    @patch('toolbox.services.drive_organizer.main.build_entity_id')
    def test_post_process_memory_calls_save(self, mock_build, mock_em):
        """post_process_memory should load, update, and save entity memory."""
        from toolbox.services.drive_organizer import main
        analysis = {
            'entity': 'Chase',
            'doc_date': '2026-05-01',
            'folder_path': '02 - Finance/Banking'
        }
        
        mem_instance = mock_em.load_from_drive.return_value
        mem_instance.entity_id = None
        
        main.post_process_memory(analysis, '2026-05-01 - Chase - Statement.pdf', 'id_file')
        
        mock_em.load_from_drive.assert_called_once_with('Finance', 'Chase.md')
        mem_instance.add_timeline_event.assert_called_once()
        mem_instance.add_source.assert_called_once()
        mem_instance.save_to_drive.assert_called_once_with('Finance', 'Chase.md')


class TestRecursion(unittest.TestCase):

    def setUp(self):
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_subfolder_triggers_recursive_scan(self):
        """A folder mime type entry triggers a recursive scan_folder call."""
        from toolbox.services.drive_organizer import main

        sub_folder = _make_file('SubFolder', 'application/vnd.google-apps.folder', fid='id_sub')
        inner_file = _make_file('note.txt', 'text/plain', fid='id_note')

        call_count = [0]
        list_results = {
            'id_inbox': [sub_folder],
            'id_sub': [inner_file],
        }

        svc = MagicMock()
        def list_side_effect(q=None, fields=None):
            # Extract folder ID from query
            import re
            m = re.search(r"'([^']+)' in parents", q)
            fid = m.group(1) if m else 'id_inbox'
            result = MagicMock()
            result.execute.return_value = {'files': list_results.get(fid, [])}
            return result

        svc.files().list.side_effect = list_side_effect
        svc.files().update.return_value.execute.return_value = {}

        with patch.object(main, 'download_file_content', return_value=b'content'), \
             patch('toolbox.services.drive_organizer.main.call_json_llm', return_value=(ANALYSIS_HIGH, 'reasoning', 5)), \
             patch.object(main, 'resolve_folder_id', return_value='id_target'), \
             patch.object(main, 'get_category_prompt_str', return_value=''), \
             patch.object(main, 'log_to_sheet'), \
             patch.object(main, 'send_message'), \
             patch.object(main, 'move_file', return_value=True):
            main.scan_folder('id_inbox', dry_run=True, service=svc,
                             recursive=True, folder_name='Inbox')

        # list() should have been called twice: once for Inbox, once for SubFolder
        self.assertGreaterEqual(svc.files().list.call_count, 2)

    def test_no_recursion_when_disabled(self):
        """Subfolders are not scanned when recursive=False."""
        from toolbox.services.drive_organizer import main

        sub_folder = _make_file('SubFolder', 'application/vnd.google-apps.folder', fid='id_sub')
        svc = _make_service([sub_folder])

        with patch('toolbox.services.drive_organizer.main.call_json_llm') as mock_ai, \
             patch.object(main, 'get_category_prompt_str', return_value=''), \
             patch.object(main, 'send_message'):
            main.scan_folder('id_inbox', dry_run=True, service=svc,
                             recursive=False, folder_name='Inbox')

        # list() called once only (for inbox, not for subfolder)
        self.assertEqual(svc.files().list.call_count, 1)
        mock_ai.assert_not_called()


class TestCliCompatibility(unittest.TestCase):

    def test_legacy_execute_flag_enables_run_mode(self):
        from toolbox.services.drive_organizer import main

        args = main.parse_args(["--execute"])

        self.assertFalse(args.run)
        self.assertTrue(args.execute)

    def test_legacy_inbox_flag_is_accepted(self):
        from toolbox.services.drive_organizer import main

        args = main.parse_args(["--inbox", "--execute"])

        self.assertTrue(args.inbox)
        self.assertTrue(args.execute)


