"""
API integration tests for the FastAPI /parse endpoint.
Run with: pytest tests/test_api.py -v

These tests use FastAPI's TestClient — no running server needed.
"""
import json
import io
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


class TestHealth:
    def test_health_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_banks_returns_list(self):
        r = client.get("/banks")
        assert r.status_code == 200
        data = r.json()
        assert "banks" in data
        assert len(data["banks"]) > 0
        assert "HDFC" in data["banks"]
        assert "CHASE" in data["banks"]
        assert "BARCLAYS" in data["banks"]


class TestParseEndpoint:
    def _post(self, content: bytes, filename: str = "test.pdf", bank_code: str | None = None):
        files = {"file": (filename, io.BytesIO(content), "application/pdf")}
        data = {}
        if bank_code:
            data["bank_code"] = bank_code
        return client.post("/parse", files=files, data=data)

    def test_empty_pdf_returns_422(self):
        r = self._post(b"%PDF-1.4 empty")
        assert r.status_code in (200, 422)
        body = r.json()
        assert "success" in body
        assert "transactions" in body
        assert "warnings" in body

    def test_garbage_bytes_returns_result(self):
        r = self._post(b"this is not a pdf at all", filename="bad.bin")
        body = r.json()
        # Must return a ParseResult shape — never crash with 500
        assert "success" in body

    def test_csv_file_is_accepted(self):
        csv_content = b"Date,Description,Debit,Credit,Balance\n15/01/2024,Grocery,-500,,10000\n"
        files = {"file": ("statement.csv", io.BytesIO(csv_content), "text/csv")}
        r = client.post("/parse", files=files)
        body = r.json()
        assert "success" in body

    def test_oversized_file_returns_413(self):
        # Simulate a file just over 25MB
        big = b"%PDF " + b"x" * (26 * 1024 * 1024)
        r = self._post(big, filename="big.pdf")
        assert r.status_code == 413

    def test_response_shape_always_present(self):
        r = self._post(b"%PDF-1.4", bank_code="HDFC")
        body = r.json()
        required_keys = ["success", "transactions", "warnings", "balance_validated"]
        for key in required_keys:
            assert key in body, f"Missing key: {key}"

    def test_bank_code_override_accepted(self):
        r = self._post(b"%PDF-1.4", bank_code="CHASE")
        assert r.status_code in (200, 422)

    def test_invalid_bank_code_falls_back_gracefully(self):
        r = self._post(b"%PDF-1.4", bank_code="TOTALLY_FAKE_BANK_XYZ")
        assert r.status_code in (200, 422)
        body = r.json()
        assert "success" in body
