"""
statement-parser — universal bank/credit-card statement parsing library.

Public API surface:
    StatementParser          — main entry point (parse, file_hash, supported_banks)
    ParseResult              — returned by StatementParser.parse()
    TransactionRow           — one transaction extracted from a statement
    StatementMetadata        — account/period metadata from the statement
    BankCode                 — enum of supported banks
    Currency                 — enum of supported currencies
    StatementType            — BANK | CREDIT_CARD | LOAN
    TransactionType          — DEBIT | CREDIT
    PaymentMode              — UPI | NEFT | IMPS | CARD | ATM | ACH | WIRE | etc.
"""
from statement_parser.facade import StatementParser
from statement_parser.models.result import ParseResult, ParseError
from statement_parser.models.transaction import TransactionRow
from statement_parser.models.statement import StatementMetadata, StatementPeriod
from statement_parser.enums import BankCode, Currency, StatementType, TransactionType, PaymentMode

__version__ = "0.2.0"
__all__ = [
    "StatementParser",
    "ParseResult",
    "ParseError",
    "TransactionRow",
    "StatementMetadata",
    "StatementPeriod",
    "BankCode",
    "Currency",
    "StatementType",
    "TransactionType",
    "PaymentMode",
    "__version__",
]
