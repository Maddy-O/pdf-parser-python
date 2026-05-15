import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.parse import router as parse_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="Life App — Statement Parser",
    description="Extracts transactions from Indian bank statement PDFs",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

# Only the NestJS backend should call this service — restrict in prod via network policy.
# CORS is left open here so the Docker-internal calls work without origin headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(parse_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "statement-parser"}
