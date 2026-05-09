from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.core.schemas import (
    ConfidenceBand,
    ExtractedInvoiceFields,
    InvoiceLineItem,
    OCRConfidenceSummary,
    OCRExtractedField,
    OCRExtractedLineItem,
    OCRExtractionResult,
    OCRProviderMetadata,
    OCRProviderName,
)


REQUIRED_FIELDS = [
    "invoice_number",
    "supplier_name",
    "invoice_date",
    "currency",
    "grand_total",
]


class MockOCRProvider:
    def get_provider_name(self) -> str:
        return OCRProviderName.MOCK

    def is_configured(self) -> bool:
        return True

    def health_check(self) -> dict:
        return {"provider": OCRProviderName.MOCK, "configured": True, "status": "ok"}

    def extract_invoice(self, document_reference: dict, tenant_id: UUID) -> OCRExtractionResult:
        return self.normalize_provider_response(
            {
                "content": document_reference.get("content"),
                "mime_type": document_reference.get("mime_type"),
            },
            tenant_id,
        )

    def normalize_provider_response(self, raw_response: dict, tenant_id: UUID) -> OCRExtractionResult:
        content = raw_response.get("content")
        mime_type = raw_response.get("mime_type")
        if mime_type not in {"application/pdf", "image/png", "image/jpeg", "application/xml", "text/xml"}:
            fields: list[OCRExtractedField] = []
            return OCRExtractionResult(
                tenant_id=tenant_id,
                provider_metadata=OCRProviderMetadata(
                    provider_name=OCRProviderName.MOCK,
                    configured=True,
                    raw_provider_status="unsupported_mime_type",
                ),
                fields=fields,
                line_items=[],
                confidence_summary=self._summary(fields),
                raw_response={"mime_type": mime_type},
                error="unsupported invoice MIME type",
            )

        text = self._safe_text(content)
        default_confidence = float(self._read_token(text, "confidence") or 0.96)
        field_confidence = {
            "invoice_number": float(self._read_token(text, "confidence_invoice_number") or default_confidence),
            "supplier_name": float(self._read_token(text, "confidence_supplier_name") or default_confidence),
            "supplier_tax_id": float(self._read_token(text, "confidence_supplier_tax_id") or default_confidence),
            "invoice_date": float(self._read_token(text, "confidence_invoice_date") or default_confidence),
            "due_date": float(self._read_token(text, "confidence_due_date") or default_confidence),
            "currency": float(self._read_token(text, "confidence_currency") or default_confidence),
            "subtotal": float(self._read_token(text, "confidence_subtotal") or default_confidence),
            "tax_total": float(self._read_token(text, "confidence_tax_total") or default_confidence),
            "grand_total": float(self._read_token(text, "confidence_grand_total") or default_confidence),
            "po_number": float(self._read_token(text, "confidence_po_number") or default_confidence),
        }
        subtotal = float(self._read_token(text, "subtotal") or 1000)
        tax_total = float(self._read_token(text, "tax_total") or 170)
        grand_total = float(self._read_token(text, "grand_total") or subtotal + tax_total)
        invoice_date = self._read_token(text, "invoice_date") or date.today().isoformat()
        due_date = self._read_token(text, "due_date") or (date.today() + timedelta(days=30)).isoformat()

        values: dict[str, str | float | None] = {
            "invoice_number": self._read_token(text, "invoice_number") or "INV-MOCK-001",
            "supplier_name": self._read_token(text, "supplier_name") or "Northstar Components",
            "supplier_tax_id": self._read_token(text, "supplier_tax_id") or "TAX-12345",
            "invoice_date": invoice_date,
            "due_date": due_date,
            "currency": self._read_token(text, "currency") or "USD",
            "subtotal": subtotal,
            "tax_total": tax_total,
            "grand_total": grand_total,
            "po_number": self._read_token(text, "po_number") or "PO-100",
        }
        fields = [
            OCRExtractedField(
                field_name=field_name,
                value=value,
                confidence=field_confidence[field_name],
                raw_text=str(value) if value is not None else None,
                requires_review=field_confidence[field_name] < 0.75
                or (field_name in REQUIRED_FIELDS and value is None),
            )
            for field_name, value in values.items()
        ]
        line_item = OCRExtractedLineItem(
            fields=[
                OCRExtractedField(
                    field_name="description",
                    value="Mock extracted invoice line",
                    confidence=default_confidence,
                ),
                OCRExtractedField(field_name="quantity", value=1, confidence=default_confidence),
                OCRExtractedField(field_name="unit_price", value=subtotal, confidence=default_confidence),
                OCRExtractedField(field_name="tax_amount", value=tax_total, confidence=default_confidence),
                OCRExtractedField(field_name="total", value=grand_total, confidence=default_confidence),
            ],
            confidence=default_confidence,
            requires_review=default_confidence < 0.75,
        )
        return OCRExtractionResult(
            tenant_id=tenant_id,
            provider_metadata=OCRProviderMetadata(
                provider_name=OCRProviderName.MOCK,
                configured=True,
                model_version="mock-v2",
                raw_provider_status="ok",
            ),
            fields=fields,
            line_items=[line_item],
            confidence_summary=self._summary(fields),
            raw_response={"mime_type": mime_type, "provider": "mock"},
        )

    def extract(self, content: str | bytes | None, mime_type: str) -> dict[str, Any]:
        ocr = self.normalize_provider_response({"content": content, "mime_type": mime_type}, UUID(int=0))
        return self.to_legacy_result(ocr)

    def to_legacy_result(self, ocr: OCRExtractionResult) -> dict[str, Any]:
        field_map = {field.field_name: field.value for field in ocr.fields}
        confidence = {field.field_name: field.confidence for field in ocr.fields}
        confidence["document"] = ocr.confidence_summary.average_confidence
        return {
            "fields": ExtractedInvoiceFields(
                invoice_number=self._string(field_map.get("invoice_number")),
                supplier_name=self._string(field_map.get("supplier_name")),
                supplier_tax_id=self._string(field_map.get("supplier_tax_id")),
                invoice_date=self._string(field_map.get("invoice_date")),
                due_date=self._string(field_map.get("due_date")),
                currency=self._string(field_map.get("currency")),
                subtotal=self._float(field_map.get("subtotal")),
                tax_total=self._float(field_map.get("tax_total")),
                grand_total=self._float(field_map.get("grand_total")),
                po_number=self._string(field_map.get("po_number")),
            ),
            "line_items": [
                InvoiceLineItem(
                    description="Mock extracted invoice line",
                    quantity=1,
                    unit_price=self._float(field_map.get("subtotal")) or 0,
                    tax_amount=self._float(field_map.get("tax_total")) or 0,
                    total=self._float(field_map.get("grand_total")) or 0,
                    po_number=self._string(field_map.get("po_number")),
                )
            ],
            "confidence": confidence,
            "ocr_result": ocr,
        }

    def _summary(self, fields: list[OCRExtractedField]) -> OCRConfidenceSummary:
        if not fields:
            return OCRConfidenceSummary(
                average_confidence=0,
                required_fields_missing=REQUIRED_FIELDS,
                required_fields_low_confidence=[],
            )
        missing = [
            field_name
            for field_name in REQUIRED_FIELDS
            if not any(field.field_name == field_name and field.value not in (None, "") for field in fields)
        ]
        low_required = [
            field.field_name
            for field in fields
            if field.field_name in REQUIRED_FIELDS and field.confidence < 0.75
        ]
        return OCRConfidenceSummary(
            average_confidence=round(sum(field.confidence for field in fields) / len(fields), 4),
            high_confidence_fields=sum(1 for field in fields if self._band(field.confidence) == ConfidenceBand.HIGH),
            medium_confidence_fields=sum(
                1 for field in fields if self._band(field.confidence) == ConfidenceBand.MEDIUM
            ),
            low_confidence_fields=sum(1 for field in fields if self._band(field.confidence) == ConfidenceBand.LOW),
            required_fields_missing=missing,
            required_fields_low_confidence=low_required,
        )

    def _band(self, confidence: float) -> ConfidenceBand:
        if confidence >= 0.9:
            return ConfidenceBand.HIGH
        if confidence >= 0.75:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW

    def _read_token(self, text: str, key: str) -> str | None:
        prefix = f"{key}="
        for token in text.replace("\n", " ").split():
            if token.startswith(prefix):
                return token.removeprefix(prefix).strip()
        return None

    def _safe_text(self, content: str | bytes | None) -> str:
        if content is None:
            return ""
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="ignore")
        return str(content)

    def _string(self, value: str | float | int | None) -> str | None:
        return str(value) if value is not None else None

    def _float(self, value: str | float | int | None) -> float | None:
        return float(value) if value is not None else None
