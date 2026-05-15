"""
DBS Bank Singapore statement parser.

Format: Date | Transaction Ref. No | Description | Withdrawals | Deposits | Available Balance
Singapore date format: DD/MM/YYYY or DD MMM YYYY
Currency: SGD (primary), also USD, HKD for multi-currency accounts
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

_HEADER_KEYWORDS = ["date", "withdrawals", "deposits", "balance"]


class DbsParser(BaseParser):
    BANK_CODE = BankCode.DBS
    DEFAULT_CURRENCY = Currency.SGD

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        full_text = self._full_text(pdf)
        currency = detect_currency(full_text) if detect_currency(full_text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY

        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_dbs_cols(table[h])
                rows.extend(_parse(table, h, col_map, currency, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        currency = detect_currency(text) if detect_currency(text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY
        opening = self._find_amount_in_text(text, ["opening balance", "balance brought forward"])
        closing = self._find_amount_in_text(text, ["closing balance", "available balance", "balance carried forward"])
        meta = self._default_metadata()
        meta.currency = currency
        meta.account_number_masked = _dbs_account(text)
        meta.period = _dbs_period(text)
        return opening, closing, meta


def _detect_dbs_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell and "value" not in cell:
            m.setdefault("date", i)
        elif "ref" in cell or "transaction ref" in cell:
            m.setdefault("ref", i)
        elif any(k in cell for k in ["description", "transaction details", "narration", "particulars"]):
            m.setdefault("desc", i)
        elif "withdrawal" in cell or "debit" in cell:
            m.setdefault("debit", i)
        elif "deposit" in cell or "credit" in cell:
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
        if any(k in desc.upper() for k in ["OPENING BALANCE", "CLOSING BALANCE", "BALANCE B/F", "BALANCE C/F"]):
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


def _dbs_account(text):
    m = re.search(r"account\s+(?:no|number)[.:\s]*(\d+)", text, re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"****{num[-4:]}"
    return None


def _dbs_period(text):
    m = re.search(r"(?:from|statement period)[:\s]+(\d{2}[/ ]\w+[/ ]\d{4}|\d{2}/\d{2}/\d{4})\s+(?:to|–|-)\s+(\d{2}[/ ]\w+[/ ]\d{4}|\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1), "dmy"), to_date=parse_date(m.group(2), "dmy"))
    return None
