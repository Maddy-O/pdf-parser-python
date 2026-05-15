"""
Generic CSV parser. Handles the standard 5-column CSV format that most banks
export: Date, Description, Debit, Credit, Balance.
Also handles single-amount-column formats with signed amounts.
"""

import csv
import io
import logging
from statement_parser.enums import BankCode, Currency, TransactionType
from statement_parser.models.result import ParseResult, ParseError
from statement_parser.models.statement import StatementMetadata
from statement_parser.models.transaction import TransactionRow
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount, is_negative_amount
from statement_parser.utils.text import detect_payment_mode, extract_reference
from statement_parser.utils.balance_validator import validate_balance

import pdfplumber
_PARSER_VERSION = pdfplumber.__version__

logger = logging.getLogger(__name__)

_DATE_HEADERS    = {"date", "transaction date", "txn date", "tran date", "posting date", "value date"}
_DESC_HEADERS    = {"description", "narration", "particulars", "memo", "details", "remarks", "narrative"}
_DEBIT_HEADERS   = {"debit", "dr", "withdrawal", "withdrawals", "paid out", "debit amount"}
_CREDIT_HEADERS  = {"credit", "cr", "deposit", "deposits", "paid in", "credit amount"}
_AMOUNT_HEADERS  = {"amount", "transaction amount"}
_BALANCE_HEADERS = {"balance", "closing balance", "running balance", "available balance"}


class CsvParser:
    def parse(self, file_bytes: bytes, statement_id: str = "") -> ParseResult:
        try:
            text = file_bytes.decode("utf-8-sig")  # strip BOM if present
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
        except Exception as exc:
            return ParseResult(
                success=False,
                parser_used="CsvParser",
                parser_version=_PARSER_VERSION,
                error=ParseError(code="CSV_DECODE_ERROR", message=str(exc)),
            )

        header_idx, col_map = _find_header(rows)
        if header_idx is None or not col_map:
            return ParseResult(
                success=False,
                parser_used="CsvParser",
                parser_version=_PARSER_VERSION,
                error=ParseError(code="NO_HEADER", message="Could not detect header row in CSV"),
            )

        warnings: list[str] = []
        transactions = _parse_rows(rows[header_idx + 1:], col_map, warnings)
        balance_ok = validate_balance(None, transactions, None)

        return ParseResult(
            success=True,
            bank_code=BankCode.GENERIC.value,
            parser_used="CsvParser",
            parser_version=_PARSER_VERSION,
            metadata=StatementMetadata(bank_code=BankCode.GENERIC.value, currency=Currency.UNKNOWN),
            transactions=transactions,
            balance_validated=balance_ok,
            warnings=warnings,
        )


def _find_header(rows: list[list[str]]) -> tuple[int | None, dict[str, int]]:
    for row_idx, row in enumerate(rows[:10]):
        cells = [c.strip().lower() for c in row]
        has_date = any(c in _DATE_HEADERS for c in cells)
        has_desc = any(c in _DESC_HEADERS for c in cells)
        has_amount = any(c in _DEBIT_HEADERS | _CREDIT_HEADERS | _AMOUNT_HEADERS for c in cells)
        if not (has_date and has_desc and has_amount):
            continue

        col_map: dict[str, int] = {}
        for idx, cell in enumerate(cells):
            if cell in _DATE_HEADERS and "date" not in col_map:
                col_map["date"] = idx
            elif cell in _DESC_HEADERS and "desc" not in col_map:
                col_map["desc"] = idx
            elif cell in _DEBIT_HEADERS and "debit" not in col_map:
                col_map["debit"] = idx
            elif cell in _CREDIT_HEADERS and "credit" not in col_map:
                col_map["credit"] = idx
            elif cell in _AMOUNT_HEADERS and "amount" not in col_map:
                col_map["amount"] = idx
            elif cell in _BALANCE_HEADERS and "balance" not in col_map:
                col_map["balance"] = idx
        return row_idx, col_map
    return None, {}


def _parse_rows(
    rows: list[list[str]],
    col_map: dict[str, int],
    warnings: list[str],
) -> list[TransactionRow]:
    result: list[TransactionRow] = []
    has_split = "debit" in col_map and "credit" in col_map

    for row in rows:
        if not row or all(c.strip() == "" for c in row):
            continue

        def get(key: str) -> str | None:
            idx = col_map.get(key)
            if idx is None or idx >= len(row):
                return None
            return row[idx].strip() or None

        date = parse_date(get("date"), "auto")
        if not date:
            continue
        desc = get("desc") or ""
        if not desc:
            continue

        if has_split:
            debit = clean_amount(get("debit"))
            credit = clean_amount(get("credit"))
            if debit and _pos(get("debit")):
                amount, tx_type = debit, TransactionType.DEBIT
            elif credit and _pos(get("credit")):
                amount, tx_type = credit, TransactionType.CREDIT
            else:
                continue
        else:
            raw = get("amount")
            amount = clean_amount(raw)
            if not amount:
                continue
            # Negative amount = debit (common in US bank CSV exports)
            tx_type = TransactionType.DEBIT if is_negative_amount(raw or "") else TransactionType.CREDIT

        result.append(
            TransactionRow(
                transaction_date=date,
                raw_description=desc,
                amount=amount,
                transaction_type=tx_type,
                balance_after=clean_amount(get("balance")),
                payment_mode=detect_payment_mode(desc),
                reference_number=extract_reference(desc),
            )
        )
    return result


def _pos(raw: str | None) -> bool:
    if not raw:
        return False
    import re
    try:
        return float(re.sub(r"[^\d.]", "", raw)) > 0
    except ValueError:
        return False
