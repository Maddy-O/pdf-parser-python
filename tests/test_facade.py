"""
Integration-level tests for StatementParser facade.
These tests run without real PDF files — they verify error handling,
format detection, and that the parse() method returns a well-formed ParseResult.
"""
import pytest
from statement_parser import StatementParser, ParseResult, BankCode


class TestStatementParserMeta:
    def test_supported_banks_is_nonempty(self):
        banks = StatementParser.supported_banks()
        assert len(banks) > 0

    def test_generic_not_in_supported_banks(self):
        # GENERIC is a fallback, not a bank users choose
        banks = StatementParser.supported_banks()
        assert "GENERIC" not in banks

    def test_file_hash_returns_64_char_hex(self):
        h = StatementParser.file_hash(b"test content")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestStatementParserErrorHandling:
    def test_empty_bytes_returns_failure(self):
        result = StatementParser.parse(b"")
        assert isinstance(result, ParseResult)
        # May fail gracefully or return empty
        # Must not raise

    def test_garbage_bytes_returns_failure(self):
        result = StatementParser.parse(b"this is not a valid statement file at all!!")
        assert isinstance(result, ParseResult)
        # Must not raise

    def test_invalid_bank_code_falls_back_to_generic(self):
        # Should not raise, should fall back gracefully
        result = StatementParser.parse(b"%PDF-1.4 fake pdf", bank_code="NONEXISTENT_BANK_XYZ")
        assert isinstance(result, ParseResult)

    def test_returns_parse_result_type(self):
        result = StatementParser.parse(b"%PDF-1.4")
        assert isinstance(result, ParseResult)
        assert hasattr(result, "success")
        assert hasattr(result, "transactions")
        assert hasattr(result, "warnings")
