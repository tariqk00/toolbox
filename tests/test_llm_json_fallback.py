import pytest
import json
from unittest.mock import MagicMock, patch
from toolbox.lib.llm_gateway import LLMGateway

@pytest.fixture
def gateway():
    return LLMGateway()

def test_json_fallback_resilience(gateway, mocker):
    """
    Test that if a provider returns invalid JSON when require_json=True,
    it falls back to the next provider in the tier.
    """
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    mocker.patch('time.sleep')
    
    # First provider returns malformed JSON
    mock_provider_fail = MagicMock()
    mock_provider_fail.supports.return_value = True
    mock_provider_fail.analyze.return_value = ("{ INVALID JSON }", 50)
    
    # Second provider returns valid JSON
    mock_provider_success = MagicMock()
    mock_provider_success.supports.return_value = True
    mock_provider_success.analyze.return_value = ('{"reasoning": "success", "result": "ok"}', 50)
    
    # We need to target a tier with multiple providers. 
    # 'efficiency' tier in config has deepseek, groq, gemini-paid.
    mocker.patch.object(gateway, '_get_provider_instance', side_effect=[mock_provider_fail, mock_provider_success])
    
    # Use a task that maps to efficiency tier
    res = gateway.call("automation", "extract data", require_json=True)
    
    assert res['json'] == {"reasoning": "success", "result": "ok"}
    assert mock_provider_fail.analyze.call_count == 1
    assert mock_provider_success.analyze.call_count == 1
