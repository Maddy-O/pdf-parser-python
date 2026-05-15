"""
CLI entry point for statement-parser.

Usage:
    statement-parser parse statement.pdf
    statement-parser parse statement.pdf --bank HDFC --type BANK --out result.json
    statement-parser parse statement.pdf --ocr
    statement-parser banks
"""
import sys
import json
import click


@click.group()
@click.version_option(package_name="statement-parser")
def cli():
    """Universal bank statement parser — PDF, OFX, QFX, CSV."""


@cli.command()
@click.argument("file", type=click.Path(exists=True, readable=True))
@click.option("--bank", default=None, help="Override bank detection (e.g. HDFC, CHASE, BARCLAYS)")
@click.option("--type", "stmt_type", default=None, help="BANK or CREDIT_CARD")
@click.option("--ocr", is_flag=True, default=False, help="Enable OCR for scanned PDFs")
@click.option("--date-hint", default=None, help="Date format hint: dmy, mdy, auto")
@click.option("--out", default=None, type=click.Path(), help="Write JSON output to file instead of stdout")
@click.option("--pretty/--compact", default=True, help="Pretty-print JSON output")
def parse(file, bank, stmt_type, ocr, date_hint, out, pretty):
    """Parse a statement file and output JSON."""
    from statement_parser import StatementParser

    with open(file, "rb") as fh:
        file_bytes = fh.read()

    result = StatementParser.parse(
        file_bytes,
        bank_code=bank,
        statement_type=stmt_type,
        enable_ocr=ocr,
        date_hint=date_hint,
    )

    indent = 2 if pretty else None
    output = json.dumps(result.model_dump(mode="json"), indent=indent, default=str)

    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(output)
        click.echo(f"Written to {out}")
    else:
        click.echo(output)

    if not result.success:
        sys.exit(1)


@cli.command()
def banks():
    """List all supported bank codes."""
    from statement_parser import StatementParser

    for code in sorted(StatementParser.supported_banks()):
        click.echo(code)


if __name__ == "__main__":
    cli()
