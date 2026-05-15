import logging
import re

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

# Keywords that identify a row as a transaction header
_DATE_KEYWORDS = {"date", "dt", "tran date", "txn date", "transaction date"}
_DEBIT_KEYWORDS = {"debit", "dr", "withdrawal", "withdrawal amt", "dr amt"}
_CREDIT_KEYWORDS = {"credit", "cr", "deposit", "deposit amt", "cr amt"}
_DESC_KEYWORDS = {"description", "narration", "particulars", "details", "remarks"}
_BALANCE_KEYWORDS = {"balance", "bal", "closing balance"}


class GenericParser(BaseParser):
    """
    Heuristic parser that works without bank-specific knowledge.

    Strategy:
    1. Collect all tables from all pages via pdfplumber.
    2. For each table, look for a header row containing date + amount-like columns.
    3. Map columns to fields based on header cell content.
    4. Parse rows below the header.
    """

    BANK_NAME = "GENERIC"

    def _extract_transactions(
        self, pdf: pdfplumber.PDF, warnings: list[str]
    ) -> list[TransactionRow]:
        all_tables = self._collect_tables(pdf)
        if not all_tables:
            warnings.append("No tables found — PDF may be scanned or image-based")
            return []

        rows: list[TransactionRow] = []
        for table in all_tables:
            mapping = _detect_column_mapping(table)
            if mapping is None:
                continue
            header_idx, col_map = mapping
            rows.extend(_parse_table_rows(table, header_idx, col_map, warnings))

        return rows

    def _extract_metadata(
        self, pdf: pdfplumber.PDF
    ) -> tuple[str | None, str | None, StatementPeriod | None]:
        full_text = " ".join(
            page.extract_text() or "" for page in pdf.pages
        )
        opening = _find_balance_in_text(full_text, ["opening balance", "op bal", "opening bal"])
        closing = _find_balance_in_text(full_text, ["closing balance", "cl bal", "closing bal"])
        period = _find_statement_period(full_text)
        return opening, closing, period


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _detect_column_mapping(
    table: list[list[str | None]],
) -> tuple[int, dict[str, int]] | None:
    """
    Return (header_row_index, {field_name: column_index}) or None if this
    table does not look like a transaction table.
    """
    for row_idx, row in enumerate(table[:5]):  # header is usually in first 5 rows
        cells = [str(c or "").strip().lower() for c in row]
        joined = " | ".join(cells)

        has_date = any(kw in joined for kw in _DATE_KEYWORDS)
        has_amount = any(
            any(kw in c for kw in _DEBIT_KEYWORDS | _CREDIT_KEYWORDS)
            for c in cells
        )
        if not (has_date and has_amount):
            continue

        # Build column mapping
        col_map: dict[str, int] = {}
        for col_idx, cell in enumerate(cells):
            if any(kw in cell for kw in _DATE_KEYWORDS) and "date" not in col_map:
                col_map["date"] = col_idx
            elif "value" in cell and "date" in cell:
                col_map["value_date"] = col_idx
            elif any(kw in cell for kw in _DESC_KEYWORDS) and "desc" not in col_map:
                col_map["desc"] = col_idx
            elif any(kw in cell for kw in _DEBIT_KEYWORDS) and "debit" not in col_map:
                col_map["debit"] = col_idx
            elif any(kw in cell for kw in _CREDIT_KEYWORDS) and "credit" not in col_map:
                col_map["credit"] = col_idx
            elif any(kw in cell for kw in _BALANCE_KEYWORDS) and "balance" not in col_map:
                col_map["balance"] = col_idx
            elif "ref" in cell or "chq" in cell or "cheque" in cell:
                col_map["ref"] = col_idx

        if "date" in col_map and "desc" in col_map:
            return row_idx, col_map

    return None


def _parse_table_rows(
    table: list[list[str | None]],
    header_idx: int,
    col_map: dict[str, int],
    warnings: list[str],
) -> list[TransactionRow]:
    rows: list[TransactionRow] = []
    has_split_columns = "debit" in col_map and "credit" in col_map

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
        if not desc:
            continue

        if has_split_columns:
            debit_raw = get("debit")
            credit_raw = get("credit")
            debit = clean_amount(debit_raw)
            credit = clean_amount(credit_raw)
            if debit and _is_nonzero(debit_raw):
                amount, tx_type = debit, "DEBIT"
            elif credit and _is_nonzero(credit_raw):
                amount, tx_type = credit, "CREDIT"
            else:
                continue
        else:
            # Single amount column — infer type from description or balance direction
            amount_raw = get("debit") or get("credit")
            amount = clean_amount(amount_raw)
            if not amount:
                continue
            tx_type = "CREDIT" if "cr" in str(amount_raw or "").lower() else "DEBIT"

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


def _is_nonzero(raw: str | None) -> bool:
    if not raw:
        return False
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return float(cleaned) > 0
    except ValueError:
        return False


def _find_balance_in_text(text: str, labels: list[str]) -> str | None:
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


def _find_statement_period(text: str) -> StatementPeriod | None:
    # Match "From: 01/01/2025 To: 31/01/2025" or "01 Jan 2025 to 31 Jan 2025"
    m = re.search(
        r"from[:\s]+(\d{1,2}[\s/\-]\w+[\s/\-]\d{2,4})\s+to[:\s]+(\d{1,2}[\s/\-]\w+[\s/\-]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if m:
        return StatementPeriod(
            from_date=parse_date(m.group(1)),
            to_date=parse_date(m.group(2)),
        )
    return None
