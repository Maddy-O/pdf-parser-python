"""
Bank of America statement parser.

BoA PDF format:
- Bank account: Date | Description | Amount (signed: negative = debit)
- Credit card: separate "Payments and Other Credits" / "Purchases and Adjustments" sections
US date format: MM/DD/YYYY
Currency: USD
"""
import re
import pdfplumber
from statement_parser.enums import BankCode, Currency, StatementType
from statement_parser.models.statement import StatementMetadata, StatementPeriod
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount, is_negative_amount
from statement_parser.utils.text import detect_payment_mode, extract_reference

_HEADER_KEYWORDS = ["date", "description", "amount"]
_CC_CREDIT_SECTIONS = {"PAYMENTS AND OTHER CREDITS", "PAYMENTS & OTHER CREDITS", "CREDITS"}
_CC_DEBIT_SECTIONS  = {"PURCHASES AND ADJUSTMENTS", "PURCHASES", "TRANSACTIONS", "OTHER FEES"}


class BankOfAmericaParser(BaseParser):
    """BoA checking/savings account parser — signed amounts."""
    BANK_CODE = BankCode.BANK_OF_AMERICA
    DEFAULT_CURRENCY = Currency.USD
    DATE_HINT = "mdy"

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_cols(table[h])
                rows.extend(_parse_signed(table, h, col_map, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        opening = self._find_amount_in_text(text, ["beginning balance", "opening balance"])
        closing = self._find_amount_in_text(text, ["ending balance", "closing balance"])
        meta = self._default_metadata()
        meta.period = _boa_period(text)
        meta.account_number_masked = _boa_account(text)
        return opening, closing, meta


class BankOfAmericaCreditParser(BaseParser):
    """BoA credit card statement parser — section-based."""
    BANK_CODE = BankCode.BANK_OF_AMERICA
    DEFAULT_CURRENCY = Currency.USD
    DATE_HINT = "mdy"

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        current_type = "DEBIT"

        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                upper = line.strip().upper()
                if any(s in upper for s in _CC_CREDIT_SECTIONS):
                    current_type = "CREDIT"
                elif any(s in upper for s in _CC_DEBIT_SECTIONS):
                    current_type = "DEBIT"

            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_cols(table[h])
                rows.extend(_parse_cc(table, h, col_map, current_type, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        meta = StatementMetadata(
            bank_code=self.BANK_CODE.value,
            statement_type=StatementType.CREDIT_CARD,
            currency=Currency.USD,
        )
        meta.credit_limit = self._find_amount_in_text(text, ["credit limit"])
        meta.minimum_payment = self._find_amount_in_text(text, ["minimum payment due", "minimum payment"])
        meta.total_amount_due = self._find_amount_in_text(text, ["new balance", "statement balance"])
        opening = self._find_amount_in_text(text, ["previous balance"])
        closing = self._find_amount_in_text(text, ["new balance"])
        return opening, closing, meta


def _detect_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell and "post" not in cell:
            m.setdefault("date", i)
        elif "post" in cell and "date" in cell:
            m.setdefault("post_date", i)
        elif any(k in cell for k in ["description", "details", "memo", "transaction"]):
            m.setdefault("desc", i)
        elif "amount" in cell:
            m.setdefault("amount", i)
    return m


def _parse_signed(table, header_idx, col_map, warnings):
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
        raw_amt = get("amount")
        amt = clean_amount(raw_amt)
        if not amt:
            continue
        typ = "DEBIT" if is_negative_amount(raw_amt or "") else "CREDIT"
        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=typ, currency=Currency.USD,
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc),
        ))
    return rows


def _parse_cc(table, header_idx, col_map, forced_type, warnings):
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
        amt = clean_amount(get("amount"))
        if not amt:
            continue
        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=forced_type, currency=Currency.USD,
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc),
        ))
    return rows


def _boa_period(text):
    m = re.search(r"(\w+\s+\d{1,2},?\s*\d{4})\s+(?:through|to|-)\s+(\w+\s+\d{1,2},?\s*\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1), "mdy"), to_date=parse_date(m.group(2), "mdy"))
    return None


def _boa_account(text):
    m = re.search(r"account\s+(?:number|ending)[:\s#]*(\d{4})", text, re.IGNORECASE)
    return f"****{m.group(1)}" if m else None
