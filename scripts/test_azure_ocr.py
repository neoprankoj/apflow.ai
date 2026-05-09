"""Run a live Azure Document Intelligence invoice OCR check.

This script calls the APFlow Azure adapter directly. It requires Azure
credentials in environment variables and never prints the key.

Example:
    python scripts/test_azure_ocr.py samples/invoices/invoice.pdf --out samples/ocr-results/invoice.json
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.integrations.ocr.cloud import AzureDocumentIntelligenceOCRAdapter  # noqa: E402


FIELD_ALIASES = {
    "invoice_number": "invoice_number",
    "invoice_date": "invoice_date",
    "due_date": "due_date",
    "supplier_name": "vendor_name",
    "supplier_tax_id": "vendor_tax_id",
    "currency": "currency",
    "subtotal": "subtotal",
    "tax_total": "tax_amount",
    "grand_total": "total_amount",
    "po_number": "purchase_order_number",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Azure OCR against a local invoice PDF/image")
    parser.add_argument("file", help="Path to a local PDF, PNG, or JPEG invoice")
    parser.add_argument("--tenant-id", default=str(uuid4()))
    parser.add_argument("--out", help="Optional JSON output path, usually under samples/ocr-results/")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists() or not path.is_file():
        raise SystemExit(f"Invoice file not found: {path}")

    settings = Settings(ocr_provider="azure")
    adapter = AzureDocumentIntelligenceOCRAdapter(settings)
    if not adapter.is_configured():
        raise SystemExit(
            "Azure OCR is not configured. Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT "
            "and AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )

    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    result = adapter.extract_invoice(
        {"content": path.read_bytes(), "mime_type": content_type, "file_name": path.name},
        args.tenant_id,
    )
    payload = result.model_dump(mode="json")

    print_summary(payload)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON written to {out}")

    return 1 if result.error else 0


def print_summary(payload: dict) -> None:
    print("Azure OCR extraction")
    print(f"provider_status: {payload['provider_metadata']['raw_provider_status']}")
    if payload.get("error"):
        print(f"error: {payload['error']}")

    fields = {field["field_name"]: field for field in payload.get("fields", [])}
    print("\nFields")
    for source_name, label in FIELD_ALIASES.items():
        field = fields.get(source_name, {})
        value = field.get("value")
        confidence = field.get("confidence", 0)
        review = "yes" if field.get("requires_review") else "no"
        print(f"- {label}: {value!r} confidence={confidence:.2f} review_required={review}")

    print("\nLine items")
    for index, line in enumerate(payload.get("line_items", []), start=1):
        mapped = {field["field_name"]: field for field in line.get("fields", [])}
        description = mapped.get("description", {}).get("value")
        total = mapped.get("total", {}).get("value")
        confidence = line.get("confidence", 0)
        print(f"- line {index}: description={description!r} total={total!r} confidence={confidence:.2f}")

    summary = payload["confidence_summary"]
    print("\nConfidence summary")
    print(f"average_confidence: {summary['average_confidence']:.2f}")
    print(f"low_confidence_fields: {summary['low_confidence_fields']}")
    print(f"required_fields_missing: {summary['required_fields_missing']}")
    print(f"required_fields_low_confidence: {summary['required_fields_low_confidence']}")

    review_fields = [
        field["field_name"]
        for field in payload.get("fields", [])
        if field.get("requires_review")
    ]
    print(f"review_required_fields: {review_fields}")


if __name__ == "__main__":
    raise SystemExit(main())
