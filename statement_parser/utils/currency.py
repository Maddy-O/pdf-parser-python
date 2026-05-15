import re
from decimal import Decimal, InvalidOperation
from statement_parser.enums import Currency

# Symbol / code → Currency enum
_SYMBOL_MAP: dict[str, Currency] = {
    "₹": Currency.INR,
    "RS.": Currency.INR,
    "INR": Currency.INR,
    "$": Currency.USD,
    "USD": Currency.USD,
    "£": Currency.GBP,
    "GBP": Currency.GBP,
    "€": Currency.EUR,
    "EUR": Currency.EUR,
    "AED": Currency.AED,
    "دإ": Currency.AED,
    "S$": Currency.SGD,
    "SGD": Currency.SGD,
    "A$": Currency.AUD,
    "AUD": Currency.AUD,
    "C$": Currency.CAD,
    "CAD": Currency.CAD,
    "¥": Currency.JPY,
    "JPY": Currency.JPY,
    "CHF": Currency.CHF,
    "HK$": Currency.HKD,
    "HKD": Currency.HKD,
    "NZ$": Currency.NZD,
    "NZD": Currency.NZD,
}

# Currencies where amounts use European-style formatting (period as thousands separator)
_EUROPEAN_STYLE = {Currency.EUR, Currency.CHF}


def clean_amount(raw: str | None, currency: Currency = Currency.UNKNOWN) -> str | None:
    """
    Strip currency symbols and thousands separators.
    Returns a decimal string like "1299.00" or None.

    Handles:
    - Indian lakh format: "1,23,456.78"
    - Standard format: "1,234,567.89"
    - European format: "1.234.567,89" (when currency hint is EUR/CHF)
    - Negative in parentheses: "(1,299.00)" — used by US banks
    - Signed: "-1299.00" or "+1299.00"
    - Trailing indicator: "1,299.00 DR" or "1,299.00 CR"
    """
    if not raw:
        return None

    s = str(raw).strip()

    # Strip currency symbols (longest first to avoid partial matches)
    for sym in sorted(_SYMBOL_MAP, key=len, reverse=True):
        s = s.replace(sym, "").strip()

    # Strip trailing DR/CR/D/C indicators (used by some UK/Indian banks)
    s = re.sub(r"\s+(DR|CR|D|C)$", "", s, flags=re.IGNORECASE).strip()

    # Convert European-style (1.234,56 → 1234.56) when hinted
    if currency in _EUROPEAN_STYLE:
        s = s.replace(".", "").replace(",", ".")
    else:
        # Standard or Indian: remove commas
        s = s.replace(",", "")

    # Parentheses = negative amount, e.g. "(1299.00)" → "-1299.00"
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]

    # Remove leading + sign
    s = s.lstrip("+").strip()

    try:
        return f"{Decimal(s):.2f}"
    except InvalidOperation:
        return None


def detect_currency(text: str) -> Currency:
    """Scan text for the most specific currency symbol/code and return it."""
    upper = text.upper()
    # Check multi-char codes first (more specific than single-char symbols)
    for sym, currency in sorted(_SYMBOL_MAP.items(), key=lambda x: -len(x[0])):
        if sym.upper() in upper:
            return currency
    return Currency.UNKNOWN


def is_negative_amount(raw: str) -> bool:
    """Return True if the raw amount string represents a negative value (debit indicator)."""
    s = raw.strip()
    return s.startswith("-") or (s.startswith("(") and s.endswith(")"))
