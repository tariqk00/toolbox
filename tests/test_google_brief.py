
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from toolbox.services.email_extractor.categories import google_brief

def test_google_brief_none_handling():
    print("Testing Google Brief NoneType handling...")
    
    email = {
        'id': 'msg_brief_123',
        'subject': 'Your Day Ahead',
        'date': '2026-05-02',
        'plain': 'Some body text'
    }
    state = {'processed_briefs': []}
    
    # Mock LLM response with None values that caused the crash
    mock_details = {
        'tasks': [],
        'events': [
            {
                'title': 'Test Event',
                'time': '10:00',
                'location': None, # This was crashing
                'notes': None     # This was crashing
            }
        ]
    }
    
    import json
    with patch('toolbox.lib.llm_gateway.call_llm', return_value={'text': json.dumps(mock_details)}), \
         patch('toolbox.services.email_extractor.categories.google_brief.append_to_memory') as mock_append:
        
        result = google_brief.process(email, state)
        
        assert result is not None
        assert result['category'] == 'google_brief'
        assert "1 events" in result['summary']
        
        # Verify markdown content doesn't have @ None or similar
        args, _ = mock_append.call_args
        content = args[2]
        print(f"Generated content:\n{content}")
        assert "Test Event" in content
        assert "None" not in content
        
    print("Google Brief NoneType handling test passed!")

if __name__ == "__main__":
    try:
        test_google_brief_none_handling()
        print("\nAll Google Brief tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

