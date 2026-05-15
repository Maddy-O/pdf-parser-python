"""
Generic credit card statement parser.
Used as fallback for any credit card statement where no bank-specific parser exists.

Credit card statements differ from bank statements:
- Purchases = DEBIT (money you owe)
- Payments/Refunds = CREDIT (reduces your balance)
- Amounts are usually unsigned; type inferred from section context
- Statement metadata includes credit limit, minimum payment, due date
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

_HEADER_KEYWORDS = ["date", "description", "amount"]
_CREDIT_SIGNALS = ["PAYMENT", "CREDIT", "REFUND", "CASHBACK", "REVERSAL", "ADJUSTMENT CR"]
_DEBIT_SIGNALS  = ["PURCHASE", "FEE", "INTEREST", "CHARGE", "CASH ADVANCE"]


class GenericCreditCardParser(BaseParser):
    BANK_CODE = BankCode.GENERIC
    DEFAULT_CURRENCY = Currency.UNKNOWN

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        currency = detect_currency(self._full_text(pdf))

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
        meta = StatementMetadata(
            bank_code=self.BANK_CODE.value,
            statement_type=StatementType.CREDIT_CARD,
            currency=currency,
        )
        meta.credit_limit = self._find_amount_in_text(text, ["credit limit"])
        meta.available_credit = self._find_amount_in_text(text, ["available credit", "available limit"])
        meta.minimum_payment = self._find_amount_in_text(text, ["minimum payment due", "minimum amount due", "min payment"])
        meta.total_amount_due = self._find_amount_in_text(text, ["total amount due", "statement balance", "new balance", "outstanding balance"])
        m = re.search(r"payment\s+due\s+(?:date|by)[:\s]+(\d{1,2}[/\-\s]\w+[/\-\s]\d{2,4})", text, re.IGNORECASE)
        if m:
            meta.payment_due_date = parse_date(m.group(1).strip(), "auto")
        opening = self._find_amount_in_text(text, ["opening balance", "previous balance", "last statement balance"])
        closing = self._find_amount_in_text(text, ["closing balance", "new balance", "statement balance"])
        return opening, closing, meta


def _detect_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell and "value" not in cell and "post" not in cell:
            m.setdefault("date", i)
        elif any(k in cell for k in ["description", "details", "narration", "particulars", "memo"]):
            m.setdefault("desc", i)
        elif "debit" in cell or " dr" in cell:
            m.setdefault("debit", i)
        elif "credit" in cell or " cr" in cell:
            m.setdefault("credit", i)
        elif "amount" in cell:
            m.setdefault("amount", i)
    return m


def _parse_table(table, header_idx, col_map, currency, warnings):
    rows = []
    has_split = "debit" in col_map and "credit" in col_map
    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        def get(k):
            i = col_map.get(k)
            return str(row[i] or "").strip() or None if i is not None and i < len(row) else None
        date = parse_date(get("date"), "auto")
        if not date: continue
        desc = get("desc") or ""
        if not desc: continue
        if has_split:
            d, c = clean_amount(get("debit")), clean_amount(get("credit"))
            if d and _pos(get("debit")): amt, typ = d, "DEBIT"
            elif c and _pos(get("credit")): amt, typ = c, "CREDIT"
            else: continue
        else:
            raw = get("amount")
            amt = clean_amount(raw)
            if not amt: continue
            # Infer from description keywords
            desc_upper = desc.upper()
            if any(s in desc_upper for s in _CREDIT_SIGNALS):
                typ = "CREDIT"
            elif any(s in desc_upper for s in _DEBIT_SIGNALS):
                typ = "DEBIT"
            else:
                typ = "DEBIT"  # Default: purchases are most common
        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=typ, currency=currency,
            payment_mode=detect_payment_mode(desc),
            reference_number=extract_reference(desc),
        ))
    return rows

def _pos(raw):
    if not raw: return False
    import re
    try: return float(re.sub(r"[^\d.]", "", raw)) > 0
    except: return False
