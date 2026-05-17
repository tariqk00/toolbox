import pytest
from unittest.mock import patch
from toolbox.lib.telegram import is_automation_generated, _encode_origin

def test_is_automation_generated():
    origin = "test-origin"
    text = f"Hello world{_encode_origin(origin)}"
    assert is_automation_generated(text) == origin
    
    text_no_tag = "Hello world"
    assert is_automation_generated(text_no_tag) is None

@patch("toolbox.lib.llm_gateway.call_llm")
def test_classifier_skips_automation(mock_call_llm):
    from toolbox.services.inbox_scanner.classifier import classify_email
    
    body = "System report" + _encode_origin("cron-job")
    
    result = classify_email("bot@system.com", "Daily Log", body)
    
    assert result['category'] == 'skip'
    assert 'Automation detected' in result['reason']
    assert 'cron-job' in result['reason']
    
    # Ensure LLM was NOT called
    mock_call_llm.assert_not_called()
