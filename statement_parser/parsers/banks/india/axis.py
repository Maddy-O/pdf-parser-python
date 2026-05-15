"""
Axis Bank statement parser.

Axis Bank uses two distinct table layouts:

  Format A (older / net-banking PDF):
    Tran Date | CHQNO | PARTICULARS | DR | CR | BAL

  Format B (newer / passbook-style):
    Date | Transaction Details | Chq/Ref No | Value Dt | Withdrawal (Dr) | Deposit (Cr) | Balance

Both are handled by a single grouped keyword definition — each tuple covers all
known column name variants for that slot, so either format matches in one pass.
"""
import logging
import re

import pdfplumber

from statement_parser.enums import BankCode, Currency
from statement_parser.models.statement import StatementPeriod
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.currency import clean_amount
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.text import detect_payment_mode, extract_reference

logger = logging.getLogger(__name__)

# Each tuple covers all known column name variants for that slot across both formats.
# A row matches if it contains at least one word from each group.
_HEADER_KEYWORDS: list[str | tuple[str, ...]] = [
    ("date", "tran date"),                      # date column
    ("dr", "debit", "withdrawal"),              # debit column
    ("cr", "credit", "deposit"),               # credit column
]


class AxisParser(BaseParser):
    BANK_CODE = BankCode.AXIS
    DEFAULT_CURRENCY = Currency.INR

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                logger.debug("No tables found on page %d", page.page_number)
                continue

            for table in tables:
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    logger.debug(
                        "No matching header in table on page %d — skipping. "
                        "Header row cells: %s",
                        page.page_number,
                        [str(c or "").strip() for c in (table[0] if table else [])],
                    )
                    continue

                col_map = _detect_axis_cols(table[h])
                logger.debug(
                    "Header found at row %d on page %d. Column map: %s",
                    h, page.page_number, col_map,
                )

                if "date" not in col_map or ("debit" not in col_map and "credit" not in col_map):
                    logger.debug(
                        "Column map missing required columns (date/debit/credit) — skipping table"
                    )
                    warnings.append(
                        f"Table on page {page.page_number} matched a header but column "
                        "mapping is incomplete — skipped."
                    )
                    continue

                page_rows = _parse(table, h, col_map, warnings)
                logger.debug(
                    "Extracted %d transactions from page %d", len(page_rows), page.page_number
                )
                rows.extend(page_rows)

        return rows

    def _extract_metadata(self, pdf: pdfplumber.PDF):
        text = self._full_text(pdf)
        opening = self._find_amount_in_text(text, ["opening balance", "opening bal", "op bal"])
        closing = self._find_amount_in_text(text, ["closing balance", "closing bal", "cl bal"])

        # Axis Bank often embeds opening/closing balance as rows inside the transaction
        # table rather than as free-form text, so extract_text() misses them.
        if not opening or not closing:
            opening, closing = _balance_from_tables(pdf, opening, closing)

        meta = self._default_metadata()
        meta.account_number_masked = _axis_account(text)
        meta.account_holder = _axis_holder(text)
        meta.period = _axis_period(text)
        return opening, closing, meta


def _detect_axis_cols(header_row: list) -> dict[str, int]:
    m: dict[str, int] = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()

        if not cell:
            continue

        # Date column — matches "tran date", "date" but NOT "value dt"
        if "date" in cell and "value" not in cell:
            m.setdefault("date", i)

        # Value date column
        elif "value" in cell and ("dt" in cell or "date" in cell):
            m.setdefault("value_date", i)

        # Description column
        elif any(k in cell for k in ["description", "transaction details", "narration", "particulars"]):
            m.setdefault("desc", i)

        # Cheque / reference column
        elif "chq" in cell or ("ref" in cell and "no" in cell):
            m.setdefault("ref", i)

        # Debit / withdrawal column — matches "dr", "debit", "(dr)", "withdrawal"
        elif cell in ("dr",) or "debit" in cell or "(dr)" in cell or "withdrawal" in cell:
            m.setdefault("debit", i)

        # Credit / deposit column — matches "cr", "credit", "(cr)", "deposit"
        elif cell in ("cr",) or "credit" in cell or "(cr)" in cell or "deposit" in cell:
            m.setdefault("credit", i)

        # Balance column — matches "bal", "balance"
        elif cell in ("bal",) or "balance" in cell:
            m.setdefault("balance", i)

    return m


