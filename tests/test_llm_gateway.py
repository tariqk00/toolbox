import pytest
import os
import json
from unittest.mock import MagicMock, patch
from toolbox.lib.llm_gateway import LLMGateway

@pytest.fixture
def gateway():
    # Use the real config for tests to ensure it's valid
    return LLMGateway()

def test_routing_heartbeat(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    mock_provider.analyze.return_value = ("pong", 10)
    
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    # Heartbeat should use 'cheapest' tier
    res = gateway.call("heartbeat", "ping")
    assert res['text'] == "pong"
    assert res['tier'] == 'cheapest'

def test_budget_enforcement_daily(gateway, mocker):
    # Set current USD usage above the default limit (2.0)
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=5.0)
    
    with pytest.raises(RuntimeError, match="Daily LLM budget exceeded"):
        gateway.call("coding", "fix bug")

def test_budget_enforcement_per_task(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    # 2M tokens at 0.15/1M = $0.30. Per-task limit in config is 0.20.
    mock_provider.analyze.return_value = ("result", 2000000) 
    
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    with pytest.raises(RuntimeError, match="Task cost .* exceeded limit"):
        gateway.call("coding", "huge task")

def test_fallback_behavior(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    # Mock first provider failing consistently (3 retries), second succeeding
    mock_provider_fail = MagicMock()
    mock_provider_fail.supports.return_value = True
    mock_provider_fail.analyze.side_effect = Exception("429 Rate limit")
    
    mock_provider_success = MagicMock()
    mock_provider_success.supports.return_value = True
    mock_provider_success.analyze.return_value = ("fallback success", 20)
    
    # side_effect returns one for each call to _get_provider_instance
    # First provider is tried, then 3 retries (all fail), then next provider instance requested
    mocker.patch.object(gateway, '_get_provider_instance', side_effect=[mock_provider_fail, mock_provider_success])
    
    # Patch time.sleep to speed up tests
    mocker.patch('time.sleep')
    
    res = gateway.call("sub-agent", "do work")
    assert res['text'] == "fallback success"
    assert res['provider'] != 'N/A'

def test_long_context_routing(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    mock_provider.analyze.return_value = ("long result", 100)
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    # Prompt > 15000 tokens (threshold in config) -> 60000 chars
    long_prompt = "a" * 65000 
    res = gateway.call("automation", long_prompt)
    assert res['tier'] == 'long-context'

def test_unknown_route_defaults_to_efficiency(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    mock_provider.analyze.return_value = ("default result", 10)
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    res = gateway.call("unknown_task", "hello")
    assert res['tier'] == 'efficiency'
