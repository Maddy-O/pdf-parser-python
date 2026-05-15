"""
Wells Fargo Bank statement parser.

Wells Fargo PDF format:
- Date | Check # | Description | Deposits | Withdrawals | Ending Balance
US date format: MM/DD/YYYY
Currency: USD
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

_HEADER_KEYWORDS = ["date", "description", "deposits", "withdrawals"]


class WellsFargoParser(BaseParser):
    BANK_CODE = BankCode.WELLS_FARGO
    DEFAULT_CURRENCY = Currency.USD
    DATE_HINT = "mdy"

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_wf_cols(table[h])
                rows.extend(_parse(table, h, col_map, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        opening = self._find_amount_in_text(text, ["beginning balance", "opening balance"])
        closing = self._find_amount_in_text(text, ["ending balance", "closing balance"])
        meta = self._default_metadata()
        meta.period = _wf_period(text)
        meta.account_number_masked = _wf_account(text)
        return opening, closing, meta


def _detect_wf_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell:
            m.setdefault("date", i)
        elif "check" in cell:
            m.setdefault("check", i)
        elif any(k in cell for k in ["description", "memo", "transaction"]):
            m.setdefault("desc", i)
        elif "deposit" in cell or "credit" in cell:
            m.setdefault("credit", i)
        elif "withdrawal" in cell or "debit" in cell:
            m.setdefault("debit", i)
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

        date = parse_date(get("date"), "mdy")
        if not date:
            continue
        desc = get("desc") or ""
        if not desc:
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
            transaction_type=typ, currency=Currency.USD,
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


def _wf_period(text):
    m = re.search(r"(\w+\s+\d{1,2},?\s*\d{4})\s+(?:through|to|-)\s+(\w+\s+\d{1,2},?\s*\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1), "mdy"), to_date=parse_date(m.group(2), "mdy"))
    return None


def _wf_account(text):
    m = re.search(r"account\s+(?:number|ending\s+in)[:\s]*(\d{4})", text, re.IGNORECASE)
    return f"****{m.group(1)}" if m else None
