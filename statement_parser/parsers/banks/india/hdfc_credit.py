import re
import pdfplumber
from statement_parser.enums import BankCode, Currency, StatementType
from statement_parser.models.statement import StatementMetadata
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount
from statement_parser.utils.text import detect_payment_mode, extract_reference

# HDFC CC: Date | Description | Amount (single col, signed or CR/DR indicator)
_HEADER_KEYWORDS = ["date", "description", "amount"]


class HdfcCreditParser(BaseParser):
    """HDFC Bank credit card statement parser."""
    BANK_CODE = BankCode.HDFC
    DEFAULT_CURRENCY = Currency.INR

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                col_map = _detect_cols(table[h])
                rows.extend(_parse_cc_table(table, h, col_map, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        meta = self._default_cc_metadata()
        meta.credit_limit = self._find_amount_in_text(text, ["credit limit"])
        meta.available_credit = self._find_amount_in_text(text, ["available credit", "available limit"])
        meta.minimum_payment = self._find_amount_in_text(text, ["minimum amount due", "minimum payment due"])
        meta.total_amount_due = self._find_amount_in_text(text, ["total amount due", "outstanding balance"])
        # Due date
        m = re.search(r"payment\s+due\s+date[:\s]+(\d{1,2}[/\-]\w+[/\-]\d{2,4})", text, re.IGNORECASE)
        if m:
            meta.payment_due_date = parse_date(m.group(1))
        opening = self._find_amount_in_text(text, ["opening balance", "previous balance"])
        closing = self._find_amount_in_text(text, ["closing balance", "total outstanding"])
        return opening, closing, meta


def _detect_cols(header_row):
    m = {}
    for i, c in enumerate(header_row):
        cell = str(c or "").strip().lower()
        if "date" in cell and "value" not in cell:
            m.setdefault("date", i)
        elif any(k in cell for k in ["description", "narration", "particular", "details"]):
            m.setdefault("desc", i)
        elif "debit" in cell or " dr" in cell:
            m.setdefault("debit", i)
        elif "credit" in cell or " cr" in cell:
            m.setdefault("credit", i)
        elif "amount" in cell:
            m.setdefault("amount", i)
    return m


def _parse_cc_table(table, header_idx, col_map, warnings):
    rows = []
    has_split = "debit" in col_map and "credit" in col_map
    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        def get(k):
            i = col_map.get(k)
            return str(row[i] or "").strip() or None if i is not None and i < len(row) else None
        date = parse_date(get("date"))
        if not date: continue
        desc = get("desc") or ""
        if not desc: continue
        if any(k in desc.upper() for k in ["OPENING BALANCE", "CLOSING BALANCE", "TOTAL"]):
            continue
        if has_split:
            d, c = clean_amount(get("debit")), clean_amount(get("credit"))
            if d and _pos(get("debit")): amt, typ = d, "DEBIT"
            elif c and _pos(get("credit")): amt, typ = c, "CREDIT"
            else: continue
        else:
            raw = get("amount")
            amt = clean_amount(raw)
            if not amt: continue
            # HDFC CC: amount with "Cr" suffix = payment/credit
            typ = "CREDIT" if raw and "cr" in raw.lower() else "DEBIT"
        rows.append(TransactionRow(
            transaction_date=date, raw_description=desc, amount=amt,
            transaction_type=typ, currency=Currency.INR,
            reference_number=extract_reference(desc),
            payment_mode=detect_payment_mode(desc),
        ))
    return rows

def _pos(raw):
    if not raw: return False
    import re
    try: return float(re.sub(r"[^\d.]", "", raw)) > 0
    except: return False
