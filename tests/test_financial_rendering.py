import pytest
import json
from unittest.mock import MagicMock, patch
from toolbox.lib.schemas.financial import FinancialRecord, LineItem, Accounting, Payment, FinancialMetadata
from toolbox.lib.telegram import render_financial_body, bold_header, send_message
from toolbox.services.email_extractor.writers import render_financial_markdown

@pytest.fixture
def sample_record():
    return FinancialRecord(
        vendor="Amazon",
        date="2026-05-17",
        record_type="Order",
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
        metadata=FinancialMetadata(order_number="112-1234567-1234567", carrier="UPS", tracking="1Z12345")
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

def test_render_financial_body_escaping():
    record = FinancialRecord(
        vendor="AT&T",
        date="2026-05-17",
        record_type="Payment",
        line_items=[LineItem(name="Internet <Fiber>", qty=1, unit_price="$80.00")],
        accounting=Accounting(total="$80.00")
    )
    body = render_financial_body(record.to_dict())
    # Note: Vendor is NOT in body, it's in the header (tested in test_bold_header_escaping)
    assert "Internet &lt;Fiber&gt;" in body

def test_bold_header_escaping():
    header = bold_header("AT&T")
    assert "AT&amp;T" in header
    
    header_dec = bold_header("inbox-scanner <test>")
    assert "INBOX-SCANNER &lt;TEST&gt;" in header_dec

def test_render_financial_body_truncation():
    items = [LineItem(name=f"Item {i}", qty=1, unit_price="$1.00") for i in range(12)]
    record = FinancialRecord(vendor="Store", date="2026-05-17", record_type="Receipt", line_items=items)
    body = render_financial_body(record.to_dict())
    assert "Item 0" in body
    assert "Item 7" in body
    assert "Item 8" not in body
    assert "<i>...and 4 more</i>" in body

def test_render_financial_markdown(sample_record):
    md = render_financial_markdown(sample_record.to_dict())
    
    assert "## 2026-05-17 — $114.59" in md
    assert "**Merchant:** Amazon" in md
    assert "**Payment:** Visa (1234) [Tariq]" in md
    assert "**Financial Breakdown:** Subtotal: $109.97 | Tax: $9.62 | Discounts: -$5.00" in md
    assert "- Mechanical Keyboard — $89.99" in md
    assert "- USB-C Cable ×2 — $9.99" in md
    assert "**Tracking:** 1Z12345 (UPS)" in md
