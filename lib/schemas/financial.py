"""
Normalized financial schema for receipts and orders.
Ensures consistency across LLM extraction and Markdown/Telegram rendering.
"""
from typing import List, Optional, Dict
from dataclasses import dataclass, field, asdict

@dataclass
class LineItem:
    name: str
    qty: int = 1
    unit_price: Optional[str] = ""
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
class OrderMetadata:
    order_number: Optional[str] = ""
    carrier: Optional[str] = ""
    tracking: Optional[str] = ""
    estimated_delivery: Optional[str] = ""

@dataclass
class FinancialRecord:
    vendor: str
    date: str  # YYYY-MM-DD
    type: str  # Payment, Receipt, Order, etc.
    line_items: List[LineItem] = field(default_factory=list)
    accounting: Accounting = field(default_factory=Accounting)
    payment: Payment = field(default_factory=Payment)
    metadata: OrderMetadata = field(default_factory=OrderMetadata)

    def to_dict(self):
        return asdict(self)
