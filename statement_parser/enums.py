from enum import Enum


class BankCode(str, Enum):
    # India
    HDFC = "HDFC"
    ICICI = "ICICI"
    SBI = "SBI"
    AXIS = "AXIS"
    KOTAK = "KOTAK"
    PNB = "PNB"
    BOB = "BOB"
    CANARA = "CANARA"
    INDUSIND = "INDUSIND"
    YES_BANK = "YES_BANK"
    IDFC = "IDFC"
    FEDERAL = "FEDERAL"
    # United States
    CHASE = "CHASE"
    BANK_OF_AMERICA = "BANK_OF_AMERICA"
    WELLS_FARGO = "WELLS_FARGO"
    CITI_US = "CITI_US"
    CAPITAL_ONE = "CAPITAL_ONE"
    AMEX = "AMEX"
    # United Kingdom
    BARCLAYS = "BARCLAYS"
    HSBC_UK = "HSBC_UK"
    LLOYDS = "LLOYDS"
    NATWEST = "NATWEST"
    SANTANDER_UK = "SANTANDER_UK"
    # UAE
    EMIRATES_NBD = "EMIRATES_NBD"
    FAB = "FAB"
    ADCB = "ADCB"
    DIB = "DIB"
    # Singapore
    DBS = "DBS"
    OCBC = "OCBC"
    UOB = "UOB"
    # Fallback
    GENERIC = "GENERIC"


class Currency(str, Enum):
    INR = "INR"   # Indian Rupee
    USD = "USD"   # US Dollar
    GBP = "GBP"   # British Pound
    AED = "AED"   # UAE Dirham
    SGD = "SGD"   # Singapore Dollar
    EUR = "EUR"   # Euro
    AUD = "AUD"   # Australian Dollar
    CAD = "CAD"   # Canadian Dollar
    JPY = "JPY"   # Japanese Yen
    CHF = "CHF"   # Swiss Franc
    HKD = "HKD"   # Hong Kong Dollar
    NZD = "NZD"   # New Zealand Dollar
    UNKNOWN = "UNKNOWN"


class StatementType(str, Enum):
    BANK = "BANK"
    CREDIT_CARD = "CREDIT_CARD"
    LOAN = "LOAN"


class TransactionType(str, Enum):
    DEBIT = "DEBIT"    # Money out / purchase charged / expense
    CREDIT = "CREDIT"  # Money in / payment made / income


class PaymentMode(str, Enum):
    UPI = "UPI"
    NEFT = "NEFT"
    RTGS = "RTGS"
    IMPS = "IMPS"
    CARD = "CARD"
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    WALLET = "WALLET"
    ACH = "ACH"               # US/international direct debit
    WIRE = "WIRE"             # International wire transfer
    FASTER_PAYMENTS = "FASTER_PAYMENTS"  # UK instant transfer
    BACS = "BACS"             # UK bank transfer
    SEPA = "SEPA"             # European transfer
    OTHER = "OTHER"
