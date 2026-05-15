"""
FastAPI application — thin HTTP wrapper around statement_parser library.

Endpoints:
    POST /parse          — parse uploaded statement file
    GET  /health         — liveness probe
    GET  /banks          — list supported bank codes
"""
import logging
import os
import time

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from statement_parser import StatementParser, __version__
from api.models import HealthResponse

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "25")) * 1024 * 1024

logging.basicConfig(
    level=logging.DEBUG if os.getenv("LOG_LEVEL", "info").lower() == "debug" else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("parser-api")

app = FastAPI(
    title="Statement Parser API",
    description="Parse bank and credit card statements (PDF, OFX, CSV)",
    version=__version__,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(
        "%s %s → %s  (%dms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    return HealthResponse(status="ok", version=__version__)


@app.get("/banks", tags=["meta"])
def supported_banks():
    return {"banks": StatementParser.supported_banks()}


@app.post("/parse", tags=["parse"])
async def parse_statement(
    file: UploadFile = File(..., description="PDF, OFX, QFX, or CSV statement file"),
    bank_code: str = Form(None, description="Override bank detection (e.g. HDFC, CHASE)"),
    statement_type: str = Form(None, description="BANK or CREDIT_CARD"),
    enable_ocr: bool = Form(False, description="Enable OCR fallback for scanned PDFs"),
    date_hint: str = Form(None, description="dmy, mdy, or auto"),
):
    file_bytes = await file.read()
    file_size_kb = round(len(file_bytes) / 1024, 1)

    logger.info(
        "Parse request — file=%s  size=%sKB  bank_code=%s  type=%s  ocr=%s",
        file.filename,
        file_size_kb,
        bank_code or "auto",
        statement_type or "auto",
        enable_ocr,
    )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024*1024)} MB",
        )

    t0 = time.perf_counter()
    result = StatementParser.parse(
        file_bytes,
        bank_code=bank_code,
        statement_type=statement_type,
        enable_ocr=enable_ocr,
        date_hint=date_hint,
    )
    parse_ms = round((time.perf_counter() - t0) * 1000)

    logger.info(
        "Parse complete — success=%s  parser=%s  bank=%s  transactions=%d  "
        "balance_ok=%s  warnings=%d  duration=%dms",
        result.success,
        result.parser_used or "—",
        result.bank_code or "—",
        len(result.transactions),
        result.balance_validated,
        len(result.warnings),
        parse_ms,
    )

    if result.warnings:
        for w in result.warnings:
            logger.warning("  Parser warning: %s", w)

    if not result.success:
        logger.error("Parse failed — %s: %s", result.error.code if result.error else "?", result.error.message if result.error else "unknown")

    status_code = 200 if result.success else 422
    return JSONResponse(
        status_code=status_code,
        content=result.model_dump(mode="json"),
    )
