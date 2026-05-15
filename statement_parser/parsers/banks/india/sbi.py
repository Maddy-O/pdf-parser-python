"""
State Bank of India (SBI) statement parser.

Format: Txn Date | Value Date | Description | Ref No/Cheque No | Debit | Credit | Balance
Indian date format: DD/MM/YYYY
Currency: INR
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

_HEADER_KEYWORDS = ["txn date", "debit", "credit", "balance"]


class SbiParser(BaseParser):
    BANK_CODE = BankCode.SBI
    DEFAULT_CURRENCY = Currency.INR

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_sbi_cols(table[h])
                rows.extend(_parse(table, h, col_map, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        opening = self._find_amount_in_text(text, ["opening balance"])
        closing = self._find_amount_in_text(text, ["closing balance", "current balance"])
        meta = self._default_metadata()
        meta.account_number_masked = _sbi_account(text)
        meta.account_holder = _sbi_holder(text)
        meta.period = _sbi_period(text)
        return opening, closing, meta


def _detect_sbi_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if cell in ("txn date", "date") and "value" not in cell:
            m.setdefault("date", i)
        elif "value" in cell and "date" in cell:
            m.setdefault("value_date", i)
        elif any(k in cell for k in ["description", "narration", "particulars", "remarks"]):
            m.setdefault("desc", i)
        elif "ref" in cell or "cheque" in cell:
            m.setdefault("ref", i)
        elif "debit" in cell or "withdrawal" in cell:
            m.setdefault("debit", i)
        elif "credit" in cell or "deposit" in cell:
            m.setdefault("credit", i)
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
        if not date:
            continue
        desc = get("desc") or ""
        if not desc:
            continue
        if any(k in desc.upper() for k in ["OPENING BALANCE", "CLOSING BALANCE", "TOTAL", "BY TRANSFER"]):
            pass  # Allow "BY TRANSFER" but skip summaries
        if any(k in desc.upper() for k in ["OPENING BALANCE", "CLOSING BALANCE"]):
            continue

        d, c = clean_amount(get("debit")), clean_amount(get("credit"))
        if d and _pos(get("debit")):
            amt, typ = d, "DEBIT"
        elif c and _pos(get("credit")):
            amt, typ = c, "CREDIT"
        else:
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


def _pos(raw):
    if not raw:
        return False
    import re
    try:
        return float(re.sub(r"[^\d.]", "", raw)) > 0
    except Exception:
        return False


def _sbi_account(text):
    m = re.search(r"account\s+(?:no|number)[.:\s]*(\d+)", text, re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"****{num[-4:]}"
    return None


def _sbi_holder(text):
    m = re.search(r"(?:account\s+holder|name)[:\s]+([A-Z][A-Z\s]{2,40})", text, re.IGNORECASE)
    return m.group(1).strip().title() if m else None


def _sbi_period(text):
    m = re.search(r"(?:from|period)[:\s]+(\d{2}/\d{2}/\d{4})\s+(?:to|–|-)\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1), "dmy"), to_date=parse_date(m.group(2), "dmy"))
    return None
