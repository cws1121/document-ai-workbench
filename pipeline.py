"""Neural OCR plus deliberately constrained, evidence-linked invoice extraction."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

LABELS = {
    "supplier": "Supplier",
    "invoice_number": "Invoice number",
    "date": "Date",
    "currency": "Currency",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "total": "Total",
}


def extract(lines):
    fields = {}
    for key, label in LABELS.items():
        match = next(
            (
                x
                for x in lines
                if re.match(r"^" + re.escape(label) + r"\s*:", x["text"], re.IGNORECASE)
            ),
            None,
        )
        fields[key] = {
            "value": match["text"].split(":", 1)[1].strip() if match else "",
            "source": match["id"] if match else None,
            "ocr_score": match["score"] if match else None,
        }
    return fields


def validate(values):
    issues = []
    for key, label in LABELS.items():
        if not values.get(key, "").strip():
            issues.append(f"{label} is required.")
    try:
        date.fromisoformat(values.get("date", ""))
    except ValueError:
        issues.append("Date must use YYYY-MM-DD.")
    if values.get("currency") not in ("USD", "EUR", "PAB"):
        issues.append("Supported currencies: USD, EUR, PAB.")
    amounts = {}
    for key in ("subtotal", "tax", "total"):
        try:
            raw = values.get(key, "")
            if not re.fullmatch(r"\d{1,9}\.\d{2}", raw):
                raise InvalidOperation
            amounts[key] = Decimal(raw)
        except InvalidOperation:
            issues.append(
                f"{LABELS[key]} must be a nonnegative amount with two decimals."
            )
    if len(amounts) == 3 and amounts["subtotal"] + amounts["tax"] != amounts["total"]:
        issues.append(
            "Subtotal + tax does not equal total. Review the source before approving."
        )
    return issues
