import os
import httpx
import pikepdf
from io import BytesIO

_TIMEOUT = float(os.getenv("DOWNLOAD_TIMEOUT_S", "60"))
_MAX_MB = float(os.getenv("MAX_FILE_SIZE_MB", "30"))
_MAX_BYTES = _MAX_MB * 1024 * 1024


async def download_pdf(presigned_url: str, password: str | None = None) -> bytes:
    """Download PDF bytes from a presigned S3 URL."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(presigned_url)
        response.raise_for_status()

    raw = response.content
    if len(raw) > _MAX_BYTES:
        raise ValueError(f"File size {len(raw)} bytes exceeds {_MAX_MB} MB limit")

    if password:
        raw = _unlock_pdf(raw, password)

    return raw


def _unlock_pdf(pdf_bytes: bytes, password: str) -> bytes:
    """Decrypt a password-protected PDF and return unlocked bytes."""
    try:
        with pikepdf.open(BytesIO(pdf_bytes), password=password) as pdf:
            output = BytesIO()
            pdf.save(output)
            return output.getvalue()
    except pikepdf.PasswordError:
        raise ValueError("Incorrect PDF password")
    except Exception as exc:
        raise ValueError(f"Failed to unlock PDF: {exc}") from exc
