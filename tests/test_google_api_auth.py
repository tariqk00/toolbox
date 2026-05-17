import pytest
from unittest.mock import MagicMock, patch
from google.auth.exceptions import RefreshError
from toolbox.lib.google_api import GoogleAuth

@patch("toolbox.lib.google_api.Request")
@patch("toolbox.lib.telegram.send_message")
def test_refresh_with_retry_invalid_grant(mock_send_message, mock_request):
    auth = GoogleAuth()
    mock_creds = MagicMock()
    # Raise RefreshError with 'invalid_grant'
    mock_creds.refresh.side_effect = RefreshError("Token has been expired or revoked. invalid_grant")
    
    mock_log = MagicMock()
    
    with pytest.raises(RefreshError):
        auth._refresh_with_retry(mock_creds, mock_log)
    
    # Verify log called with FATAL
    mock_log.assert_any_call("AUTH_REFRESH", "FATAL", "OAuth Token Revoked (invalid_grant). Manual re-auth required on Chromebook.", level="ERROR")
    
    # Verify Telegram message sent
    mock_send_message.assert_called_once_with(
        "OAuth Token Revoked (invalid_grant). Manual re-auth required on Chromebook.",
        service="google_auth",
        category="error",
        origin="google_auth"
    )

@patch("toolbox.lib.google_api.Request")
def test_refresh_with_retry_success(mock_request):
    auth = GoogleAuth()
    mock_creds = MagicMock()
    mock_log = MagicMock()
    
    result = auth._refresh_with_retry(mock_creds, mock_log)
    
    assert result is True
    mock_creds.refresh.assert_called_once()
    mock_log.assert_called_with("AUTH_REFRESH", "SUCCESS", "Token refreshed (attempt 1).")
