"""
Smoke tests — live Drive integration.
Skipped by default. Run with: pytest --smoke tests/smoke/

These tests make REAL Drive API calls and require valid credentials at
~/github/tariqk00/toolbox/config/token.json.

Run from repo root:
    source google-drive/venv/bin/activate
    PYTHONPATH=/home/tariqk/github/tariqk00 pytest --smoke tests/smoke/ -v
"""
import pytest


@pytest.mark.smoke
class TestDriveConnectivity:

    def test_drive_service_authenticates(self):
        """get_drive_service() returns a functional service object."""
        from toolbox.lib.drive_utils import get_drive_service
        svc = get_drive_service()
        assert svc is not None

    def test_inbox_folder_is_listable(self):
        """Drive Inbox folder (INBOX_ID) can be listed without error."""
        from toolbox.lib.drive_utils import get_drive_service, INBOX_ID
        svc = get_drive_service()
        results = svc.files().list(
            q=f"'{INBOX_ID}' in parents and trashed = false",
            fields="files(id, name)",
            pageSize=5,
        ).execute()
        assert 'files' in results

    def test_drive_tree_ids_resolve(self):
        """All folder IDs in drive_tree.json can be listed (no 404s)."""
        from toolbox.lib.drive_utils import get_drive_service, DRIVE_TREE
        svc = get_drive_service()
        path_to_id = DRIVE_TREE.get('path_to_id', {})
        if not path_to_id:
            pytest.skip("drive_tree.json not present")

        errors = []
        for path, fid in list(path_to_id.items())[:10]:  # spot-check first 10
            try:
                svc.files().get(fileId=fid, fields='id').execute()
            except Exception as e:
                errors.append(f"{path} ({fid}): {e}")

        assert not errors, "Some drive_tree folder IDs are invalid:\n" + "\n".join(errors)


@pytest.mark.smoke
class TestAiEngineSmoke:

    def test_analyze_text_returns_valid_result(self):
        """analyze_with_gemini on a short text snippet returns a parseable dict."""
        from toolbox.lib.ai_engine import analyze_with_gemini
        text = b"Invoice from Amazon dated January 2026 for $49.99 - Prime membership renewal"
        result, tokens = analyze_with_gemini(text, 'text/plain', 'invoice.txt', '01 - Second Brain')
        assert isinstance(result, dict), "Expected dict result"
        assert 'confidence' in result, "Expected confidence field"
        assert 'folder_path' in result, "Expected folder_path field"
        assert isinstance(tokens, int), "Expected integer token count"
        assert tokens >= 0, "Expected non-negative token count"
