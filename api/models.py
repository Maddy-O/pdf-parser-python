"""
Request / response models for the FastAPI layer.
These are thin wrappers over the library's Pydantic models.
"""
from typing import Optional
from pydantic import BaseModel


class ParseRequest(BaseModel):
    bank_code: Optional[str] = None
    statement_type: Optional[str] = None
    enable_ocr: bool = False
    date_hint: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
