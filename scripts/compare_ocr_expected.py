"""Compare APFlow OCR JSON against a small expected-field JSON file.

Expected file example:
{
  "invoice_number": "INV-100",
  "vendor_name": "Northstar Components",
  "total_amount": 1170,
  "currency": "USD",
  "purchase_order_number": "PO-100"
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELD_ALIASES = {
    "invoice_number": "invoice_number",
    "vendor_name": "supplier_name",
    "vendor_tax_id": "supplier_tax_id",
    "invoice_date": "invoice_date",
    "due_date": "due_date",
    "currency": "currency",
    "subtotal": "subtotal",
    "tax_amount": "tax_total",
    "total_amount": "grand_total",
    "purchase_order_number": "po_number",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare OCR result JSON with expected fields")
    parser.add_argument("ocr_result", help="OCRExtractionResult JSON from scripts/test_azure_ocr.py")
    parser.add_argument("expected", help="Expected flat JSON fields")
    args = parser.parse_args()

    ocr = json.loads(Path(args.ocr_result).read_text(encoding="utf-8"))
    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    actual = {field["field_name"]: field for field in ocr.get("fields", [])}

    matched: dict[str, object] = {}
    mismatched: dict[str, dict[str, object]] = {}
    missing: dict[str, object] = {}

    for expected_name, expected_value in expected.items():
        actual_name = FIELD_ALIASES.get(expected_name, expected_name)
        field = actual.get(actual_name)
        if field is None or field.get("value") in (None, ""):
            missing[expected_name] = expected_value
            continue
        actual_value = field.get("value")
        if values_match(actual_value, expected_value):
            matched[expected_name] = actual_value
        else:
            mismatched[expected_name] = {
                "expected": expected_value,
                "actual": actual_value,
                "confidence": field.get("confidence"),
            }

    report = {
        "matched_fields": matched,
        "mismatched_fields": mismatched,
        "missing_fields": missing,
        "confidence_summary": ocr.get("confidence_summary", {}),
    }
    print(json.dumps(report, indent=2))
    return 1 if mismatched or missing else 0


def values_match(actual, expected) -> bool:
    if isinstance(expected, (int, float)):
        try:
            return abs(float(actual) - float(expected)) < 0.01
        except (TypeError, ValueError):
            return False
    return str(actual).strip().casefold() == str(expected).strip().casefold()


if __name__ == "__main__":
    raise SystemExit(main())
