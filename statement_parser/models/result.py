from pydantic import BaseModel
from typing import Optional
from statement_parser.models.transaction import TransactionRow
from statement_parser.models.statement import StatementMetadata


class ParseError(BaseModel):
    code: str
    message: str


class ParseResult(BaseModel):
    success: bool
    bank_code: Optional[str] = None
    parser_used: Optional[str] = None
    parser_version: str = "0.2.0"
    file_hash: Optional[str] = None
    metadata: Optional[StatementMetadata] = None
    transactions: list[TransactionRow] = []
    opening_balance: Optional[str] = None
    closing_balance: Optional[str] = None
    balance_validated: bool = False
    warnings: list[str] = []
    error: Optional[ParseError] = None
    ocr_attempted: bool = False
