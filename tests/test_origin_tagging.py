import pytest
import json
from unittest.mock import MagicMock, patch
from toolbox.lib.telegram import send_message, is_automation_generated, ZWSP, _encode_origin

def test_is_automation_generated():
    origin = "test-origin"
    text = f"Hello world{_encode_origin(origin)}"
    assert is_automation_generated(text) == origin
    
    text_no_tag = "Hello world"
    assert is_automation_generated(text_no_tag) is None

@patch("urllib.request.urlopen")
@patch("urllib.request.Request")
@patch("toolbox.lib.telegram._load_config")
def test_send_message_adds_tag(mock_load_config, mock_Request, mock_urlopen):
    # Setup mock config
    mock_load_config.return_value = {"bot_token": "123", "chat_id": "456"}
    
    # Setup mock response
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"ok": true}'
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    # Test tagging
    send_message("My alert", service="test-service", origin="my-origin")
    
    # Check what was passed to Request
    # It might be positional or keyword data
    # mock_Request is the constructor
    args, kwargs = mock_Request.call_args
    data = kwargs.get('data') or args[1]
    payload = json.loads(data.decode())
    
    assert "<b>🤖 TEST-SERVICE</b>" in payload['text']
    assert "My alert" in payload['text']
    assert ZWSP in payload['text']
    assert is_automation_generated(payload['text']) == "my-origin"
    assert "<code>my-origin</code>" in payload['text']

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
