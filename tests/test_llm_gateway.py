import pytest
import os
import json
from unittest.mock import MagicMock, patch
from toolbox.lib.llm_gateway import LLMGateway
from toolbox.lib.providers.base import RateLimitError, ProviderSkip

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

def test_pre_call_budget_block(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    
    # Patch config to have a very low per-task limit
    gateway.config['budgets']['per_task_usd'] = 0.000001
    
    with pytest.raises(RuntimeError, match="All providers in tier coding failed"):
        gateway.call("coding", "this should be too expensive")

def test_token_cap_truncation(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    # Capture the prompt sent to provider
    def analyze_side_effect(data, mime, prompt):
        return f"Truncated: {len(prompt)}", 10
    mock_provider.analyze.side_effect = analyze_side_effect
    
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    # Cheapest tier cap is 2000 tokens -> 8000 chars
    long_prompt = "x" * 20000
    res = gateway.call("heartbeat", long_prompt)
    
    # 2000 tokens * 4 chars/token = 8000 chars
    assert "Truncated: 8000" in res['text']

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
    
    # Prompt > 200000 tokens (threshold in config) -> 800000 chars
    long_prompt = "a" * 900000 
    res = gateway.call("automation", long_prompt)
    assert res['tier'] == 'long-context'

def test_unknown_route_fails_loudly(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    
    with pytest.raises(ValueError, match="Unknown task_type 'unknown_task'"):
        gateway.call("unknown_task", "hello")

def test_rate_limit_retry_behavior(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    mocker.patch('time.sleep')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    # Fail twice with RateLimitError, then succeed
    mock_provider.analyze.side_effect = [
        RateLimitError("429 RPM"),
        RateLimitError("429 RPM"),
        ("success after retries", 10)
    ]
    
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    res = gateway.call("heartbeat", "ping")
    assert res['text'] == "success after retries"
    assert mock_provider.analyze.call_count == 3

def test_rate_limit_exhaustion_reports_last_provider_error(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('time.sleep')

    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    mock_provider.analyze.side_effect = RateLimitError("429 RESOURCE_EXHAUSTED monthly cap")
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)

    with pytest.raises(RuntimeError) as exc:
        gateway.call("heartbeat", "ping")

    message = str(exc.value)
    assert "All providers in tier cheapest failed" in message
    assert "429 RESOURCE_EXHAUSTED monthly cap" in message
    assert "Last error: None" not in message

def test_text_plain_content_preservation(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    mock_provider.analyze.return_value = ("result", 10)
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    content = b"extra details"
    gateway.call("heartbeat", "the prompt", content_bytes=content, mime_type="text/plain")
    
    # Check that content_bytes was NOT dropped
    args, _ = mock_provider.analyze.call_args
    assert args[0] == content

def test_source_metadata_is_forwarded_to_usage_log(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    record_usage = mocker.patch('toolbox.lib.quota_manager.record_llm_usage')

    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    mock_provider.analyze.return_value = ("result", 10)
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)

    gateway.call("heartbeat", "ping", source="openclaw")

    args, kwargs = record_usage.call_args
    assert args[0] == 10
    assert args[1] >= 0.0
    assert kwargs["metadata"]["source"] == "openclaw"
    assert kwargs["metadata"]["task_type"] == "heartbeat"

def test_model_specific_cost_lookup(gateway, mocker):
    mocker.patch('toolbox.lib.quota_manager.get_total_usd_used', return_value=0.0)
    mocker.patch('toolbox.lib.quota_manager.record_llm_usage')
    
    mock_provider = MagicMock()
    mock_provider.supports.return_value = True
    # 100k tokens
    mock_provider.analyze.return_value = ("result", 100000)
    mocker.patch.object(gateway, '_get_provider_instance', return_value=mock_provider)
    
    # gemini-3.1-pro-preview is $2.00/1M in config
    # 100k tokens * $2.00 / 1M = $0.20
    res = gateway.call("final", "high stakes")
    assert res['model'] == 'gemini-3.1-pro-preview'
    assert res['cost'] == 0.20
