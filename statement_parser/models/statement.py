from pydantic import BaseModel
from typing import Optional
from statement_parser.enums import Currency, StatementType


class StatementPeriod(BaseModel):
    from_date: Optional[str] = None   # ISO date YYYY-MM-DD
    to_date: Optional[str] = None


class StatementMetadata(BaseModel):
    bank_code: str
    statement_type: StatementType = StatementType.BANK
    currency: Currency = Currency.UNKNOWN
    account_number_masked: Optional[str] = None
    account_holder: Optional[str] = None
    period: Optional[StatementPeriod] = None
    # Bank account specific
    account_type: Optional[str] = None      # SAVINGS | CURRENT | NRE | etc.
    ifsc_code: Optional[str] = None
    # Credit card specific
    credit_limit: Optional[str] = None
    available_credit: Optional[str] = None
    minimum_payment: Optional[str] = None
    payment_due_date: Optional[str] = None
    total_amount_due: Optional[str] = None  # Outstanding balance (CC only)
    total_purchases: Optional[str] = None
    total_payments: Optional[str] = None
