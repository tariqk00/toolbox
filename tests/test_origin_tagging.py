import pytest
from unittest.mock import MagicMock, patch
from toolbox.lib.telegram import send_message, is_automation_generated

def test_is_automation_generated():
    text = "Hello world\n<!-- origin: test-origin -->"
    assert is_automation_generated(text) == "test-origin"
    
    text_no_tag = "Hello world"
    assert is_automation_generated(text_no_tag) is None
    
    text_malformed = "<!-- origin:  -->"
    assert is_automation_generated(text_malformed) is None

@patch("urllib.request.urlopen")
@patch("urllib.request.Request")
@patch("toolbox.lib.telegram._load_config")
def test_send_message_adds_tag(mock_load_config, mock_request, mock_urlopen):
    # Setup mock config
    mock_load_config.return_value = {"bot_token": "123", "chat_id": "456"}
    
    # Setup mock response
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"ok": true}'
    mock_urlopen.return_value.__enter__.return_value = mock_response
    
    # Test tagging
    send_message("My alert", service="test-service", origin="my-origin")
    
    # Verify the body of the request sent to Telegram
    args, kwargs = mock_request.call_args
    import json
    payload = json.loads(kwargs['data'].decode())
    
    assert "<!-- origin: my-origin -->" in payload['text']
    assert "[test-service] My alert" in payload['text']

@patch("toolbox.lib.llm_gateway.call_llm")
def test_classifier_skips_automation(mock_call_llm):
    from toolbox.services.inbox_scanner.classifier import classify_email
    
    body = "System report\n<!-- origin: cron-job -->"
    result = classify_email("bot@system.com", "Daily Log", body)
    
    assert result['category'] == 'skip'
    assert 'Automation detected' in result['reason']
    
    # Ensure LLM was NOT called
    mock_call_llm.assert_not_called()
