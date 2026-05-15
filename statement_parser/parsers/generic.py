"""
Generic bank statement parser.
Heuristic fallback for any bank statement where no specific parser exists.

Strategy:
- Auto-detect columns by header keywords
- Handle both split (Debit/Credit) and single signed-amount formats
- Infer transaction type from amount sign or column
"""
import pdfplumber
from statement_parser.enums import BankCode, Currency
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount, is_negative_amount, detect_currency
from statement_parser.utils.text import detect_payment_mode, extract_reference

_HEADER_KEYWORDS = ["date", "description", "amount", "debit", "credit", "withdrawal", "deposit"]


class GenericParser(BaseParser):
    """Heuristic fallback parser for unrecognised bank statements."""
    BANK_CODE = BankCode.GENERIC
    DEFAULT_CURRENCY = Currency.UNKNOWN

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        full_text = self._full_text(pdf)
        currency = detect_currency(full_text)

        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_cols(table[h])
                rows.extend(_parse_table(table, h, col_map, currency, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        currency = detect_currency(text)
        meta = self._default_metadata()
        meta.currency = currency
        opening = self._find_amount_in_text(text, ["opening balance", "beginning balance", "previous balance"])
        closing = self._find_amount_in_text(text, ["closing balance", "ending balance", "available balance"])
        return opening, closing, meta


def _detect_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if not cell:
            continue
        # Date columns — prefer transaction date over value/post date
        if "date" in cell and "value" not in cell and "post" not in cell and "due" not in cell:
            m.setdefault("date", i)
        elif "post" in cell and "date" in cell:
            m.setdefault("post_date", i)
        elif "value" in cell and "date" in cell:
            m.setdefault("value_date", i)
        # Description
        elif any(k in cell for k in ["description", "narration", "particular", "details", "memo", "remarks", "narrative"]):
            m.setdefault("desc", i)
        # Split debit/credit
        elif any(k in cell for k in ["debit", "withdrawal", "paid out", "dr"]):
            m.setdefault("debit", i)
        elif any(k in cell for k in ["credit", "deposit", "paid in", "cr"]):
            m.setdefault("credit", i)
        # Single amount
        elif "amount" in cell:
            m.setdefault("amount", i)
        # Balance
        elif "balance" in cell:
            m.setdefault("balance", i)
    return m


def _parse_table(table, header_idx, col_map, currency, warnings):
    rows = []
    has_split = "debit" in col_map and "credit" in col_map
    has_amount = "amount" in col_map

    if not has_split and not has_amount:
        return rows  # Cannot determine amounts without a column

    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        def get(k):
            i = col_map.get(k)
            return str(row[i] or "").strip() or None if i is not None and i < len(row) else None

        date = parse_date(get("date"), "auto")
        if not date:
            continue
        desc = get("desc") or ""
        if not desc:
            continue

        # Skip running totals / summary rows
        if any(k in desc.upper() for k in ["OPENING BALANCE", "CLOSING BALANCE", "TOTAL", "BROUGHT FORWARD"]):
            continue

        if has_split:
            d, c = clean_amount(get("debit")), clean_amount(get("credit"))
            if d and _is_positive(get("debit")):
                amt, typ = d, "DEBIT"
            elif c and _is_positive(get("credit")):
                amt, typ = c, "CREDIT"
            else:
                continue
        else:
            raw = get("amount")
            amt = clean_amount(raw)
            if not amt:
                continue
            typ = "DEBIT" if is_negative_amount(raw or "") else "CREDIT"

        rows.append(TransactionRow(
            transaction_date=date,
            value_date=get("value_date"),
            raw_description=desc,
            amount=amt,
            transaction_type=typ,
            currency=currency,
            balance_after=clean_amount(get("balance")),
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc),
        ))
    return rows


def _is_positive(raw):
    if not raw:
        return False
    import re
    try:
        return float(re.sub(r"[^\d.]", "", raw)) > 0
    except Exception:
        return False
