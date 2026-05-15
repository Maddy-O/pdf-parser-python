import logging
import re
from abc import ABC, abstractmethod
from io import BytesIO

import pdfplumber

from statement_parser.enums import BankCode, Currency, StatementType
from statement_parser.models.result import ParseResult, ParseError
from statement_parser.models.statement import StatementMetadata, StatementPeriod
from statement_parser.models.transaction import TransactionRow
from statement_parser.utils.balance_validator import validate_balance

logger = logging.getLogger(__name__)

import pdfplumber
_PARSER_VERSION = pdfplumber.__version__


class BaseParser(ABC):
    """
    Abstract base for every bank/format parser.

    Subclasses implement:
    - _extract_transactions(pdf, warnings) → list[TransactionRow]
    - _extract_metadata(pdf)              → (opening, closing, StatementMetadata)  [optional]

    BaseParser.parse() orchestrates:
    1. Table extraction via pdfplumber
    2. OCR fallback when no transactions found
    3. Balance validation
    4. ParseResult assembly
    """

    # Subclasses set these
    BANK_CODE: BankCode = BankCode.GENERIC
    DEFAULT_CURRENCY: Currency = Currency.UNKNOWN
    DATE_HINT: str = "dmy"  # "dmy" | "mdy" | "auto"

    def parse(self, pdf_bytes: bytes, *, statement_id: str = "", enable_ocr: bool = False) -> ParseResult:
        warnings: list[str] = []
        ocr_attempted = False

        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                transactions = self._extract_transactions(pdf, warnings)
                opening, closing, metadata = self._extract_metadata(pdf)

            if not transactions and enable_ocr:
                logger.info(
                    "No transactions via table extraction — attempting OCR",
                    extra={"statement_id": statement_id, "bank": self.BANK_CODE},
                )
                ocr_attempted = True
                transactions, ocr_warnings = self._run_ocr_fallback(pdf_bytes)
                warnings.extend(ocr_warnings)

                if not transactions:
                    warnings.append("OCR also produced no parseable transactions")

            # Apply default currency to transactions that have UNKNOWN currency
            for txn in transactions:
                if txn.currency == Currency.UNKNOWN and self.DEFAULT_CURRENCY != Currency.UNKNOWN:
                    txn.currency = self.DEFAULT_CURRENCY

            balance_ok = validate_balance(opening, transactions, closing)
            if transactions and not balance_ok and opening and closing:
                warnings.append(
                    f"Balance mismatch: opening={opening}, closing={closing}. "
                    "Some transactions may be missing from the extracted data."
                )

            return ParseResult(
                success=True,
                bank_code=self.BANK_CODE.value,
                parser_used=self.__class__.__name__,
                parser_version=_PARSER_VERSION,
                metadata=metadata,
                transactions=transactions,
                opening_balance=opening,
                closing_balance=closing,
                balance_validated=balance_ok,
                warnings=warnings,
                ocr_attempted=ocr_attempted,
            )

        except Exception as exc:
            logger.error(
                "Parser raised exception",
                exc_info=exc,
                extra={"statement_id": statement_id, "bank": self.BANK_CODE},
            )
            return ParseResult(
                success=False,
                bank_code=self.BANK_CODE.value,
                parser_used=self.__class__.__name__,
                parser_version=_PARSER_VERSION,
                ocr_attempted=ocr_attempted,
                error=ParseError(code="PARSE_ERROR", message=str(exc)),
            )

    # ------------------------------------------------------------------ #
    # Subclass contract                                                    #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def _extract_transactions(
        self, pdf: pdfplumber.PDF, warnings: list[str]
    ) -> list[TransactionRow]: ...

    def _extract_metadata(
        self, pdf: pdfplumber.PDF
    ) -> tuple[str | None, str | None, StatementMetadata | None]:
        """
        Return (opening_balance, closing_balance, StatementMetadata).
        Default: None for everything. Subclasses override for their bank.
        """
        return None, None, self._default_metadata()

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    def _default_metadata(self) -> StatementMetadata:
        return StatementMetadata(
            bank_code=self.BANK_CODE.value,
            currency=self.DEFAULT_CURRENCY,
        )

    def _default_cc_metadata(self) -> StatementMetadata:
        return StatementMetadata(
            bank_code=self.BANK_CODE.value,
            statement_type=StatementType.CREDIT_CARD,
            currency=self.DEFAULT_CURRENCY,
        )

    @staticmethod
    def _collect_tables(pdf: pdfplumber.PDF) -> list[list[list[str | None]]]:
        tables = []
        for page in pdf.pages:
            for table in page.extract_tables():
                tables.append(table)
        return tables

    @staticmethod
    def _find_header_row(
        table: list[list[str | None]],
        keywords: list[str | tuple[str, ...]],
    ) -> int | None:
        """
        Return the index of the first row that satisfies every keyword group.

        Each entry in `keywords` can be:
        - str   → that exact word must appear somewhere in the row
        - tuple → at least ONE of the words in the tuple must appear in the row

        This lets a single keyword list handle multiple column name variants
        (e.g. ("dr", "debit", "withdrawal") matches whichever label that bank uses).
        """
        groups: list[tuple[str, ...]] = [
            (k.upper(),) if isinstance(k, str) else tuple(v.upper() for v in k)
            for k in keywords
        ]
        for idx, row in enumerate(table[:8]):
            cells = " ".join(str(c or "") for c in row).upper()
            if all(any(variant in cells for variant in group) for group in groups):
                return idx
        return None

    @staticmethod
    def _full_text(pdf: pdfplumber.PDF) -> str:
        return " ".join(page.extract_text() or "" for page in pdf.pages)

    @staticmethod
    def _find_amount_in_text(text: str, labels: list[str]) -> str | None:
        from statement_parser.utils.currency import clean_amount
        lower = text.lower()
        for label in labels:
            idx = lower.find(label)
            if idx == -1:
                continue
            snippet = text[idx: idx + 80]
            m = re.search(r"[\d,]+\.\d{2}", snippet)
            if m:
                return clean_amount(m.group())
        return None

    def _run_ocr_fallback(
        self, pdf_bytes: bytes
    ) -> tuple[list[TransactionRow], list[str]]:
        warnings: list[str] = []
        try:
            from statement_parser.utils.ocr import ocr_pdf_bytes
            text = ocr_pdf_bytes(pdf_bytes)
            transactions = self._parse_ocr_text(text, warnings)
            return transactions, warnings
        except ImportError as exc:
            warnings.append(str(exc))
            return [], warnings
        except Exception as exc:
            warnings.append(f"OCR failed: {exc}")
            return [], warnings

    def _parse_ocr_text(
        self, text: str, warnings: list[str]
    ) -> list[TransactionRow]:
        """
        Generic OCR text parser. Subclasses may override with bank-specific patterns.
        Looks for lines: date | description | amount | balance
        """
        from statement_parser.utils.date_parser import parse_date
        from statement_parser.utils.currency import clean_amount
        from statement_parser.utils.text import detect_payment_mode, extract_reference

        rows: list[TransactionRow] = []
        pattern = re.compile(
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$",
            re.MULTILINE,
        )
        for match in pattern.finditer(text):
            date_str, desc, amount_str, balance_str = match.groups()
            date = parse_date(date_str, self.DATE_HINT)
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
                    transaction_type="DEBIT",
                    currency=self.DEFAULT_CURRENCY,
                    balance_after=clean_amount(balance_str),
                    payment_mode=detect_payment_mode(desc),
                    reference_number=extract_reference(desc),
                )
            )
        return rows
