# PDF Bank Statement Parser

A universal bank statement parser that extracts structured transaction data from PDF, OFX, QFX, and CSV statements. Supports banks across India, US, UK, UAE, and Singapore — with optional OCR for scanned documents.

---

## Supported Banks

| Region | Banks |
|--------|-------|
| **India** | HDFC (bank + credit card), ICICI, SBI, Axis, Kotak |
| **US** | Chase, Bank of America, Wells Fargo, Amex |
| **UK** | Barclays, HSBC, Lloyds |
| **UAE** | Emirates NBD, FAB (First Abu Dhabi Bank) |
| **Singapore** | DBS |

Unsupported banks fall back to a generic parser that works for most standard formats.

---

## Installation

**Requirements:** Python 3.11+

```bash
# Core library only
pip install .

# With REST API (FastAPI)
pip install ".[api]"

# With CLI
pip install ".[cli]"

# With OCR (for scanned PDFs — requires Tesseract installed separately)
pip install ".[ocr]"

# Everything (recommended for development)
pip install ".[ocr,api,cli,dev]"
```

---

## Quick Start

### As a Python library

```python
from statement_parser import parse_statement

result = parse_statement("statement.pdf")

print(result.bank_code)          # e.g. "HDFC"
print(result.opening_balance)    # e.g. "12500.00"
print(result.closing_balance)    # e.g. "8200.00"

for txn in result.transactions:
    print(txn.transaction_date, txn.transaction_type, txn.amount, txn.raw_description)
```

With options:

```python
result = parse_statement(
    "statement.pdf",
    bank_code="HDFC",          # override auto-detection
    statement_type="BANK",     # "BANK" or "CREDIT_CARD"
    enable_ocr=True,           # for scanned PDFs
    date_hint="dmy",           # "dmy", "mdy", or "auto"
)
```

---

### As a CLI

```bash
# Parse and print JSON to terminal
statement-parser parse statement.pdf

# Save to file with pretty-print
statement-parser parse statement.pdf --out result.json --pretty

# Override bank detection
statement-parser parse statement.pdf --bank HDFC --type BANK

# Enable OCR for scanned PDFs
statement-parser parse statement.pdf --ocr

# List all supported bank codes
statement-parser banks
```

---

### As a REST API

**Start the server:**

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

**Parse a statement:**

```bash
curl -X POST http://localhost:8000/parse \
  -F "file=@statement.pdf" \
  -F "bank_code=HDFC" \
  -F "enable_ocr=false"
```

**Available endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/parse` | Parse a statement file |
| `GET` | `/health` | Health check |
| `GET` | `/banks` | List supported bank codes |

**`POST /parse` parameters (multipart form):**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `file` | Yes | PDF, OFX, QFX, or CSV file (max 25 MB) |
| `bank_code` | No | Override auto-detection (e.g. `HDFC`, `CHASE`) |
| `statement_type` | No | `BANK` or `CREDIT_CARD` |
| `enable_ocr` | No | `true` / `false` — enable OCR for scanned PDFs |
| `date_hint` | No | `dmy`, `mdy`, or `auto` |

---

## Output Format

Every parse returns a JSON object with this structure:

```json
{
  "success": true,
  "bank_code": "HDFC",
  "parser_used": "HDFCParser",
  "parser_version": "0.2.0",
  "file_hash": "sha256-hex-string",
  "metadata": {
    "bank_code": "HDFC",
    "statement_type": "BANK",
    "currency": "INR",
    "account_number_masked": "XXXX1234",
    "account_holder": "John Doe",
    "period": {
      "from_date": "2024-01-01",
      "to_date": "2024-01-31"
    },
    "account_type": "SAVINGS",
    "ifsc_code": "HDFC0001234"
  },
  "transactions": [
    {
      "transaction_date": "2024-01-05",
      "value_date": "2024-01-05",
      "raw_description": "UPI/SWIGGY/Payment",
      "amount": "450.00",
      "transaction_type": "DEBIT",
      "currency": "INR",
      "balance_after": "12050.00",
      "merchant_name": "Swiggy",
      "payment_mode": "UPI",
      "reference_number": null,
      "original_currency": null,
      "original_amount": null
    }
  ],
  "opening_balance": "12500.00",
  "closing_balance": "8200.00",
  "balance_validated": true,
  "warnings": [],
  "error": null,
  "ocr_attempted": false
}
```

**Credit card statements** include additional metadata fields: `credit_limit`, `available_credit`, `minimum_payment`, `payment_due_date`, `total_amount_due`, `total_purchases`, `total_payments`.

---

## Docker

```bash
# Build
docker build -t statement-parser .

# Run
docker run -p 8000:8000 statement-parser

# With custom config
docker run -p 8000:8000 \
  -e MAX_FILE_SIZE_MB=50 \
  -e LOG_LEVEL=DEBUG \
  statement-parser
```

The Docker image includes Tesseract OCR with English, Hindi, and Arabic language support.

---

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

```bash
MAX_FILE_SIZE_MB=30     # Max upload size for the API (default: 25)
LOG_LEVEL=INFO          # DEBUG or INFO
```

---

## Project Structure

```
statement_parser/       # Core library
  parsers/
    banks/
      india/            # HDFC, ICICI, SBI, Axis, Kotak
      us/               # Chase, Bank of America, Wells Fargo
      uk/               # Barclays, HSBC, Lloyds
      uae/              # Emirates NBD, FAB
      sg/               # DBS
    credit_card/        # Amex, generic credit card
    formats/            # OFX/QFX and CSV parsers
    generic.py          # Fallback parser for unknown banks
    detector.py         # Auto-detects bank from PDF content
  models/               # Transaction, Statement, Result data models
  utils/                # Date parsing, currency, balance validation, OCR

api/                    # FastAPI application
cli/                    # Click CLI application
tests/                  # Test suite
```

---

## Running Tests

```bash
pip install ".[dev]"
pytest
```
