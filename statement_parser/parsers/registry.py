from statement_parser.enums import BankCode, StatementType
from statement_parser.parsers.base import BaseParser


class ParserRegistry:
    def __init__(self) -> None:
        self._map: dict[tuple[BankCode, StatementType], type[BaseParser]] = {}

    def register(
        self,
        bank_code: BankCode,
        parser_cls: type[BaseParser],
        statement_type: StatementType = StatementType.BANK,
    ) -> None:
        self._map[(bank_code, statement_type)] = parser_cls

    def get(
        self,
        bank_code: BankCode,
        statement_type: StatementType = StatementType.BANK,
    ) -> BaseParser:
        """Return a parser instance. Falls back to GENERIC if no exact match."""
        cls = self._map.get((bank_code, statement_type))
        if cls is None and statement_type == StatementType.CREDIT_CARD:
            # Try generic CC parser, then generic bank parser
            cls = self._map.get((BankCode.GENERIC, StatementType.CREDIT_CARD))
        if cls is None:
            cls = self._map.get((BankCode.GENERIC, StatementType.BANK))
        if cls is None:
            from statement_parser.parsers.generic import GenericParser
            return GenericParser()
        return cls()

    def list_supported(self) -> list[tuple[BankCode, StatementType]]:
        return list(self._map.keys())


def _build_default_registry() -> ParserRegistry:
    reg = ParserRegistry()

    # ── India ──────────────────────────────────────────────────────────
    from statement_parser.parsers.banks.india.hdfc import HdfcParser
    from statement_parser.parsers.banks.india.hdfc_credit import HdfcCreditParser
    from statement_parser.parsers.banks.india.icici import IciciParser
    from statement_parser.parsers.banks.india.sbi import SbiParser
    from statement_parser.parsers.banks.india.axis import AxisParser
    from statement_parser.parsers.banks.india.kotak import KotakParser

    reg.register(BankCode.HDFC, HdfcParser)
    reg.register(BankCode.HDFC, HdfcCreditParser, StatementType.CREDIT_CARD)
    reg.register(BankCode.ICICI, IciciParser)
    reg.register(BankCode.SBI, SbiParser)
    reg.register(BankCode.AXIS, AxisParser)
    reg.register(BankCode.KOTAK, KotakParser)

    # ── United States ──────────────────────────────────────────────────
    from statement_parser.parsers.banks.us.chase import ChaseParser, ChaseCreditParser
    from statement_parser.parsers.banks.us.bank_of_america import BankOfAmericaParser, BankOfAmericaCreditParser
    from statement_parser.parsers.banks.us.wells_fargo import WellsFargoParser

    reg.register(BankCode.CHASE, ChaseParser)
    reg.register(BankCode.CHASE, ChaseCreditParser, StatementType.CREDIT_CARD)
    reg.register(BankCode.BANK_OF_AMERICA, BankOfAmericaParser)
    reg.register(BankCode.BANK_OF_AMERICA, BankOfAmericaCreditParser, StatementType.CREDIT_CARD)
    reg.register(BankCode.WELLS_FARGO, WellsFargoParser)

    # ── United Kingdom ─────────────────────────────────────────────────
    from statement_parser.parsers.banks.uk.barclays import BarclaysParser
    from statement_parser.parsers.banks.uk.hsbc import HsbcParser
    from statement_parser.parsers.banks.uk.lloyds import LloydsParser

    reg.register(BankCode.BARCLAYS, BarclaysParser)
    reg.register(BankCode.HSBC_UK, HsbcParser)
    reg.register(BankCode.LLOYDS, LloydsParser)

    # ── UAE ────────────────────────────────────────────────────────────
    from statement_parser.parsers.banks.uae.emirates_nbd import EmiratesNBDParser
    from statement_parser.parsers.banks.uae.fab import FabParser

    reg.register(BankCode.EMIRATES_NBD, EmiratesNBDParser)
    reg.register(BankCode.FAB, FabParser)

    # ── Singapore ──────────────────────────────────────────────────────
    from statement_parser.parsers.banks.sg.dbs import DbsParser

    reg.register(BankCode.DBS, DbsParser)

    # ── Credit card (generic) ──────────────────────────────────────────
    from statement_parser.parsers.credit_card.generic_cc import GenericCreditCardParser
    from statement_parser.parsers.credit_card.amex import AmexParser

    reg.register(BankCode.GENERIC, GenericCreditCardParser, StatementType.CREDIT_CARD)
    reg.register(BankCode.AMEX, AmexParser, StatementType.CREDIT_CARD)

    # ── Fallback ───────────────────────────────────────────────────────
    from statement_parser.parsers.generic import GenericParser

    reg.register(BankCode.GENERIC, GenericParser)

    return reg


DEFAULT_REGISTRY = _build_default_registry()
