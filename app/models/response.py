from pydantic import BaseModel
from typing import Optional, List


class StatementPeriod(BaseModel):
    from_date: Optional[str] = None   # ISO date YYYY-MM-DD
    to_date: Optional[str] = None


class TransactionRow(BaseModel):
    transaction_date: str             # ISO date YYYY-MM-DD
    value_date: Optional[str] = None  # ISO date YYYY-MM-DD
    raw_description: str
    amount: str                       # decimal string e.g. "1299.00"
    transaction_type: str             # "DEBIT" | "CREDIT"
    reference_number: Optional[str] = None
    balance_after: Optional[str] = None  # decimal string
    payment_mode: Optional[str] = None   # UPI | NEFT | RTGS | IMPS | CARD | CASH | CHEQUE | WALLET | OTHER


class ParseResponse(BaseModel):
    success: bool
    bank_detected: Optional[str] = None
    parser_used: Optional[str] = None
    parser_version: str
    opening_balance: Optional[str] = None
    closing_balance: Optional[str] = None
    balance_validated: bool = False
    statement_period: Optional[StatementPeriod] = None
    transactions: List[TransactionRow] = []
    warnings: List[str] = []
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    ocr_attempted: bool = False
