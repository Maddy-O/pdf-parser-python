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

# Axis Bank columns: Tran Date | CHQNO | PARTICULARS | DR | CR | BAL
_HEADER_KEYWORDS = ["tran date", "particulars", "dr", "cr", "bal"]


class AxisParser(BaseParser):
    """Parser for Axis Bank account statements."""

    BANK_NAME = "AXIS"

    def _extract_transactions(
        self, pdf: pdfplumber.PDF, warnings: list[str]
    ) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                header_idx = self._find_header_row(table, _HEADER_KEYWORDS)
                if header_idx is None:
                    header_idx = self._find_header_row(
                        table, ["date", "particulars", "debit", "credit", "balance"]
                    )
                if header_idx is None:
                    continue
                col_map = _detect_axis_columns(table[header_idx])
                rows.extend(_parse_axis_table(table, header_idx, col_map, warnings))
        return rows

    def _extract_metadata(
        self, pdf: pdfplumber.PDF
    ) -> tuple[str | None, str | None, StatementPeriod | None]:
        text = " ".join(p.extract_text() or "" for p in pdf.pages)
        opening = _axis_balance(text, ["opening balance", "op bal"])
        closing = _axis_balance(text, ["closing balance", "cl bal"])
        period = _axis_period(text)
        return opening, closing, period


def _detect_axis_columns(header_row: list[str | None]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        c = str(cell or "").strip().lower()
        if "tran date" in c or ("date" in c and "value" not in c):
            mapping.setdefault("date", idx)
        elif "chqno" in c or "chq" in c or "ref" in c:
            mapping.setdefault("ref", idx)
        elif "particulars" in c or "description" in c or "narration" in c:
            mapping.setdefault("desc", idx)
        elif c in ("dr", "debit", "dr amt", "withdrawal"):
            mapping.setdefault("debit", idx)
        elif c in ("cr", "credit", "cr amt", "deposit"):
            mapping.setdefault("credit", idx)
        elif c in ("bal", "balance", "closing balance"):
            mapping.setdefault("balance", idx)
    return mapping


def _parse_axis_table(
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
        if not desc:
            continue
        if any(kw in desc.upper() for kw in ["OPENING BALANCE", "CLOSING BALANCE"]):
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


def _axis_balance(text: str, labels: list[str]) -> str | None:
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


def _axis_period(text: str) -> StatementPeriod | None:
    m = re.search(
        r"from[:\s]+(\d{2}-\d{2}-\d{4})\s+to[:\s]+(\d{2}-\d{2}-\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        from app.parsers.base import parse_date
        return StatementPeriod(
            from_date=parse_date(m.group(1)),
            to_date=parse_date(m.group(2)),
        )
    return None
