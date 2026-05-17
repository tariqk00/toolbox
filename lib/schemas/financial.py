"""
Normalized financial schema for receipts and orders.
Ensures consistency across LLM extraction and Markdown/Telegram rendering.

Note: Monetary values are currently strings to preserve original formatting 
from source emails for presentation purposes.
"""
from typing import List, Optional, Dict
from dataclasses import dataclass, field, asdict

@dataclass
class LineItem:
    name: str
    qty: int = 1
    unit_price: Optional[str] = ""  # Presentation string (e.g. "$10.00")
    total_price: Optional[str] = ""

@dataclass
class Accounting:
    subtotal: Optional[str] = ""
    tax: Optional[str] = ""
    fees: Optional[str] = ""
    discounts: Optional[str] = ""
    total: Optional[str] = ""

@dataclass
class Payment:
    method: Optional[str] = ""  # e.g. Visa, Amex, Bank
    last_4: Optional[str] = ""
    cardholder: Optional[str] = ""  # Tariq, Dawn, Sofia, Thomas

@dataclass
class FinancialMetadata:
    order_number: Optional[str] = ""
    carrier: Optional[str] = ""
    tracking: Optional[str] = ""
    estimated_delivery: Optional[str] = ""

@dataclass
class FinancialRecord:
    vendor: str
    date: str  # YYYY-MM-DD
    record_type: str  # e.g. Payment, Receipt, Order, Statement
    line_items: List[LineItem] = field(default_factory=list)
    accounting: Accounting = field(default_factory=Accounting)
    payment: Payment = field(default_factory=Payment)
    metadata: FinancialMetadata = field(default_factory=FinancialMetadata)
    category: str = "receipts"  # receipts, orders, etc.

    def to_dict(self):
        return asdict(self)
