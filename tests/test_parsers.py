"""
Parser unit tests.

Fixtures (real PDFs) are NOT committed to git — store them in tests/fixtures/
and add that path to .gitignore. Each test gracefully skips when the fixture
file is missing so CI doesn't fail in the absence of sample PDFs.
"""

import os
from pathlib import Path

import pytest

from app.parsers.base import (
    parse_date,
    clean_amount,
    detect_payment_mode,
    extract_reference,
)
from app.utils.balance_validator import validate_balance
from app.utils.bank_detector import detect_bank
from app.models.response import TransactionRow

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------ #
# parse_date                                                           #
# ------------------------------------------------------------------ #


class TestParseDate:
    def test_ddmmyyyy_slash(self):
        assert parse_date("15/01/2025") == "2025-01-15"

    def test_ddmmyy_slash(self):
        assert parse_date("15/01/25") == "2025-01-15"

    def test_ddmmyyyy_dash(self):
        assert parse_date("15-01-2025") == "2025-01-15"

    def test_dd_mon_yyyy(self):
        assert parse_date("15 Jan 2025") == "2025-01-15"

    def test_dd_dash_mon_yyyy(self):
        assert parse_date("15-Jan-2025") == "2025-01-15"

    def test_iso(self):
        assert parse_date("2025-01-15") == "2025-01-15"

    def test_invalid_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_none_returns_none(self):
        assert parse_date(None) is None


# ------------------------------------------------------------------ #
# clean_amount                                                         #
# ------------------------------------------------------------------ #


class TestCleanAmount:
    def test_with_commas(self):
        assert clean_amount("1,23,456.78") == "123456.78"

    def test_with_rupee_symbol(self):
        assert clean_amount("₹1,299.00") == "1299.00"

    def test_plain(self):
        assert clean_amount("500.00") == "500.00"

    def test_none(self):
        assert clean_amount(None) is None

    def test_empty_string(self):
        assert clean_amount("") is None

    def test_adds_two_decimals(self):
        assert clean_amount("500") == "500.00"


# ------------------------------------------------------------------ #
# detect_payment_mode                                                  #
# ------------------------------------------------------------------ #


class TestDetectPaymentMode:
    def test_upi(self):
        assert detect_payment_mode("UPI/AMAZON PAY/INDIA/123456789") == "UPI"

    def test_neft(self):
        assert detect_payment_mode("NEFT-HDFC-12345") == "NEFT"

    def test_imps(self):
        assert detect_payment_mode("IMPS/123456789012") == "IMPS"

    def test_cheque(self):
        assert detect_payment_mode("CLG/000012345") == "CHEQUE"

    def test_atm(self):
        assert detect_payment_mode("ATM CASH WITHDRAWAL") == "CASH"

    def test_fallback(self):
        assert detect_payment_mode("SALARY CREDIT") == "OTHER"


# ------------------------------------------------------------------ #
# extract_reference                                                    #
# ------------------------------------------------------------------ #


class TestExtractReference:
    def test_upi_ref(self):
        ref = extract_reference("UPI/AMAZON/INDIA/987654321012")
        assert ref == "987654321012"

    def test_utr(self):
        ref = extract_reference("NEFT UTR:HDFC0000012345678")
        assert ref == "HDFC0000012345678"

    def test_no_ref(self):
        assert extract_reference("SALARY CREDIT") is None


# ------------------------------------------------------------------ #
# validate_balance                                                     #
# ------------------------------------------------------------------ #


class TestValidateBalance:
    def _make_txn(self, amount: str, tx_type: str) -> TransactionRow:
        return TransactionRow(
            transaction_date="2025-01-01",
            raw_description="test",
            amount=amount,
            transaction_type=tx_type,
        )

    def test_valid(self):
        txns = [
            self._make_txn("500.00", "DEBIT"),
            self._make_txn("1000.00", "CREDIT"),
        ]
        # 10000 + 1000 - 500 = 10500
        assert validate_balance("10000.00", txns, "10500.00") is True

    def test_mismatch(self):
        txns = [self._make_txn("500.00", "DEBIT")]
        # 10000 - 500 = 9500, not 9000
        assert validate_balance("10000.00", txns, "9000.00") is False

    def test_none_opening(self):
        assert validate_balance(None, [], "1000.00") is False

    def test_within_tolerance(self):
        txns = [self._make_txn("333.33", "DEBIT"), self._make_txn("333.33", "DEBIT")]
        # 1000 - 666.66 = 333.34, closing says 333.33 — diff 0.01 ≤ tolerance
        assert validate_balance("1000.00", txns, "333.34") is True


# ------------------------------------------------------------------ #
# Integration tests against real PDF fixtures                          #
# (skipped when fixture files are absent)                             #
# ------------------------------------------------------------------ #


def _fixture(name: str) -> Path:
    return FIXTURE_DIR / name


@pytest.mark.skipif(
    not _fixture("hdfc_sample.pdf").exists(),
    reason="HDFC fixture PDF not present",
)
def test_hdfc_parser_integration():
    from app.parsers.banks.hdfc import HdfcParser

    pdf_bytes = _fixture("hdfc_sample.pdf").read_bytes()
    result = HdfcParser().parse(pdf_bytes, statement_id="test-hdfc")

    assert result.success, f"Parser failed: {result.error_message}"
    assert len(result.transactions) > 0, "No transactions extracted"
    assert all(t.transaction_date for t in result.transactions)
    assert all(t.amount for t in result.transactions)
    assert all(t.transaction_type in ("DEBIT", "CREDIT") for t in result.transactions)


@pytest.mark.skipif(
    not _fixture("icici_sample.pdf").exists(),
    reason="ICICI fixture PDF not present",
)
def test_icici_parser_integration():
    from app.parsers.banks.icici import IciciParser

    pdf_bytes = _fixture("icici_sample.pdf").read_bytes()
    result = IciciParser().parse(pdf_bytes, statement_id="test-icici")

    assert result.success
    assert len(result.transactions) > 0


@pytest.mark.skipif(
    not _fixture("sbi_sample.pdf").exists(),
    reason="SBI fixture PDF not present",
)
def test_sbi_parser_integration():
    from app.parsers.banks.sbi import SbiParser

    pdf_bytes = _fixture("sbi_sample.pdf").read_bytes()
    result = SbiParser().parse(pdf_bytes, statement_id="test-sbi")

    assert result.success
    assert len(result.transactions) > 0


@pytest.mark.skipif(
    not _fixture("generic_sample.pdf").exists(),
    reason="Generic fixture PDF not present",
)
def test_generic_parser_integration():
    from app.parsers.generic import GenericParser

    pdf_bytes = _fixture("generic_sample.pdf").read_bytes()
    result = GenericParser().parse(pdf_bytes, statement_id="test-generic")

    assert result.success
