import logging

from fastapi import APIRouter, HTTPException

from app.models.request import ParseRequest
from app.models.response import ParseResponse
from app.utils.pdf_loader import download_pdf
from app.utils.bank_detector import detect_bank
from app.parsers.registry import get_parser

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/parse", response_model=ParseResponse)
async def parse_statement(req: ParseRequest) -> ParseResponse:
    """
    Download a bank statement PDF from a presigned S3 URL and extract
    all transactions. Returns structured JSON regardless of success/failure.
    HTTP 200 always; check `success` field in the response body.
    """
    logger.info(
        "Parse request received",
        extra={"statement_id": req.statement_id, "bank_hint": req.bank_name},
    )

    # 1. Download PDF bytes
    try:
        pdf_bytes = await download_pdf(req.presigned_url, req.password)
    except ValueError as exc:
        logger.warning(
            "PDF download/unlock failed",
            extra={"statement_id": req.statement_id, "error": str(exc)},
        )
        return ParseResponse(
            success=False,
            parser_version="unknown",
            error_code="DOWNLOAD_FAILED",
            error_message=str(exc),
        )
    except Exception as exc:
        logger.error(
            "Unexpected error during PDF download",
            exc_info=exc,
            extra={"statement_id": req.statement_id},
        )
        return ParseResponse(
            success=False,
            parser_version="unknown",
            error_code="DOWNLOAD_ERROR",
            error_message=f"Failed to fetch PDF: {exc}",
        )

    # 2. Auto-detect bank if no hint provided
    bank_key = req.bank_name or detect_bank(pdf_bytes)
    logger.info(
        "Bank detected",
        extra={"statement_id": req.statement_id, "bank": bank_key},
    )

    # 3. Select parser and run
    parser = get_parser(bank_key)
    result = parser.parse(pdf_bytes, req.statement_id)

    logger.info(
        "Parse completed",
        extra={
            "statement_id": req.statement_id,
            "success": result.success,
            "transaction_count": len(result.transactions),
            "balance_validated": result.balance_validated,
            "ocr_attempted": result.ocr_attempted,
        },
    )

    return result
