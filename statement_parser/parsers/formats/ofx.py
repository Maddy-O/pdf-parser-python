"""
OFX / QFX parser.

OFX (Open Financial Exchange) is the standard export format used by virtually
every US, UK, and international bank. Most banks have a "Download Transactions"
button that exports .ofx or .qfx files.

Depends on: ofxtools (already in pyproject.toml base deps)
"""

import logging
from io import StringIO, BytesIO
from statement_parser.enums import BankCode, Currency, TransactionType, PaymentMode
from statement_parser.models.result import ParseResult, ParseError
from statement_parser.models.statement import StatementMetadata, StatementPeriod
from statement_parser.models.transaction import TransactionRow
from statement_parser.utils.currency import clean_amount, detect_currency
from statement_parser.utils.balance_validator import validate_balance

import pdfplumber
_PARSER_VERSION = pdfplumber.__version__

logger = logging.getLogger(__name__)

# OFX TRNTYPE → our TransactionType
_TRNTYPE_MAP: dict[str, TransactionType] = {
    "DEBIT":   TransactionType.DEBIT,
    "CREDIT":  TransactionType.CREDIT,
    "INT":     TransactionType.CREDIT,   # Interest earned
    "DIV":     TransactionType.CREDIT,   # Dividend
    "FEE":     TransactionType.DEBIT,    # Fee charged
    "SRVCHG":  TransactionType.DEBIT,    # Service charge
    "DEP":     TransactionType.CREDIT,   # Deposit
    "ATM":     TransactionType.DEBIT,    # ATM withdrawal
    "POS":     TransactionType.DEBIT,    # POS purchase
    "XFER":    TransactionType.DEBIT,    # Transfer (direction ambiguous; treat as debit)
    "CHECK":   TransactionType.DEBIT,    # Cheque
    "PAYMENT": TransactionType.DEBIT,    # Payment made (bill pay = money out)
    "CASH":    TransactionType.DEBIT,
    "DIRECTDEP": TransactionType.CREDIT, # Direct deposit
    "DIRECTDEBIT": TransactionType.DEBIT,
    "REPEATPMT": TransactionType.DEBIT,
    "OTHER":   TransactionType.DEBIT,
}


class OFXParser:
    """Parses OFX 1.x / 2.x and QFX files."""

    def parse(self, file_bytes: bytes, statement_id: str = "") -> ParseResult:
        try:
            from ofxtools.Parser import OFXTree
        except ImportError:
            return ParseResult(
                success=False,
                parser_used=self.__class__.__name__,
                parser_version=_PARSER_VERSION,
                error=ParseError(code="MISSING_DEP", message="ofxtools not installed"),
            )

        try:
            parser = OFXTree()
            parser.parse(BytesIO(file_bytes))
            ofx = parser.convert()
        except Exception as exc:
            return ParseResult(
                success=False,
                parser_used=self.__class__.__name__,
                parser_version=_PARSER_VERSION,
                error=ParseError(code="PARSE_ERROR", message=str(exc)),
            )

        transactions: list[TransactionRow] = []
        opening: str | None = None
        closing: str | None = None
        metadata: StatementMetadata | None = None
        warnings: list[str] = []

        for stmt in _iter_statements(ofx):
            currency = _map_currency(getattr(stmt, "curdef", None))
            acct = getattr(stmt, "account", None)
            acct_id = getattr(acct, "acctid", None)

            # Balances
            if hasattr(stmt, "balance"):
                bal = stmt.balance
                if hasattr(bal, "balamt"):
                    closing = f"{bal.balamt:.2f}"
            if hasattr(stmt, "ledgerbal"):
                lb = stmt.ledgerbal
                if hasattr(lb, "balamt"):
                    closing = f"{lb.balamt:.2f}"

            # Period
            dtstart = _ofx_date(getattr(stmt, "dtstart", None))
            dtend   = _ofx_date(getattr(stmt, "dtend", None))
            period = StatementPeriod(from_date=dtstart, to_date=dtend) if dtstart or dtend else None

            metadata = StatementMetadata(
                bank_code=BankCode.GENERIC.value,
                currency=currency,
                account_number_masked=acct_id[-4:].rjust(8, "*") if acct_id and len(acct_id) >= 4 else acct_id,
                period=period,
            )

            for txn in (getattr(stmt, "transactions", None) or []):
                trntype = str(getattr(txn, "trntype", "OTHER")).upper()
                tx_type = _TRNTYPE_MAP.get(trntype, TransactionType.DEBIT)

                amt_raw = getattr(txn, "trnamt", None)
                if amt_raw is None:
                    continue
                # OFX signs: positive = credit, negative = debit
                amt = abs(float(amt_raw))
                if float(amt_raw) > 0:
                    tx_type = TransactionType.CREDIT
                elif float(amt_raw) < 0:
                    tx_type = TransactionType.DEBIT

                date = _ofx_date(getattr(txn, "dtposted", None))
                if not date:
                    warnings.append(f"Skipped transaction with no date: {txn}")
                    continue

                desc = str(getattr(txn, "memo", None) or getattr(txn, "name", None) or "")
                ref  = str(getattr(txn, "fitid", None) or getattr(txn, "checknum", None) or "")

                transactions.append(
                    TransactionRow(
                        transaction_date=date,
                        value_date=_ofx_date(getattr(txn, "dtavail", None)),
                        raw_description=desc,
                        amount=f"{amt:.2f}",
                        transaction_type=tx_type,
                        currency=currency,
                        reference_number=ref or None,
                        payment_mode=_map_payment_mode(trntype),
                    )
                )

        balance_ok = validate_balance(opening, transactions, closing)
        return ParseResult(
            success=True,
            bank_code=BankCode.GENERIC.value,
            parser_used=self.__class__.__name__,
            parser_version=_PARSER_VERSION,
            metadata=metadata,
            transactions=transactions,
            opening_balance=opening,
            closing_balance=closing,
            balance_validated=balance_ok,
            warnings=warnings,
        )


# QFX is OFX with a Quicken-specific wrapper — same parsing
QFXParser = OFXParser


def _iter_statements(ofx):
    """Yield bank and credit card statements from an OFX document."""
    for attr in ("bankmsgsrsv1", "creditcardmsgsrsv1"):
        msg = getattr(ofx, attr, None)
        if msg is None:
            continue
        stmts = getattr(msg, "statements", []) or []
        yield from stmts


def _ofx_date(dt) -> str | None:
    if dt is None:
        return None
    try:
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(dt)[:10]


def _map_currency(curdef: str | None) -> Currency:
    if not curdef:
        return Currency.UNKNOWN
    try:
        return Currency(curdef.upper())
    except ValueError:
        return Currency.UNKNOWN


def _map_payment_mode(trntype: str) -> PaymentMode:
    mapping = {
        "ATM":         PaymentMode.CASH,
        "CHECK":       PaymentMode.CHEQUE,
        "POS":         PaymentMode.CARD,
        "DIRECTDEP":   PaymentMode.ACH,
        "DIRECTDEBIT": PaymentMode.ACH,
        "XFER":        PaymentMode.WIRE,
    }
    return mapping.get(trntype.upper(), PaymentMode.OTHER)
