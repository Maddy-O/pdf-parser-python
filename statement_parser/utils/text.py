import re
from statement_parser.enums import PaymentMode

# Payment mode patterns — checked in order (most specific first)
_MODE_PATTERNS: list[tuple[PaymentMode, list[str]]] = [
    (PaymentMode.UPI,             ["UPI", "PHONEPE", "GPAY", "GOOGLE PAY", "BHIM", "PAYTM UPI"]),
    (PaymentMode.NEFT,            ["NEFT"]),
    (PaymentMode.RTGS,            ["RTGS"]),
    (PaymentMode.IMPS,            ["IMPS"]),
    (PaymentMode.FASTER_PAYMENTS, ["FASTER PAYMENT", "FPS", "FASTER PAY"]),
    (PaymentMode.BACS,            ["BACS", "DIRECT DEBIT", "DIRECT CREDIT", "STANDING ORDER"]),
    (PaymentMode.ACH,             ["ACH", "DIRECT DEPOSIT", "ZELLE", "VENMO", "AUTOPAY"]),
    (PaymentMode.WIRE,            ["WIRE", "INTERNATIONAL TRANSFER", "SWIFT", "CHAPS"]),
    (PaymentMode.SEPA,            ["SEPA"]),
    (PaymentMode.CASH,            ["ATM", "CASH WDL", "CASH WITHDRAWAL", "CASH DEP", "WITHDRAW"]),
    (PaymentMode.CHEQUE,          ["CLG", "CHEQUE", "CHQ", "CTS", "CLEARING", "CHECK"]),
    (PaymentMode.WALLET,          ["WALLET", "MOBIKWIK", "FREECHARGE", "LAZYPAY", "PAYTM WALLET"]),
    (PaymentMode.CARD,            ["POS ", "CARD", "SWIPE", "VISA", "MASTERCARD", "CONTACTLESS"]),
]


def detect_payment_mode(description: str) -> PaymentMode:
    upper = description.upper()
    for mode, keywords in _MODE_PATTERNS:
        if any(kw in upper for kw in keywords):
            return mode
    return PaymentMode.OTHER


def extract_reference(description: str) -> str | None:
    """Extract a transaction reference number from a bank description string."""
    # Indian UPI: UPI/merchant/name/123456789
    m = re.search(r"UPI/[^/]+/[^/]*/(\d{9,})", description, re.IGNORECASE)
    if m:
        return m.group(1)

    # UTR number (NEFT / RTGS / IMPS)
    m = re.search(r"UTR[:/\s]*([A-Z0-9]{12,22})", description, re.IGNORECASE)
    if m:
        return m.group(1)

    # IMPS reference
    m = re.search(r"IMPS[/\s]+(\d{12})", description, re.IGNORECASE)
    if m:
        return m.group(1)

    # US ACH / wire reference
    m = re.search(r"(?:REF|REFERENCE|CONF)[#:\s]*([A-Z0-9]{8,20})", description, re.IGNORECASE)
    if m:
        return m.group(1)

    # UK Faster Payments / BACS reference
    m = re.search(r"FPS[:/\s]*([A-Z0-9]{10,22})", description, re.IGNORECASE)
    if m:
        return m.group(1)

    # Cheque number
    m = re.search(r"(?:CHQ|CHEQUE|CHECK)[./\s#]*(\d{6,9})", description, re.IGNORECASE)
    if m:
        return m.group(1)

    return None


def clean_merchant_name(description: str) -> str | None:
    """
    Best-effort extraction of a human-readable merchant name from a raw bank
    description. Used as 'merchant_name' hint for categorisation — not shown
    as the primary label.
    """
    # Strip common prefixes
    cleaned = re.sub(
        r"^(POS|UPI|NEFT|IMPS|RTGS|ACH|WIRE|CARD|DEBIT|CREDIT|PURCHASE|PAYMENT)\s*[/:*-]?\s*",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip()
    # Strip trailing reference numbers
    cleaned = re.sub(r"\s+\d{6,}$", "", cleaned).strip()
    return cleaned[:100] if len(cleaned) > 3 else None
