import pdfplumber
from io import BytesIO

# Maps bank key → list of text signatures to look for on the first page
_SIGNATURES: dict[str, list[str]] = {
    "HDFC":    ["HDFC BANK", "HDFCBANK", "HDFC BANK LIMITED"],
    "ICICI":   ["ICICI BANK", "ICICI BANK LIMITED", "ICICIBANKLTD"],
    "SBI":     ["STATE BANK OF INDIA", "STATE BANK OF  INDIA", "SBI"],
    "AXIS":    ["AXIS BANK", "AXIS BANK LIMITED"],
    "KOTAK":   ["KOTAK MAHINDRA BANK", "KOTAK MAHINDRA", "KOTAK BANK"],
    "PNB":     ["PUNJAB NATIONAL BANK", "PNB BANK"],
    "BOB":     ["BANK OF BARODA", "BOB BANK"],
    "CANARA":  ["CANARA BANK"],
    "INDUSIND":["INDUSIND BANK", "INDUSIND BANK LIMITED"],
    "YESBANK": ["YES BANK", "YES BANK LIMITED"],
    "IDFC":    ["IDFC FIRST BANK", "IDFC BANK"],
    "FEDERAL": ["FEDERAL BANK", "THE FEDERAL BANK"],
    "RBL":     ["RBL BANK", "RATNAKAR BANK"],
    "UCO":     ["UCO BANK"],
    "IOB":     ["INDIAN OVERSEAS BANK", "IOB"],
}


def detect_bank(pdf_bytes: bytes) -> str:
    """Return the bank key (e.g. 'HDFC') or 'GENERIC' if unrecognised."""
    try:
        text = _extract_first_page_text(pdf_bytes).upper()
    except Exception:
        return "GENERIC"

    for bank_key, signatures in _SIGNATURES.items():
        if any(sig in text for sig in signatures):
            return bank_key

    return "GENERIC"


def _extract_first_page_text(pdf_bytes: bytes) -> str:
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        if not pdf.pages:
            return ""
        return pdf.pages[0].extract_text() or ""
