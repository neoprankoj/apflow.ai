"""Run a live OCR.space invoice OCR check.

Usage:
    python scripts/test_ocr_space.py samples/invoices/invoice.pdf
    python scripts/test_ocr_space.py samples/invoices/invoice.pdf --out samples/ocr-results/ocr-space.json
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.integrations.ocr.ocr_space import OCRSpaceOCRAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live OCR.space OCR against a local invoice PDF/image")
    parser.add_argument("file", help="Local PDF/image path. Do not use sensitive real invoices.")
    parser.add_argument("--out", help="Optional JSON output path, usually under samples/ocr-results/")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")

    settings = Settings(
        ocr_provider="ocr_space",
        ocr_space_api_key=os.getenv("OCR_SPACE_API_KEY", ""),
        ocr_space_api_url=os.getenv("OCR_SPACE_API_URL", "https://api.ocr.space/parse/image"),
        ocr_space_language=os.getenv("OCR_SPACE_LANGUAGE", "eng"),
        ocr_space_engine=os.getenv("OCR_SPACE_ENGINE", "2"),
        ocr_space_timeout_seconds=int(os.getenv("OCR_SPACE_TIMEOUT_SECONDS", "60")),
    )
    adapter = OCRSpaceOCRAdapter(settings)
    if not adapter.is_configured():
        raise SystemExit("OCR.space is not configured. Set OCR_SPACE_API_KEY before running.")

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    result = adapter.extract_invoice(
        {
            "file_name": file_path.name,
            "mime_type": content_type,
            "content": file_path.read_bytes(),
        },
        tenant_id=uuid4(),
    )

    print("OCR.space extraction")
    print(f"provider_status={result.provider_metadata.raw_provider_status}")
    print(f"average_confidence={result.confidence_summary.average_confidence}")
    print(f"required_missing={','.join(result.confidence_summary.required_fields_missing) or 'none'}")
    print(f"error={result.error or 'none'}")
    for field in result.fields:
        review = " review_required" if field.requires_review else ""
        print(f"{field.field_name}: {field.value} confidence={field.confidence}{review}")
    for index, item in enumerate(result.line_items, start=1):
        print(f"line_item_{index}: confidence={item.confidence} review={item.requires_review}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(f"wrote={out_path}")

    return 0 if result.error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
