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

# HDFC statement column headers (exact strings from the PDF)
_HEADER_KEYWORDS = ["date", "narration", "withdrawal", "deposit", "closing balance"]

# Column positions in HDFC table (0-indexed)
# Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance
_COL_DATE = 0
_COL_NARRATION = 1
_COL_REF = 2
_COL_VALUE_DATE = 3
_COL_WITHDRAWAL = 4
_COL_DEPOSIT = 5
_COL_BALANCE = 6


class HdfcParser(BaseParser):
    """
    Parser for HDFC Bank account statements.

    Expected table format (7 columns):
    Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance
    """

    BANK_NAME = "HDFC"

    def _extract_transactions(
        self, pdf: pdfplumber.PDF, warnings: list[str]
    ) -> list[TransactionRow]:
        rows: list[TransactionRow] = []

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                header_idx = self._find_header_row(table, _HEADER_KEYWORDS)
                if header_idx is None:
                    continue
                rows.extend(self._parse_table(table, header_idx, warnings))

        return rows

    def _extract_metadata(
        self, pdf: pdfplumber.PDF
    ) -> tuple[str | None, str | None, StatementPeriod | None]:
        full_text = " ".join(page.extract_text() or "" for page in pdf.pages)
        opening = _extract_hdfc_balance(full_text, "opening")
        closing = _extract_hdfc_balance(full_text, "closing")
        period = _extract_hdfc_period(full_text)
        return opening, closing, period

    def _parse_table(
        self,
        table: list[list[str | None]],
        header_idx: int,
        warnings: list[str],
    ) -> list[TransactionRow]:
        rows: list[TransactionRow] = []

        for row in table[header_idx + 1 :]:
            if not row or len(row) < 6:
                continue
            if all(c is None or str(c).strip() == "" for c in row):
                continue

            def cell(idx: int) -> str | None:
                v = row[idx] if idx < len(row) else None
                return str(v or "").strip() or None

            date = parse_date(cell(_COL_DATE))
            if not date:
                continue

            narration = cell(_COL_NARRATION) or ""
            # Skip summary rows: "Opening Balance", "Closing Balance", totals
            if any(
                kw in narration.upper()
                for kw in ["OPENING BALANCE", "CLOSING BALANCE", "TOTAL"]
            ):
                continue
            if not narration:
                continue

            withdrawal = clean_amount(cell(_COL_WITHDRAWAL))
            deposit = clean_amount(cell(_COL_DEPOSIT))

            if withdrawal and _nonzero(cell(_COL_WITHDRAWAL)):
                amount, tx_type = withdrawal, "DEBIT"
            elif deposit and _nonzero(cell(_COL_DEPOSIT)):
                amount, tx_type = deposit, "CREDIT"
            else:
                warnings.append(f"Row skipped — no amount: {narration[:40]}")
                continue

            ref_raw = cell(_COL_REF) or ""
            ref = extract_reference(narration) or (ref_raw if ref_raw else None)

            rows.append(
                TransactionRow(
                    transaction_date=date,
                    value_date=parse_date(cell(_COL_VALUE_DATE)),
                    raw_description=narration,
                    amount=amount,
                    transaction_type=tx_type,
                    reference_number=ref,
                    balance_after=clean_amount(cell(_COL_BALANCE)),
                    payment_mode=detect_payment_mode(narration),
                )
            )

        return rows


def _nonzero(raw: str | None) -> bool:
    if not raw:
        return False
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return float(cleaned) > 0
    except ValueError:
        return False


def _extract_hdfc_balance(text: str, balance_type: str) -> str | None:
    pattern = re.compile(
        rf"{balance_type}\s+balance[:\s]+([\d,]+\.\d{{2}})", re.IGNORECASE
    )
    m = pattern.search(text)
    if m:
        return clean_amount(m.group(1))
    return None


def _extract_hdfc_period(text: str) -> StatementPeriod | None:
    # "Statement of Account From 01/01/2025 To 31/01/2025"
    m = re.search(
        r"from\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        return StatementPeriod(
            from_date=parse_date(m.group(1)),
            to_date=parse_date(m.group(2)),
        )
    return None
