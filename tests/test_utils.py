"""
Unit tests for utility functions.
These tests require no PDF files — pure logic.
"""
import pytest
from statement_parser.utils.date_parser import parse_date
from statement_parser.utils.currency import clean_amount, is_negative_amount, detect_currency
from statement_parser.utils.text import detect_payment_mode, extract_reference
from statement_parser.enums import Currency, PaymentMode


class TestParseDate:
    def test_dmy_slash(self):
        assert parse_date("15/03/2024", "dmy") == "2024-03-15"

    def test_dmy_dash(self):
        assert parse_date("15-03-2024", "dmy") == "2024-03-15"

    def test_mdy_slash(self):
        assert parse_date("03/15/2024", "mdy") == "2024-03-15"

    def test_iso(self):
        assert parse_date("2024-03-15") == "2024-03-15"

    def test_month_name(self):
        assert parse_date("15 Mar 2024", "dmy") == "2024-03-15"

    def test_invalid_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_empty_returns_none(self):
        assert parse_date("") is None

    def test_none_returns_none(self):
        assert parse_date(None) is None  # type: ignore


class TestCleanAmount:
    def test_plain(self):
        assert clean_amount("1299.50") == "1299.50"

    def test_commas(self):
        assert clean_amount("1,23,456.78") == "123456.78"

    def test_rupee_symbol(self):
        assert clean_amount("₹1,000.00") == "1000.00"

    def test_dollar_symbol(self):
        assert clean_amount("$250.00") == "250.00"

    def test_parentheses_negative(self):
        # Parentheses indicate negative value — sign is preserved
        assert clean_amount("(500.00)") == "-500.00"

    def test_dr_suffix(self):
        assert clean_amount("1000.00 Dr") == "1000.00"

    def test_cr_suffix(self):
        assert clean_amount("500.00 Cr") == "500.00"

    def test_empty_returns_none(self):
        assert clean_amount("") is None

    def test_none_returns_none(self):
        assert clean_amount(None) is None  # type: ignore

    def test_zero_returns_string(self):
        # Zero is a valid amount string — callers decide if zero should be skipped
        assert clean_amount("0.00") == "0.00"

    def test_negative_amount(self):
        assert clean_amount("-1500.00") == "-1500.00"


class TestIsNegativeAmount:
    def test_minus_prefix(self):
        assert is_negative_amount("-500.00") is True

    def test_parentheses(self):
        assert is_negative_amount("(500.00)") is True

    def test_dr_suffix(self):
        # DR suffix alone doesn't make is_negative_amount true (DR is stripped by clean_amount before this)
        assert is_negative_amount("500.00 DR") is False

    def test_positive(self):
        assert is_negative_amount("500.00") is False

    def test_cr_suffix(self):
        assert is_negative_amount("500.00 CR") is False


class TestDetectCurrency:
    def test_inr_symbol(self):
        assert detect_currency("Amount: ₹1,000") == Currency.INR

    def test_usd_symbol(self):
        assert detect_currency("Total: $500.00") == Currency.USD

    def test_gbp_symbol(self):
        assert detect_currency("Balance: £250") == Currency.GBP

    def test_inr_code(self):
        assert detect_currency("INR 500") == Currency.INR

    def test_usd_code(self):
        assert detect_currency("Currency: USD") == Currency.USD

    def test_unknown(self):
        assert detect_currency("no currency here") == Currency.UNKNOWN


class TestDetectPaymentMode:
    def test_upi(self):
        assert detect_payment_mode("UPI/paytm/merchant") == PaymentMode.UPI

    def test_neft(self):
        assert detect_payment_mode("NEFT transfer to XYZ") == PaymentMode.NEFT

    def test_imps(self):
        assert detect_payment_mode("IMPS/123456789") == PaymentMode.IMPS

    def test_cash_atm(self):
        # ATM withdrawals are categorised as CASH
        assert detect_payment_mode("ATM withdrawal") == PaymentMode.CASH

    def test_ach(self):
        assert detect_payment_mode("ACH CREDIT PAYROLL") == PaymentMode.ACH

    def test_faster_payments(self):
        assert detect_payment_mode("FPS REF 123456") == PaymentMode.FASTER_PAYMENTS

    def test_unknown_returns_other(self):
        assert detect_payment_mode("random description") == PaymentMode.OTHER


class TestExtractReference:
    def test_upi_ref(self):
        # UPI pattern: UPI/app/merchant_name/ref_number
        ref = extract_reference("UPI/GPAY/merchant.abc@okhdfc/423456789012")
        assert ref is not None
        assert ref == "423456789012"

    def test_utr(self):
        ref = extract_reference("NEFT UTR123456789012")
        assert ref is not None

    def test_no_ref(self):
        ref = extract_reference("some purchase at shop")
        assert ref is None
