import pytest
from unittest.mock import MagicMock, patch
from toolbox.lib.providers.gemini import GeminiProvider
from toolbox.lib.providers.base import QuotaExhaustedError, RateLimitError

@patch("google.genai.Client")
def test_gemini_quota_detection(mock_client):
    provider = GeminiProvider(model_name="test-model", api_key="test-key")
    
    # 1. Test Transient Rate Limit (should NOT trip breaker)
    mock_client.return_value.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded")
    with pytest.raises(RateLimitError):
        provider._analyze_gateway(b"content", "text/plain", "prompt")
        
    # 2. Test Persistent Billing Cap (SHOULD trip breaker)
    mock_client.return_value.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: You exceeded your current quota, please check your plan and billing details")
    with pytest.raises(QuotaExhaustedError):
        provider._analyze_gateway(b"content", "text/plain", "prompt")

    # 3. Test Persistent Monthly Cap (SHOULD trip breaker)
    mock_client.return_value.models.generate_content.side_effect = Exception("Monthly cap hit")
    with pytest.raises(QuotaExhaustedError):
        provider._analyze_gateway(b"content", "text/plain", "prompt")
