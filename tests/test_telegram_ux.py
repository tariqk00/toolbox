import pytest
from unittest.mock import MagicMock, patch
from toolbox.lib.telegram import bold_header, standard_footer, SERVICE_EMOJIS

def test_bold_header():
    # Test known service
    assert bold_header("ai-sorter") == "<b>📂 AI-SORTER</b>"
    # Test decorated service name (the Codex fix)
    assert bold_header("inbox-scanner · takhan") == "<b>📩 INBOX-SCANNER · TAKHAN</b>"
    # Test unknown service
    assert bold_header("unknown-bot") == "<b>🤖 UNKNOWN-BOT</b>"
    # Test custom emoji
    assert bold_header("ai-sorter", emoji="🔥") == "<b>🔥 AI-SORTER</b>"

def test_standard_footer():
    # Test origin only
    footer = standard_footer(origin="test-origin")
    assert "<code>test-origin</code>" in footer
    assert "Monit" in footer
    
    # Test origin + cost
    footer = standard_footer(origin="test-origin", cost=0.0051)
    assert "Cost: $0.0051" in footer
