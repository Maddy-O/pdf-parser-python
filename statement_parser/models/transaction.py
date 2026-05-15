from pydantic import BaseModel
from typing import Optional
from statement_parser.enums import TransactionType, PaymentMode, Currency


class TransactionRow(BaseModel):
    transaction_date: str              # ISO date YYYY-MM-DD
    value_date: Optional[str] = None   # ISO date YYYY-MM-DD (settlement date)
    raw_description: str               # Exact text from the statement row
    amount: str                        # Decimal string e.g. "1299.00"
    transaction_type: TransactionType  # DEBIT or CREDIT
    currency: Currency = Currency.INR  # ISO 4217 code for this transaction's currency
    # For international transactions on a card (e.g. USD charge on INR card):
    original_currency: Optional[Currency] = None
    original_amount: Optional[str] = None
    reference_number: Optional[str] = None
    balance_after: Optional[str] = None
    payment_mode: Optional[PaymentMode] = None
    merchant_name: Optional[str] = None  # Cleaned merchant name if detectable
