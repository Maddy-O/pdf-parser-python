from app.parsers.base import BaseParser
from app.parsers.banks.hdfc import HdfcParser
from app.parsers.banks.icici import IciciParser
from app.parsers.banks.sbi import SbiParser
from app.parsers.banks.axis import AxisParser
from app.parsers.banks.kotak import KotakParser
from app.parsers.generic import GenericParser

_REGISTRY: dict[str, type[BaseParser]] = {
    "HDFC":     HdfcParser,
    "ICICI":    IciciParser,
    "SBI":      SbiParser,
    "AXIS":     AxisParser,
    "KOTAK":    KotakParser,
}


def get_parser(bank_name: str | None) -> BaseParser:
    """Return the correct parser instance for the given bank key."""
    if bank_name:
        cls = _REGISTRY.get(bank_name.upper())
        if cls:
            return cls()
    return GenericParser()
