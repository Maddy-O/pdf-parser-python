"""
StatementParser — the single public entry point for all parsing operations.

Usage:
    from statement_parser import StatementParser

    with open("statement.pdf", "rb") as f:
        result = StatementParser.parse(f.read())

    # Or with explicit hints
    result = StatementParser.parse(
        pdf_bytes,
        bank_code="HDFC",
        statement_type="BANK",
        enable_ocr=True,
    )
"""
from __future__ import annotations

import hashlib
from typing import Optional

from statement_parser.enums import BankCode, StatementType
from statement_parser.models.result import ParseResult, ParseError
from statement_parser.parsers.detector import detect_bank, detect_statement_type
from statement_parser.parsers.registry import DEFAULT_REGISTRY


class StatementParser:
    """
    Facade: detect → look up parser → parse → return result.

    All methods are classmethods; no instance needed.
    """

    @classmethod
    def parse(
        cls,
        file_bytes: bytes,
        *,
        bank_code: Optional[str] = None,
        statement_type: Optional[str] = None,
        enable_ocr: bool = False,
        date_hint: Optional[str] = None,
    ) -> ParseResult:
        """
        Parse a statement file (PDF, OFX, QFX, CSV).

        Args:
            file_bytes:      Raw file bytes.
            bank_code:       Override auto-detection (e.g. "HDFC", "CHASE").
            statement_type:  "BANK" or "CREDIT_CARD" — override auto-detection.
            enable_ocr:      Attempt OCR if text extraction yields no transactions.
            date_hint:       "dmy", "mdy", or "auto" — passed to parsers that support it.

        Returns:
            ParseResult with transactions, metadata, balance validation, and warnings.
        """
        try:
            fmt = _detect_format(file_bytes)

            # For structured formats (OFX/QFX/CSV), skip bank detection
            if fmt in ("ofx", "qfx"):
                from statement_parser.parsers.formats.ofx import OFXParser
                parser = OFXParser()
                return parser.parse(file_bytes, enable_ocr=enable_ocr)

            if fmt == "csv":
                from statement_parser.parsers.formats.csv import CsvParser
                parser = CsvParser()
                return parser.parse(file_bytes, enable_ocr=enable_ocr)

            # PDF: detect bank and statement type
            resolved_bank = _resolve_bank(bank_code, file_bytes)
            resolved_type = _resolve_statement_type(statement_type, file_bytes)

            parser = DEFAULT_REGISTRY.get(resolved_bank, resolved_type)

            if date_hint and hasattr(parser, "DATE_HINT"):
                parser.DATE_HINT = date_hint

            return parser.parse(file_bytes, enable_ocr=enable_ocr)

        except Exception as exc:
            return ParseResult(
                success=False,
                file_hash=hashlib.sha256(file_bytes).hexdigest() if file_bytes else None,
                error=ParseError(
                    code="PARSE_EXCEPTION",
                    message=str(exc),
                ),
            )

    @classmethod
    def file_hash(cls, file_bytes: bytes) -> str:
        """Return SHA-256 hex digest of raw file bytes."""
        return hashlib.sha256(file_bytes).hexdigest()

    @classmethod
    def supported_banks(cls) -> list[str]:
        """Return all bank codes that have a dedicated parser."""
        return [
            bc.value for bc in BankCode
            if bc != BankCode.GENERIC
        ]


def _detect_format(file_bytes: bytes) -> str:
    """Detect file format from magic bytes / content sniffing."""
    header = file_bytes[:16]
    # PDF
    if header.startswith(b"%PDF"):
        return "pdf"
    # OFX/QFX — plain text starting with OFXHEADER: or <OFX
    try:
        snippet = file_bytes[:512].decode("utf-8", errors="ignore").lstrip()
        if snippet.startswith("OFXHEADER") or snippet.startswith("<OFX"):
            return "ofx"
    except Exception:
        pass
    # CSV — check for commas in first line
    try:
        first_line = file_bytes[:256].decode("utf-8", errors="ignore").split("\n")[0]
        if first_line.count(",") >= 2:
            return "csv"
    except Exception:
        pass
    return "pdf"  # Default: attempt as PDF


def _resolve_bank(hint: Optional[str], file_bytes: bytes) -> BankCode:
    if hint:
        try:
            return BankCode(hint.upper())
        except ValueError:
            pass
    return detect_bank(file_bytes)


def _resolve_statement_type(hint: Optional[str], file_bytes: bytes) -> StatementType:
    if hint:
        try:
            return StatementType(hint.upper())
        except ValueError:
            pass
    return detect_statement_type(file_bytes)
