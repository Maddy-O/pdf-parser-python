import re
import logging
from abc import ABC, abstractmethod
from io import BytesIO
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pdfplumber

from app.models.response import ParseResponse, TransactionRow, StatementPeriod
from app.utils.balance_validator import validate_balance

logger = logging.getLogger(__name__)

# Date formats tried in order when parsing raw date strings from bank statements
_DATE_FORMATS = [
    "%d/%m/%Y", "%d/%m/%y",         # 15/01/2025 or 15/01/25
    "%d-%m-%Y", "%d-%m-%y",          # 15-01-2025
    "%d %b %Y", "%d-%b-%Y",          # 15 Jan 2025 or 15-Jan-2025
    "%d %B %Y",                       # 15 January 2025
    "%Y-%m-%d",                       # ISO 2025-01-15
    "%d %b %y",                       # 15 Jan 25
]

# Payment mode keyword groups
_PAYMENT_MODE_PATTERNS: list[tuple[str, list[str]]] = [
    ("UPI",    ["UPI", "PHONEPE", "GPAY", "GOOGLE PAY", "BHIM", "PAYTM UPI"]),
    ("NEFT",   ["NEFT"]),
    ("RTGS",   ["RTGS"]),
    ("IMPS",   ["IMPS"]),
    ("CASH",   ["ATM", "CASH WDL", "CASH WITHDRAWAL", "CASH DEP"]),
    ("CHEQUE", ["CLG", "CHEQUE", "CHQ", "CTS", "CLEARING"]),
    ("WALLET", ["WALLET", "MOBIKWIK", "FREECHARGE", "LAZYPAY"]),
    ("CARD",   ["POS ", "CARD", "SWIPE", "VISA", "MASTERCARD"]),
]


class BaseParser(ABC):
    """Abstract base for all bank statement parsers."""

    BANK_NAME: str = "GENERIC"
    PARSER_VERSION: str = pdfplumber.__version__

    def parse(self, pdf_bytes: bytes, statement_id: str) -> ParseResponse:
        """
        Top-level entry point. Tries table extraction first; falls back to OCR
        when pdfplumber yields no rows.
        """
        warnings: list[str] = []
        ocr_attempted = False

        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                transactions = self._extract_transactions(pdf, warnings)
                opening, closing, period = self._extract_metadata(pdf)

            if not transactions:
                logger.info(
                    "No transactions via table extraction — attempting OCR",
                    extra={"statement_id": statement_id, "bank": self.BANK_NAME},
                )
                ocr_attempted = True
                transactions, warnings_ocr = self._ocr_fallback(pdf_bytes)
                warnings.extend(warnings_ocr)
                # Re-open to try metadata extraction on text
                with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                    opening, closing, period = self._extract_metadata(pdf)

            balance_ok = validate_balance(opening, transactions, closing)
            if transactions and not balance_ok and opening and closing:
                warnings.append(
                    f"Balance mismatch: opening={opening}, closing={closing}. "
                    "Some transactions may be missing."
                )

            return ParseResponse(
                success=True,
                bank_detected=self.BANK_NAME,
                parser_used=self.__class__.__name__,
                parser_version=self.PARSER_VERSION,
                opening_balance=opening,
                closing_balance=closing,
                balance_validated=balance_ok,
                statement_period=period,
                transactions=transactions,
                warnings=warnings,
                ocr_attempted=ocr_attempted,
            )

        except Exception as exc:
            logger.error(
                "Parser raised exception",
                exc_info=exc,
                extra={"statement_id": statement_id, "bank": self.BANK_NAME},
            )
            return ParseResponse(
                success=False,
                bank_detected=self.BANK_NAME,
                parser_used=self.__class__.__name__,
                parser_version=self.PARSER_VERSION,
                error_code="PARSE_ERROR",
                error_message=str(exc),
                ocr_attempted=ocr_attempted,
            )

    # ------------------------------------------------------------------ #
    # Subclasses override these                                            #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def _extract_transactions(
        self, pdf: pdfplumber.PDF, warnings: list[str]
    ) -> list[TransactionRow]:
        """Extract transaction rows from the PDF using pdfplumber."""
        ...

    def _extract_metadata(
        self, pdf: pdfplumber.PDF
    ) -> tuple[str | None, str | None, StatementPeriod | None]:
        """
        Extract opening balance, closing balance, and statement period.
        Subclasses may override for bank-specific patterns.
        Default: return None for everything.
        """
        return None, None, None

    # ------------------------------------------------------------------ #
    # OCR fallback                                                         #
    # ------------------------------------------------------------------ #

    def _ocr_fallback(
        self, pdf_bytes: bytes
    ) -> tuple[list[TransactionRow], list[str]]:
        """Render each page to an image and run Tesseract OCR."""
        try:
            import fitz  # PyMuPDF
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            return [], [f"OCR dependencies not available: {exc}"]

        warnings: list[str] = []
        all_text = ""

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            page_text = pytesseract.image_to_string(img, lang="eng")
            all_text += page_text + "\n"
        doc.close()

        transactions = self._parse_ocr_text(all_text, warnings)
        if not transactions:
            warnings.append("OCR produced no parseable transactions")
        return transactions, warnings

    def _parse_ocr_text(
        self, text: str, warnings: list[str]
    ) -> list[TransactionRow]:
        """
        Generic OCR text parser. Override in subclasses for bank-specific regex.
        Looks for lines that match: date | description | amount | balance
        """
        rows: list[TransactionRow] = []
        # Pattern: date at start of line followed by text and amounts
        pattern = re.compile(
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(.+?)\s+"
            r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$",
            re.MULTILINE,
        )
        for match in pattern.finditer(text):
            date_str, desc, amount_str, balance_str = match.groups()
            date = parse_date(date_str)
            if not date:
                continue
            amount = clean_amount(amount_str)
            if not amount:
                continue
            rows.append(
                TransactionRow(
                    transaction_date=date,
                    raw_description=desc.strip(),
                    amount=amount,
                    transaction_type=_infer_type_from_description(desc),
                    balance_after=clean_amount(balance_str),
                    payment_mode=detect_payment_mode(desc),
                    reference_number=extract_reference(desc),
                )
            )
        return rows

    # ------------------------------------------------------------------ #
    # Shared helpers used by subclasses                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _collect_tables(pdf: pdfplumber.PDF) -> list[list[list[str | None]]]:
        """Return every table from every page, flattened into one list."""
        tables = []
        for page in pdf.pages:
            for table in page.extract_tables():
                tables.append(table)
        return tables

    @staticmethod
    def _find_header_row(
        table: list[list[str | None]], keywords: list[str]
    ) -> int | None:
        """Return the index of the row that contains ALL given keywords (case-insensitive)."""
        kw_upper = [k.upper() for k in keywords]
        for idx, row in enumerate(table):
            cells = " ".join(str(c or "") for c in row).upper()
            if all(kw in cells for kw in kw_upper):
                return idx
        return None


