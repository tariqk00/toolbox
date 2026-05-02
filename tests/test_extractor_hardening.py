
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
# Add the parent of the repository to sys.path to support 'from toolbox.lib...'
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

# Mock everything before importing local modules
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['googleapiclient.http'] = MagicMock()
sys.modules['googleapiclient.errors'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.credentials'] = MagicMock()

# Mock internal lib dependencies
sys.modules['toolbox.lib.google_api'] = MagicMock()
sys.modules['toolbox.lib.drive_utils'] = MagicMock()
sys.modules['toolbox.lib.log_manager'] = MagicMock()

from toolbox.services.email_extractor import scanner

def test_fetch_category_emails_skips_processed_threads():
    print("Testing thread-level skipping...")
    
    mock_service = MagicMock()
    # Mock _fetch_messages to return two emails in different threads
    raw_messages = [
        {'id': 'msg1', 'threadId': 'thread1'},
        {'id': 'msg2', 'threadId': 'thread2'}
    ]
    
    state = {'processed_threads': ['thread1']}
    config = {'test_cat': {'senders': {'test@example.com': 'Test'}}}
    
    with patch('toolbox.services.email_extractor.scanner._fetch_messages', return_value=raw_messages), \
         patch('toolbox.services.email_extractor.scanner.get_full_email') as mock_get_full, \
         patch('toolbox.services.email_extractor.scanner._match_sender', return_value='Test'):
        
        # Mock get_full_email to return basic dicts
        mock_get_full.side_effect = lambda svc, mid: {
            'id': mid, 'thread_id': 'thread2' if mid == 'msg2' else 'thread1', 
            'from': 'test@example.com', 'date_dt': 123, 'subject': 'test'
        }
        
        results = scanner.fetch_category_emails(mock_service, 'test_cat', config, state=state)
        
        print(f"Results: {len(results)} (Expected: 1)")
        assert len(results) == 1
        assert results[0]['id'] == 'msg2'
        print("Thread skipping test passed!")

if __name__ == "__main__":
    try:
        test_fetch_category_emails_skips_processed_threads()
        print("\nAll hardening tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
