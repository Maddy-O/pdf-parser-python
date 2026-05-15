"""
Emirates NBD (UAE) statement parser.

Format: Date | Description | Reference | Debit | Credit | Balance
UAE date format: DD/MM/YYYY or DD-MM-YYYY
Currency: AED (primary), also USD accounts
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

_HEADER_KEYWORDS = ["date", "description", "debit", "credit", "balance"]


class EmiratesNBDParser(BaseParser):
    BANK_CODE = BankCode.EMIRATES_NBD
    DEFAULT_CURRENCY = Currency.AED

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        full_text = self._full_text(pdf)
        currency = detect_currency(full_text) if detect_currency(full_text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY

        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_enbd_cols(table[h])
                rows.extend(_parse(table, h, col_map, currency, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        currency = detect_currency(text) if detect_currency(text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY
        opening = self._find_amount_in_text(text, ["opening balance", "brought forward"])
        closing = self._find_amount_in_text(text, ["closing balance", "carried forward"])
        meta = self._default_metadata()
        meta.currency = currency
        meta.account_number_masked = _enbd_account(text)
        meta.period = _enbd_period(text)
        return opening, closing, meta


def _detect_enbd_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell and "value" not in cell:
            m.setdefault("date", i)
        elif any(k in cell for k in ["description", "narration", "details", "particulars"]):
            m.setdefault("desc", i)
        elif "ref" in cell:
            m.setdefault("ref", i)
        elif "debit" in cell or "withdrawal" in cell or "dr" == cell:
            m.setdefault("debit", i)
        elif "credit" in cell or "deposit" in cell or "cr" == cell:
            m.setdefault("credit", i)
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
        if any(k in desc.upper() for k in ["OPENING BALANCE", "CLOSING BALANCE", "TOTAL"]):
            continue

        d, c = clean_amount(get("debit")), clean_amount(get("credit"))
        if d and _pos(get("debit")):
            amt, typ = d, "DEBIT"
        elif c and _pos(get("credit")):
            amt, typ = c, "CREDIT"
        else:
            continue

        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=typ, currency=currency,
            balance_after=clean_amount(get("balance")),
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc) or get("ref"),
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


def _enbd_account(text):
    m = re.search(r"account\s+(?:no|number)[.:\s]*(\d+)", text, re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"****{num[-4:]}"
    return None


def _enbd_period(text):
    m = re.search(r"(?:from|period)[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})\s+(?:to|–|-)\s+(\d{2}[/-]\d{2}[/-]\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1), "dmy"), to_date=parse_date(m.group(2), "dmy"))
    return None
