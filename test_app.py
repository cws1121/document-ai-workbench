import json
from io import BytesIO

import app
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pipeline import extract, validate

VALUES = {
    "supplier": "Demo",
    "invoice_number": "INV-1",
    "date": "2026-09-17",
    "currency": "USD",
    "subtotal": "200.00",
    "tax": "14.00",
    "total": "214.00",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB", tmp_path / "test.sqlite3")
    doc = {
        "id": "test",
        "revision": 0,
        "values": VALUES,
        "issues": [],
        "extracted": {},
        "audit": [],
        "status": "needs_review",
    }
    with app.connect() as db:
        db.execute("INSERT INTO docs VALUES (?,?)", ("test", json.dumps(doc)))
    return TestClient(app.app)


def test_exact_decimal_and_invalid_values():
    assert validate(VALUES) == []
    assert validate({**VALUES, "total": "219.00"})
    for bad in ("NaN", "Infinity", "-1.00", "1,000.00", "0.001", ""):
        assert validate({**VALUES, "tax": bad})


def test_missing_source_stays_empty_and_total_not_subtotal():
    fields = extract([{"id": 0, "text": "Subtotal: 200.00", "score": 0.99}])
    assert fields["total"]["value"] == ""
    assert fields["total"]["source"] is None
    assert fields["subtotal"]["source"] == 0


def test_review_rejects_inconsistent_invoice(client):
    r = client.post(
        "/api/documents/test/review",
        json={
            "revision": 0,
            "values": {**VALUES, "total": "219.00"},
            "note": "checked",
            "approve": True,
        },
    )
    assert r.status_code == 422
    assert client.get("/api/documents/test").json()["revision"] == 0


def test_audit_and_stale_revision(client):
    payload = {
        "revision": 0,
        "values": {**VALUES, "supplier": "Corrected supplier"},
        "note": "Checked source",
        "approve": True,
    }
    d = client.post("/api/documents/test/review", json=payload).json()
    assert d["status"] == "approved" and d["revision"] == 1
    assert d["audit"][0]["changes"]["supplier"] == {
        "before": "Demo",
        "after": "Corrected supplier",
    }
    assert client.post("/api/documents/test/review", json=payload).status_code == 409
    assert client.get("/api/documents/test/export").json()["audit"] == d["audit"]


def test_image_validation_and_size():
    with pytest.raises(app.HTTPException):
        app.normalize(b"not an image")
    with pytest.raises(app.HTTPException) as e:
        app.normalize(b"x" * (8 * 1024 * 1024 + 1))
    assert e.value.status_code == 413
    image = Image.new("RGB", (20, 20))
    buf = BytesIO()
    image.save(buf, format="PNG")
    assert app.normalize(buf.getvalue()).size == (20, 20)


def test_origin_rejected(client):
    assert (
        client.post(
            "/api/sample/clean", headers={"Origin": "https://example.com"}
        ).status_code
        == 403
    )
