"""
HSBC UK statement parser.

Format: Date | Payment Type/Description | Paid Out | Paid In | Balance
UK date format: DD/MM/YYYY or DD Mon YYYY
Currency: GBP (UK), also HKD, USD, SGD for other HSBC regions — currency auto-detected.
"""
import re
import pdfplumber
from statement_parser.enums import BankCode, Currency
from statement_parser.models.statement import StatementPeriod
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount, detect_currency
from statement_parser.utils.text import detect_payment_mode, extract_reference

_HEADER_KEYWORDS = ["date", "paid out", "paid in", "balance"]


class HsbcParser(BaseParser):
    BANK_CODE = BankCode.HSBC_UK
    DEFAULT_CURRENCY = Currency.GBP

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        full_text = self._full_text(pdf)
        currency = detect_currency(full_text) if detect_currency(full_text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY

        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_hsbc_cols(table[h])
                rows.extend(_parse(table, h, col_map, currency, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        currency = detect_currency(text) if detect_currency(text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY
        opening = self._find_amount_in_text(text, ["opening balance", "balance brought forward"])
        closing = self._find_amount_in_text(text, ["closing balance", "balance carried forward"])
        meta = self._default_metadata()
        meta.currency = currency
        meta.account_number_masked = _hsbc_account(text)
        meta.period = _hsbc_period(text)
        return opening, closing, meta


def _detect_hsbc_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell and "value" not in cell:
            m.setdefault("date", i)
        elif any(k in cell for k in ["description", "details", "payment type", "transaction"]):
            m.setdefault("desc", i)
        elif "paid out" in cell or "withdrawal" in cell or "debit" in cell:
            m.setdefault("paid_out", i)
        elif "paid in" in cell or "deposit" in cell or "credit" in cell:
            m.setdefault("paid_in", i)
        elif "balance" in cell:
            m.setdefault("balance", i)
    return m


def _parse(table, header_idx, col_map, currency, warnings):
    rows = []
    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        def get(k):
            i = col_map.get(k)
            return str(row[i] or "").strip() or None if i is not None and i < len(row) else None

        date = parse_date(get("date"), "dmy")
        if not date:
            continue
        desc = get("desc") or ""
        if not desc:
            continue

        out, inp = clean_amount(get("paid_out")), clean_amount(get("paid_in"))
        if out and _pos(get("paid_out")):
            amt, typ = out, "DEBIT"
        elif inp and _pos(get("paid_in")):
            amt, typ = inp, "CREDIT"
        else:
            continue

        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=typ, currency=currency,
            balance_after=clean_amount(get("balance")),
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc),
        ))
    return rows


def _pos(raw):
    if not raw:
        return False
    import re
    try:
        return float(re.sub(r"[^\d.]", "", raw)) > 0
    except Exception:
        return False


def _hsbc_account(text):
    m = re.search(r"(?:account|sort code[^:]*)[:\s]+(\d{2}-?\d{2}-?\d{2}[:\s]+\d{8}|\d{8,16})", text, re.IGNORECASE)
    if m:
        num = re.sub(r"\D", "", m.group(1))
        return f"****{num[-4:]}"
    return None


def _hsbc_period(text):
    m = re.search(r"(\d{2}/\d{2}/\d{4}|\d{1,2}\s+\w+\s+\d{4})\s+(?:to|-)\s+(\d{2}/\d{2}/\d{4}|\d{1,2}\s+\w+\s+\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1), "dmy"), to_date=parse_date(m.group(2), "dmy"))
    return None
