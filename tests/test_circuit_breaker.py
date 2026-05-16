import pytest
from unittest.mock import MagicMock, patch
from toolbox.lib.llm_gateway import LLMGateway
from toolbox.lib.providers.base import QuotaExhaustedError
from toolbox.lib import quota_manager

@patch("toolbox.lib.llm_gateway.LLMGateway._load_config")
@patch("toolbox.lib.llm_gateway.LLMGateway._init_secrets")
@patch("toolbox.lib.quota_manager.load")
@patch("toolbox.lib.quota_manager.save")
def test_circuit_breaker_trips_on_quota_error(mock_save, mock_load, mock_init, mock_config):
    # 1. Setup Config
    mock_config.return_value = {
        "tiers": {
            "test_tier": {
                "providers": [
                    {"name": "broken_provider", "model": "fail-1"},
                    {"name": "fallback_provider", "model": "pass-1"}
                ]
            }
        },
        "routes": {"test_task": "test_tier"},
        "budgets": {"daily_usd": 10.0, "per_task_usd": 1.0},
        "costs": {"fail-1": 1.0, "pass-1": 1.0}
    }
    
    # Mock quota state
    mock_load.return_value = {
        "date": "2026-05-16",
        "total_tokens_used": 0,
        "total_usd_used": 0.0,
        "degraded_providers": [],
        "spend_by_task": {}
    }

    gateway = LLMGateway()
    
    # 2. Mock Providers
    mock_broken = MagicMock()
    mock_broken.supports.return_value = True
    # First call raises QuotaExhaustedError
    mock_broken.analyze.side_effect = QuotaExhaustedError("Monthly cap hit")
    
    mock_fallback = MagicMock()
    mock_fallback.supports.return_value = True
    mock_fallback.analyze.return_value = ("Success!", 100)

    def side_effect_get_provider(cfg):
        if cfg['name'] == "broken_provider": return mock_broken
        return mock_fallback

    with patch.object(gateway, "_get_provider_instance", side_effect=side_effect_get_provider):
        # 3. First call - should hit broken then fallback
        res = gateway.call("test_task", "Hello")
        
        assert res['text'] == "Success!"
        assert res['provider'] == "fallback_provider"
        
        # Verify broken_provider was marked degraded
        # (Check mock_save calls to see if it was added to degraded_providers)
        # Actually easier to just check quota_manager.get_degraded_providers() if we didn't mock it so hard
        # But since we mocked load/save, we check if broken_provider is in the state passed to save
        found_degraded = False
        for call in mock_save.call_args_list:
            state = call[0][0]
            if "broken_provider" in state.get("degraded_providers", []):
                found_degraded = True
        assert found_degraded, "broken_provider should be in degraded_providers list"

        # 4. Second call - should skip broken_provider entirely
        # Update mock_load to reflect the degraded state
        mock_load.return_value["degraded_providers"] = ["broken_provider"]
        mock_broken.analyze.reset_mock()
        
        gateway.call("test_task", "Hello again")
        
        mock_broken.analyze.assert_not_called()

def test_spend_aggregation():
    # Test record_llm_usage aggregates by task_type
    with patch("toolbox.lib.quota_manager.load") as mock_load,          patch("toolbox.lib.quota_manager.save") as mock_save:
        
        mock_load.return_value = {
            "date": "2026-05-16",
            "total_usd_used": 0.0,
            "spend_by_task": {}
        }
        
        quota_manager.record_llm_usage(100, 0.50, metadata={"task_type": "scanner"})
        quota_manager.record_llm_usage(100, 0.25, metadata={"task_type": "scanner"})
        quota_manager.record_llm_usage(100, 1.00, metadata={"task_type": "sorter"})
        
        # Get final state passed to save
        final_state = mock_save.call_args[0][0]
        assert final_state["spend_by_task"]["scanner"] == 0.75
        assert final_state["spend_by_task"]["sorter"] == 1.00
