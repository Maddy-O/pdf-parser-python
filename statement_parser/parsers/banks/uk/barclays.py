"""
Barclays Bank UK statement parser.

Format: Date | Payment Type | Description | Paid Out | Paid In | Balance
UK date format: DD/MM/YYYY
Currency: GBP
"""
import re
import pdfplumber
from statement_parser.enums import BankCode, Currency
from statement_parser.models.statement import StatementPeriod
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount
from statement_parser.utils.text import detect_payment_mode, extract_reference

_HEADER_KEYWORDS = ["date", "paid out", "paid in", "balance"]


class BarclaysParser(BaseParser):
    BANK_CODE = BankCode.BARCLAYS
    DEFAULT_CURRENCY = Currency.GBP

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_barclays_cols(table[h])
                rows.extend(_parse(table, h, col_map, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        opening = self._find_amount_in_text(text, ["opening balance", "balance brought forward"])
        closing = self._find_amount_in_text(text, ["closing balance", "balance carried forward"])
        meta = self._default_metadata()
        meta.account_number_masked = _barclays_account(text)
        meta.period = _barclays_period(text)
        return opening, closing, meta


def _detect_barclays_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell and "value" not in cell:
            m.setdefault("date", i)
        elif "payment type" in cell or "type" == cell:
            m.setdefault("type", i)
        elif "description" in cell or "details" in cell or "narrative" in cell:
            m.setdefault("desc", i)
        elif "paid out" in cell or "debit" in cell or "withdrawal" in cell:
            m.setdefault("paid_out", i)
        elif "paid in" in cell or "credit" in cell or "deposit" in cell:
            m.setdefault("paid_in", i)
        elif "balance" in cell:
            m.setdefault("balance", i)
    return m


def _parse(table, header_idx, col_map, warnings):
    rows = []
    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        def get(k):
            i = col_map.get(k)
            return str(row[i] or "").strip() or None if i is not None and i < len(row) else None
        date = parse_date(get("date"), "dmy")
        if not date: continue
        desc = get("desc") or ""
        if not desc: continue
        out = clean_amount(get("paid_out"))
        inp = clean_amount(get("paid_in"))
        if out and _pos(get("paid_out")):
            amt, typ = out, "DEBIT"
        elif inp and _pos(get("paid_in")):
            amt, typ = inp, "CREDIT"
        else:
            continue
        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=typ, currency=Currency.GBP,
            balance_after=clean_amount(get("balance")),
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc),
        ))
    return rows


def _pos(raw):
    if not raw: return False
    import re
    try: return float(re.sub(r"[^\d.]", "", raw)) > 0
    except: return False

def _barclays_account(text):
    m = re.search(r"account\s+(?:number|no)[.:\s]*(\d{8})", text, re.IGNORECASE)
    return f"****{m.group(1)[-4:]}" if m else None

def _barclays_period(text):
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1)), to_date=parse_date(m.group(2)))
    return None
