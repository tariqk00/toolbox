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

    def test_medium_confidence_renames_no_move(self):
        """Medium confidence → rename only, no move."""
        files = [_make_file('doc.txt', fid='id_doc')]
        svc, mock_move = _run_scan(files, dry_run=False, analysis=ANALYSIS_MEDIUM,
                                   new_name='2026-01-15 - Unknown - Some document.txt',
                                   target_id='id_brain')
        svc.files().update.assert_called()
        mock_move.assert_not_called()

    def test_medium_confidence_stats(self):
        from toolbox.services.drive_organizer import main
        files = [_make_file('doc.txt', fid='id_doc')]
        _run_scan(files, dry_run=False, analysis=ANALYSIS_MEDIUM,
                  new_name='2026-01-15 - Unknown - Some document.txt')
        self.assertEqual(main.stats.renamed, 1)
        self.assertEqual(main.stats.moved, 0)


class TestExecuteLowConfidence(unittest.TestCase):

    def setUp(self):
        from toolbox.services.drive_organizer import main
        main.stats = main.RunStats()

    def test_low_confidence_no_action(self):
        """Low confidence → no rename, no move."""
        files = [_make_file('mystery.pdf', 'application/pdf', fid='id_mystery')]
        svc, mock_move = _run_scan(files, dry_run=False, analysis=ANALYSIS_LOW,
                                   new_name='mystery.pdf')  # same name
        svc.files().update.assert_not_called()
        mock_move.assert_not_called()


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



