from decimal import Decimal, InvalidOperation
from statement_parser.models.transaction import TransactionRow
from statement_parser.enums import TransactionType

_TOLERANCE = Decimal("0.05")  # 5 paise/cents — covers multi-row rounding


def validate_balance(
    opening: str | None,
    transactions: list[TransactionRow],
    closing: str | None,
) -> bool:
    """Return True if opening + credits − debits ≈ closing (within tolerance)."""
    if opening is None or closing is None:
        return False
    try:
        op = Decimal(_strip(opening))
        cl = Decimal(_strip(closing))
        credits = sum(Decimal(_strip(t.amount)) for t in transactions if t.transaction_type == TransactionType.CREDIT)
        debits  = sum(Decimal(_strip(t.amount)) for t in transactions if t.transaction_type == TransactionType.DEBIT)
        expected = op + credits - debits
        return abs(expected - cl) <= _TOLERANCE
    except (InvalidOperation, ValueError):
        return False


def _strip(value: str) -> str:
    return value.strip().replace(",", "")
