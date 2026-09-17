"""Real OCR smoke evaluation; tiny synthetic fixture, not a general accuracy benchmark."""

import json
from pathlib import Path

from pipeline import extract, validate
from rapidocr_onnxruntime import RapidOCR

expected = {
    "supplier": "Pacific Demo Supplies",
    "invoice_number": "INV-2026-041",
    "date": "2026-09-17",
    "currency": "USD",
    "subtotal": "200.00",
    "tax": "14.00",
    "total": "214.00",
}


def main():
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
    results = []
    for name in ("clean", "mismatch", "soft-scan"):
        raw, _ = engine(str(Path(__file__).parent / "samples" / f"{name}.png"))
        lines = [
            {"id": i, "box": b, "text": t, "score": float(s)}
            for i, (b, t, s) in enumerate(raw or [])
        ]
        values = {k: v["value"] for k, v in extract(lines).items()}
        truth = {**expected, "total": "219.00" if name == "mismatch" else "214.00"}
        results.append(
            {
                "sample": name,
                "exact_fields": sum(values[k] == truth[k] for k in truth),
                "fields": len(truth),
                "values": values,
                "issues": validate(values),
            }
        )
    report = {
        "scope": "Three synthetic template fixtures; not a general document accuracy claim",
        "results": results,
    }
    print(json.dumps(report, indent=2))
    # Clean fixtures must remain exact. The degraded scan intentionally exercises
    # abstention/review; report its measured accuracy rather than masking errors.
    assert results[0]["exact_fields"] == 7 and results[1]["exact_fields"] == 7
    assert results[0]["issues"] == [] and results[1]["issues"]
    assert results[2]["exact_fields"] >= 4
    if not results[2]["values"]["invoice_number"]:
        assert "Invoice number is required." in results[2]["issues"]


if __name__ == "__main__":
    main()