def _parse(table: list, header_idx: int, col_map: dict[str, int], warnings: list[str]) -> list[TransactionRow]:
    rows: list[TransactionRow] = []

    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        def get(k: str) -> str | None:
            i = col_map.get(k)
            if i is None or i >= len(row):
                return None
            return str(row[i] or "").strip() or None

        date_raw = get("date")
        date = parse_date(date_raw, "dmy")
        if not date:
            logger.debug("Skipping row — unparseable date: %r", date_raw)
            continue

        desc = get("desc") or ""
        if not desc:
            continue
        if any(k in desc.upper() for k in ["OPENING BALANCE", "CLOSING BALANCE", "TOTAL"]):
            continue

        debit_raw = get("debit")
        credit_raw = get("credit")
        d = clean_amount(debit_raw)
        c = clean_amount(credit_raw)

        if d and _pos(debit_raw):
            amt, typ = d, "DEBIT"
        elif c and _pos(credit_raw):
            amt, typ = c, "CREDIT"
        else:
            logger.debug(
                "Skipping row on %s — no valid debit or credit: debit=%r credit=%r",
                date, debit_raw, credit_raw,
            )
            continue

        rows.append(TransactionRow(
            transaction_date=date,
            value_date=get("value_date"),
            raw_description=desc,
            amount=amt,
            transaction_type=typ,
            currency=Currency.INR,
            balance_after=clean_amount(get("balance")),
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc) or get("ref"),
        ))

    return rows


def _balance_from_tables(
    pdf: pdfplumber.PDF,
    opening: str | None,
    closing: str | None,
) -> tuple[str | None, str | None]:
    """
    Scan every table on every page for rows whose description cell contains
    "OPENING BALANCE" or "CLOSING BALANCE", and read the balance column value.
    Returns the (possibly updated) opening and closing balance pair.
    """
    for page in pdf.pages:
        for table in page.extract_tables():
            h = AxisParser._find_header_row(table, _HEADER_KEYWORDS)
            if h is None:
                continue
            col_map = _detect_axis_cols(table[h])
            bal_idx = col_map.get("balance")
            desc_idx = col_map.get("desc")
            if bal_idx is None:
                continue

            for row in table[h + 1:]:
                if not row or bal_idx >= len(row):
                    continue
                desc = str(row[desc_idx] or "").upper() if desc_idx is not None and desc_idx < len(row) else ""
                bal = clean_amount(str(row[bal_idx] or "").strip())
                if not bal:
                    continue
                if "OPENING BALANCE" in desc and not opening:
                    opening = bal
                    logger.debug("Opening balance found in table: %s", opening)
                elif "CLOSING BALANCE" in desc and not closing:
                    closing = bal
                    logger.debug("Closing balance found in table: %s", closing)

    return opening, closing


def _pos(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        return float(re.sub(r"[^\d.]", "", raw)) > 0
    except Exception:
        return False


def _axis_account(text: str) -> str | None:
    m = re.search(r"account\s+(?:no|number)[.:\s]*(\d{6,20})", text, re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"****{num[-4:]}"
    return None


def _axis_holder(text: str) -> str | None:
    m = re.search(
        r"(?:customer|account holder)\s+name[:\s]+([A-Z][A-Z\s]{2,40})",
        text,
        re.IGNORECASE,
    )
    return m.group(1).strip().title() if m else None


def _axis_period(text: str) -> StatementPeriod | None:
    m = re.search(
        r"(?:statement period|from)[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})"
        r"\s+(?:to|–|-)\s+(\d{2}[/-]\d{2}[/-]\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        return StatementPeriod(
            from_date=parse_date(m.group(1), "dmy"),
            to_date=parse_date(m.group(2), "dmy"),
        )
    return None
