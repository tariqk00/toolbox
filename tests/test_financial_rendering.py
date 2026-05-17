import pytest
from toolbox.lib.schemas.financial import FinancialRecord, LineItem, Accounting, Payment, OrderMetadata
from toolbox.lib.telegram import render_financial_body
from toolbox.services.email_extractor.writers import render_financial_markdown

@pytest.fixture
def sample_record():
    return FinancialRecord(
        vendor="Amazon",
        date="2026-05-17",
        type="Order",
        line_items=[
            LineItem(name="Mechanical Keyboard", qty=1, unit_price="$89.99"),
            LineItem(name="USB-C Cable", qty=2, unit_price="$9.99")
        ],
        accounting=Accounting(
            subtotal="$109.97",
            tax="$9.62",
            fees="$0.00",
            discounts="-$5.00",
            total="$114.59"
        ),
        payment=Payment(method="Visa", last_4="1234", cardholder="Tariq"),
        metadata=OrderMetadata(order_number="112-1234567-1234567", carrier="UPS", tracking="1Z12345")
    )

def test_render_financial_body(sample_record):
    body = render_financial_body(sample_record.to_dict())
    
    assert "💰 <b>Total: $114.59</b>" in body
    assert "Mechanical Keyboard — $89.99" in body
    assert "USB-C Cable x2 — $9.99" in body
    assert "Subtotal: $109.97" in body
    assert "Tax: $9.62" in body
    assert "Saved: -$5.00" in body
    assert "💳 Visa (1234) [Tariq]" in body
    assert "🚚 UPS: 1Z12345" in body

def test_render_financial_markdown(sample_record):
    md = render_financial_markdown(sample_record.to_dict())
    
    assert "## 2026-05-17 — $114.59" in md
    assert "**Merchant:** Amazon" in md
    assert "**Payment:** Visa (1234) [Tariq]" in md
    assert "**Financial Breakdown:** Subtotal: $109.97 | Tax: $9.62 | Discounts: -$5.00" in md
    assert "- Mechanical Keyboard — $89.99" in md
    assert "- USB-C Cable ×2 — $9.99" in md
    assert "**Tracking:** 1Z12345 (UPS)" in md
