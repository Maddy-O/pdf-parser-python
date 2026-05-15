"""
OCR utility — converts PDF pages to images and runs Tesseract.
All OCR dependencies (PyMuPDF, pytesseract, Pillow) are optional extras.
Import this module only at call time; never at module import in BaseParser.
"""


def ocr_pdf_bytes(pdf_bytes: bytes, lang: str = "eng+hin") -> str:
    """
    Render every page of a PDF to a 300 DPI image and run Tesseract OCR.
    Returns the full extracted text across all pages.

    Raises ImportError with an install hint when OCR extras are missing.
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise ImportError(
            f"OCR dependencies missing: {exc}. "
            "Install with: pip install 'statement-parser[ocr]'"
        ) from exc

    pages_text: list[str] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pages_text.append(pytesseract.image_to_string(img, lang=lang))
    doc.close()
    return "\n".join(pages_text)
