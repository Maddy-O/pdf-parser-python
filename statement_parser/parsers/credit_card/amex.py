"""
American Express credit card statement parser.

Amex PDF format:
- Sections: "New Charges" / "Payments and Credits" / "Fees and Interest"
- Columns: Date | Description | Amount
- Amounts are unsigned; section heading determines DEBIT/CREDIT
- Currency varies (USD, GBP, SGD, AED depending on card)
"""
import re
import pdfplumber
from statement_parser.enums import BankCode, Currency, StatementType
from statement_parser.models.statement import StatementMetadata
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount, detect_currency
from statement_parser.utils.text import detect_payment_mode, extract_reference

_DEBIT_SECTIONS  = {"NEW CHARGES", "CHARGES", "FEES", "INTEREST CHARGES", "FEES AND INTEREST"}
_CREDIT_SECTIONS = {"PAYMENTS AND CREDITS", "CREDITS", "PAYMENTS"}
_HEADER_KEYWORDS = ["date", "description", "amount"]


class AmexParser(BaseParser):
    BANK_CODE = BankCode.AMEX
    DEFAULT_CURRENCY = Currency.USD
    DATE_HINT = "mdy"

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        full_text = self._full_text(pdf)
        currency = detect_currency(full_text) if detect_currency(full_text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY
        current_type = "DEBIT"

        for page in pdf.pages:
            page_text = page.extract_text() or ""
            for line in page_text.split("\n"):
                upper = line.strip().upper()
                if any(s in upper for s in _DEBIT_SECTIONS):
                    current_type = "DEBIT"
                elif any(s in upper for s in _CREDIT_SECTIONS):
                    current_type = "CREDIT"

            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_amex_cols(table[h])
                rows.extend(_parse_amex_table(table, h, col_map, current_type, currency, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        currency = detect_currency(text) if detect_currency(text) != Currency.UNKNOWN else self.DEFAULT_CURRENCY
        meta = StatementMetadata(
            bank_code=self.BANK_CODE.value,
            statement_type=StatementType.CREDIT_CARD,
            currency=currency,
        )
        meta.credit_limit = self._find_amount_in_text(text, ["credit limit", "spending limit"])
        meta.minimum_payment = self._find_amount_in_text(text, ["minimum payment due", "minimum due"])
        meta.total_amount_due = self._find_amount_in_text(text, ["new balance", "total new balance", "amount due"])
        m = re.search(r"payment\s+due\s+(?:date|by)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})", text, re.IGNORECASE)
        if m:
            meta.payment_due_date = parse_date(m.group(1).strip(), "mdy")
        opening = self._find_amount_in_text(text, ["previous balance"])
        closing = self._find_amount_in_text(text, ["new balance", "total new balance"])
        return opening, closing, meta


def _detect_amex_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell:
            m.setdefault("date", i)
        elif any(k in cell for k in ["description", "details", "merchant", "memo"]):
            m.setdefault("desc", i)
        elif "amount" in cell:
            m.setdefault("amount", i)
    return m


def _parse_amex_table(table, header_idx, col_map, forced_type, currency, warnings):
    rows = []
    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        def get(k):
            i = col_map.get(k)
            return str(row[i] or "").strip() or None if i is not None and i < len(row) else None
        date = parse_date(get("date"), "mdy")
        if not date: continue
        desc = get("desc") or ""
        if not desc: continue
        amt = clean_amount(get("amount"))
        if not amt: continue
        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=forced_type, currency=currency,
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc),
        ))
    return rows
