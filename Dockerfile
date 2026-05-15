FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    tesseract-ocr-ara \
    ghostscript \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the library first (layer-cached unless pyproject.toml changes)
COPY pyproject.toml .
COPY statement_parser/ ./statement_parser/
RUN pip install --no-cache-dir -e ".[ocr]"

# Install API-specific deps
COPY requirements-api.txt .
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx python-dotenv

# Copy API layer
COPY api/ ./api/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