# ------------------------------------------------------------------ #
# Module-level utility functions used across all parsers              #
# ------------------------------------------------------------------ #

def parse_date(raw: str | None) -> str | None:
    """Try all known date formats; return ISO string YYYY-MM-DD or None."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def clean_amount(raw: str | None) -> str | None:
    """Strip currency symbols and commas; return '1299.00' format or None."""
    if not raw:
        return None
    cleaned = re.sub(r"[₹$£€,\s]", "", str(raw).strip())
    cleaned = cleaned.replace("Rs.", "").replace("Rs", "").replace("INR", "")
    cleaned = cleaned.strip().lstrip("+-")
    try:
        return f"{Decimal(cleaned):.2f}"
    except InvalidOperation:
        return None


def detect_payment_mode(description: str) -> str:
    upper = description.upper()
    for mode, keywords in _PAYMENT_MODE_PATTERNS:
        if any(kw in upper for kw in keywords):
            return mode
    return "OTHER"


def extract_reference(description: str) -> str | None:
    # UPI: UPI/merchant/name/123456789
    m = re.search(r"UPI/[^/]+/[^/]*/(\d{9,})", description, re.IGNORECASE)
    if m:
        return m.group(1)
    # UTR number (NEFT/RTGS/IMPS)
    m = re.search(r"UTR[:/\s]*([A-Z0-9]{12,22})", description, re.IGNORECASE)
    if m:
        return m.group(1)
    # IMPS ref
    m = re.search(r"IMPS[/\s]+(\d{12})", description, re.IGNORECASE)
    if m:
        return m.group(1)
    # Cheque number
    m = re.search(r"(?:CHQ|CHEQUE)[./\s#]*(\d{6,9})", description, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _infer_type_from_description(description: str) -> str:
    upper = description.upper()
    credit_signals = ["CREDIT", "CR ", " CR", "RECEIVED", "DEPOSIT", "NEFT-CREDIT"]
    if any(s in upper for s in credit_signals):
        return "CREDIT"
    return "DEBIT"
