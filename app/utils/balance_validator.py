from decimal import Decimal, InvalidOperation
from app.models.response import TransactionRow

_TOLERANCE = Decimal("0.02")  # 2 paise tolerance for rounding across many rows


def validate_balance(
    opening: str | None,
    transactions: list[TransactionRow],
    closing: str | None,
) -> bool:
    """Return True if opening + credits - debits ≈ closing (within tolerance)."""
    if opening is None or closing is None:
        return False
    try:
        opening_dec = Decimal(_clean(opening))
        closing_dec = Decimal(_clean(closing))

        total_credits = sum(
            Decimal(_clean(t.amount)) for t in transactions if t.transaction_type == "CREDIT"
        )
        total_debits = sum(
            Decimal(_clean(t.amount)) for t in transactions if t.transaction_type == "DEBIT"
        )

        expected = opening_dec + total_credits - total_debits
        return abs(expected - closing_dec) <= _TOLERANCE
    except (InvalidOperation, ValueError):
        return False


def _clean(value: str) -> str:
    """Strip currency symbols, spaces, and commas."""
    return value.strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").replace("INR", "").strip()
