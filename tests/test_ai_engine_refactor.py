
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from toolbox.lib import ai_engine, llm, gemini

def test_wrappers_redirect():
    print("Testing LLM/Gemini wrapper redirection...")
    
    with patch('toolbox.lib.llm.call_llm') as mock_llm_call, \
         patch('toolbox.lib.gemini.call_llm') as mock_gemini_call:
        
        mock_llm_call.return_value = {"text": "Engine Response"}
        mock_gemini_call.return_value = {"text": "Engine Response"}
        
        # Test llm.call
        res = llm.call("Hello")
        assert res == "Engine Response"
        mock_llm_call.assert_called_with(task_type='automation', prompt="Hello")
        
        # Test ai_engine.call (which now redirects to llm.call)
        res = ai_engine.call("Hello AI")
        assert res == "Engine Response"
        mock_llm_call.assert_called_with(task_type='automation', prompt="Hello AI")
        
        # Test gemini.call_gemini
        res = gemini.call_gemini("Hello Gemini")
        assert res == "Engine Response"
        mock_gemini_call.assert_called_with(task_type='automation', prompt="Hello Gemini")
        
    print("Wrapper redirection passed!")

def test_parse_json_robustness():
    print("\nTesting JSON parsing robustness...")
    raw = "```json\n{\"key\": \"value\"}\n```"
    parsed = ai_engine._parse_json(raw)
    assert parsed == {"key": "value"}
    
    raw_dirty = "Here is some text { \"a\": 1 } and more."
    parsed_dirty = ai_engine._parse_json(raw_dirty)
    assert parsed_dirty == {"a": 1}
    print("JSON parsing passed!")

if __name__ == "__main__":
    try:
        test_wrappers_redirect()
        test_parse_json_robustness()
        print("\nAll AI Engine refactor tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
