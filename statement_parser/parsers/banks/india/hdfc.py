import re
import pdfplumber
from statement_parser.enums import BankCode, Currency
from statement_parser.models.statement import StatementMetadata, StatementPeriod
from statement_parser.models.transaction import TransactionRow
from statement_parser.parsers.base import BaseParser
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount
from statement_parser.utils.text import detect_payment_mode, extract_reference

# HDFC table: Date | Narration | Chq./Ref.No. | Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance
_HEADER_KEYWORDS = ["date", "narration", "withdrawal", "deposit", "closing balance"]
_COL = {"date": 0, "narration": 1, "ref": 2, "value_date": 3, "withdrawal": 4, "deposit": 5, "balance": 6}
_SKIP_NARRATIONS = {"OPENING BALANCE", "CLOSING BALANCE", "TOTAL"}


class HdfcParser(BaseParser):
    BANK_CODE = BankCode.HDFC
    DEFAULT_CURRENCY = Currency.INR

    def _extract_transactions(self, pdf: pdfplumber.PDF, warnings: list[str]) -> list[TransactionRow]:
        rows: list[TransactionRow] = []
        for page in pdf.pages:
            for table in page.extract_tables():
                h = self._find_header_row(table, _HEADER_KEYWORDS)
                if h is None:
                    continue
                rows.extend(_parse(table, h, warnings))
        return rows

    def _extract_metadata(self, pdf):
        text = self._full_text(pdf)
        opening = self._find_amount_in_text(text, ["opening balance"])
        closing = self._find_amount_in_text(text, ["closing balance"])
        period = _period(text)
        meta = self._default_metadata()
        meta.account_number_masked = _account_number(text)
        meta.account_holder = _holder_name(text)
        meta.period = period
        return opening, closing, meta


def _parse(table, header_idx, warnings):
    rows: list[TransactionRow] = []
    for row in table[header_idx + 1:]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        c = lambda k: str(row[_COL[k]] if _COL[k] < len(row) else "").strip() or None
        date = parse_date(c("date"))
        if not date:
            continue
        narr = c("narration") or ""
        if any(kw in narr.upper() for kw in _SKIP_NARRATIONS) or not narr:
            continue
        wd, dep = clean_amount(c("withdrawal")), clean_amount(c("deposit"))
        if wd and _pos(c("withdrawal")):
            amt, typ = wd, "DEBIT"
        elif dep and _pos(c("deposit")):
            amt, typ = dep, "CREDIT"
        else:
            continue
        rows.append(TransactionRow(
            transaction_date=date,
            value_date=parse_date(c("value_date")),
            raw_description=narr,
            amount=amt,
            transaction_type=typ,
            currency=Currency.INR,
            reference_number=extract_reference(narr) or c("ref"),
            balance_after=clean_amount(c("balance")),
            payment_mode=detect_payment_mode(narr),
        ))
    return rows


def _pos(raw):
    if not raw: return False
    import re
    try: return float(re.sub(r"[^\d.]", "", raw)) > 0
    except: return False

def _period(text):
    m = re.search(r"from\s+(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        return StatementPeriod(from_date=parse_date(m.group(1)), to_date=parse_date(m.group(2)))
    return None

def _account_number(text):
    m = re.search(r"account\s+(?:no|number)[.:\s]*([X*\d]{4,20})", text, re.IGNORECASE)
    return m.group(1) if m else None

def _holder_name(text):
    m = re.search(r"(?:name|customer)[:\s]+([A-Z][A-Z\s]{3,40})", text, re.IGNORECASE)
    return m.group(1).strip() if m else None
