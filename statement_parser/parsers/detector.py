import pdfplumber
from io import BytesIO
from statement_parser.enums import BankCode, StatementType

# Bank detection signatures — checked against first-page text (uppercased)
_SIGNATURES: dict[BankCode, list[str]] = {
    # India
    BankCode.HDFC:          ["HDFC BANK", "HDFC BANK LIMITED", "HDFCBANK"],
    BankCode.ICICI:         ["ICICI BANK", "ICICI BANK LIMITED", "ICICIBANKLTD"],
    BankCode.SBI:           ["STATE BANK OF INDIA", "STATE BANK OF  INDIA"],
    BankCode.AXIS:          ["AXIS BANK", "AXIS BANK LIMITED"],
    BankCode.KOTAK:         ["KOTAK MAHINDRA BANK", "KOTAK MAHINDRA", "KOTAK BANK"],
    BankCode.PNB:           ["PUNJAB NATIONAL BANK"],
    BankCode.BOB:           ["BANK OF BARODA"],
    BankCode.CANARA:        ["CANARA BANK"],
    BankCode.INDUSIND:      ["INDUSIND BANK"],
    BankCode.YES_BANK:      ["YES BANK"],
    BankCode.IDFC:          ["IDFC FIRST BANK", "IDFC BANK"],
    BankCode.FEDERAL:       ["FEDERAL BANK", "THE FEDERAL BANK"],
    # United States
    BankCode.CHASE:         ["JPMORGAN CHASE", "CHASE BANK", "CHASE.COM", "CHASE FREEDOM", "CHASE SAPPHIRE"],
    BankCode.BANK_OF_AMERICA: ["BANK OF AMERICA", "BANKOFAMERICA", "BOFA"],
    BankCode.WELLS_FARGO:   ["WELLS FARGO", "WELLSFARGO.COM"],
    BankCode.CITI_US:       ["CITIBANK", "CITI BANK", "CITICARDS.COM"],
    BankCode.CAPITAL_ONE:   ["CAPITAL ONE", "CAPITALONE.COM"],
    BankCode.AMEX:          ["AMERICAN EXPRESS", "AMERICANEXPRESS", "AMEX"],
    # United Kingdom
    BankCode.BARCLAYS:      ["BARCLAYS BANK", "BARCLAYS PLC", "BARCLAYS.CO.UK"],
    BankCode.HSBC_UK:       ["HSBC BANK PLC", "HSBC UK", "HSBC.CO.UK"],
    BankCode.LLOYDS:        ["LLOYDS BANK", "LLOYDS BANKING GROUP", "LLOYDS.COM"],
    BankCode.NATWEST:       ["NATWEST BANK", "NATIONAL WESTMINSTER", "NATWEST.COM"],
    BankCode.SANTANDER_UK:  ["SANTANDER UK", "SANTANDER.CO.UK"],
    # UAE
    BankCode.EMIRATES_NBD:  ["EMIRATES NBD", "ENBD", "EMIRATESNBD.COM"],
    BankCode.FAB:           ["FIRST ABU DHABI BANK", "FAB BANK"],
    BankCode.ADCB:          ["ABU DHABI COMMERCIAL", "ADCB.COM"],
    BankCode.DIB:           ["DUBAI ISLAMIC BANK"],
    # Singapore
    BankCode.DBS:           ["DBS BANK", "DBS GROUP", "DBS.COM"],
    BankCode.OCBC:          ["OCBC BANK", "OVERSEA-CHINESE BANKING"],
    BankCode.UOB:           ["UNITED OVERSEAS BANK", "UOB.COM"],
}

# Keywords that indicate credit card (vs bank account) statement
_CC_KEYWORDS = [
    "CREDIT CARD STATEMENT",
    "CARD STATEMENT",
    "OUTSTANDING BALANCE",
    "MINIMUM AMOUNT DUE",
    "MINIMUM PAYMENT DUE",
    "CREDIT LIMIT",
    "AVAILABLE CREDIT",
    "STATEMENT BALANCE",
    "NEW BALANCE",
]


def detect_bank(pdf_bytes: bytes) -> BankCode:
    """Return BankCode from first-page text, or GENERIC if unrecognised."""
    text = _first_page_text(pdf_bytes).upper()
    for bank_code, sigs in _SIGNATURES.items():
        if any(sig in text for sig in sigs):
            return bank_code
    return BankCode.GENERIC


def detect_statement_type(pdf_bytes: bytes) -> StatementType:
    """Return CREDIT_CARD if CC keywords found, else BANK."""
    text = _first_page_text(pdf_bytes).upper()
    if any(kw in text for kw in _CC_KEYWORDS):
        return StatementType.CREDIT_CARD
    return StatementType.BANK


def _first_page_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            if pdf.pages:
                return pdf.pages[0].extract_text() or ""
    except Exception:
        pass
    return ""
