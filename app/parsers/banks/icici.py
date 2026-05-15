import re
import logging

import pdfplumber

from app.models.response import TransactionRow, StatementPeriod
from app.parsers.base import (
    BaseParser,
    parse_date,
    clean_amount,
    detect_payment_mode,
    extract_reference,
)

logger = logging.getLogger(__name__)

# ICICI statement columns:
# S.No. | Transaction Date | Value Date | Description | Ref No./Cheque No. | Debit | Credit | Balance
_HEADER_KEYWORDS = ["transaction date", "description", "debit", "credit", "balance"]

_COL_TXN_DATE = 1
_COL_VALUE_DATE = 2
_COL_DESC = 3
_COL_REF = 4
_COL_DEBIT = 5
_COL_CREDIT = 6
_COL_BALANCE = 7


class IciciParser(BaseParser):
    """Parser for ICICI Bank account statements."""

    BANK_NAME = "ICICI"

    def _extract_transactions(
        self, pdf: pdfplumber.PDF, warnings: list[str]
    ) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                header_idx = self._find_header_row(table, _HEADER_KEYWORDS)
                if header_idx is None:
                    continue
                col_map = _detect_icici_columns(table[header_idx])
                rows.extend(_parse_icici_table(table, header_idx, col_map, warnings))
        return rows

    def _extract_metadata(
        self, pdf: pdfplumber.PDF
    ) -> tuple[str | None, str | None, StatementPeriod | None]:
        text = " ".join(p.extract_text() or "" for p in pdf.pages)
        opening = _find_icici_balance(text, ["opening balance", "op bal"])
        closing = _find_icici_balance(text, ["closing balance", "cl bal"])
        period = _find_icici_period(text)
        return opening, closing, period


def _detect_icici_columns(header_row: list[str | None]) -> dict[str, int]:
    """Flexible column detection so we handle ICICI format variations."""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        c = str(cell or "").strip().lower()
        if "transaction date" in c or ("date" in c and "value" not in c):
            mapping.setdefault("date", idx)
        elif "value date" in c or "value dt" in c:
            mapping["value_date"] = idx
        elif "description" in c or "narration" in c or "particulars" in c:
            mapping.setdefault("desc", idx)
        elif "ref" in c or "cheque" in c or "chq" in c:
            mapping.setdefault("ref", idx)
        elif "debit" in c or " dr" in c:
            mapping.setdefault("debit", idx)
        elif "credit" in c or " cr" in c:
            mapping.setdefault("credit", idx)
        elif "balance" in c or "bal" in c:
            mapping.setdefault("balance", idx)
    return mapping


def _parse_icici_table(
    table: list[list[str | None]],
    header_idx: int,
    col_map: dict[str, int],
    warnings: list[str],
) -> list[TransactionRow]:
    rows: list[TransactionRow] = []
    for row in table[header_idx + 1 :]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        def get(key: str) -> str | None:
            idx = col_map.get(key)
            if idx is None or idx >= len(row):
                return None
            return str(row[idx] or "").strip() or None

        date = parse_date(get("date"))
        if not date:
            continue

        desc = get("desc") or ""
        if not desc or any(
            kw in desc.upper()
            for kw in ["OPENING BALANCE", "CLOSING BALANCE", "TOTAL TRANSACTIONS"]
        ):
            continue

        debit = clean_amount(get("debit"))
        credit = clean_amount(get("credit"))

        if debit and _pos(get("debit")):
            amount, tx_type = debit, "DEBIT"
        elif credit and _pos(get("credit")):
            amount, tx_type = credit, "CREDIT"
        else:
            continue

        rows.append(
            TransactionRow(
                transaction_date=date,
                value_date=parse_date(get("value_date")),
                raw_description=desc,
                amount=amount,
                transaction_type=tx_type,
                reference_number=extract_reference(desc) or get("ref"),
                balance_after=clean_amount(get("balance")),
                payment_mode=detect_payment_mode(desc),
            )
        )
    return rows


def _pos(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        return float(re.sub(r"[^\d.]", "", raw)) > 0
    except ValueError:
        return False


def _find_icici_balance(text: str, labels: list[str]) -> str | None:
    lower = text.lower()
    for label in labels:
        idx = lower.find(label)
        if idx == -1:
            continue
        snippet = text[idx: idx + 60]
        m = re.search(r"[\d,]+\.\d{2}", snippet)
        if m:
            return clean_amount(m.group())
    return None


def _find_icici_period(text: str) -> StatementPeriod | None:
    m = re.search(
        r"from[:\s]+(\d{2}\s+\w{3}\s+\d{4})\s+to[:\s]+(\d{2}\s+\w{3}\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        from app.parsers.base import parse_date
        return StatementPeriod(
            from_date=parse_date(m.group(1).strip()),
            to_date=parse_date(m.group(2).strip()),
        )
    return None
