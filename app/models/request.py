from pydantic import BaseModel
from typing import Optional


class ParseRequest(BaseModel):
    presigned_url: str
    bank_name: Optional[str] = None  # hint; auto-detected from PDF text if None
    statement_id: str                # for structured logging only — not stored
    password: Optional[str] = None   # for password-protected PDFs
