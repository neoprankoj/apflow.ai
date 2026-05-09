from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from uuid import UUID

from app.core.config import Settings
from app.core.schemas import (
    ConfidenceBand,
    OCRConfidenceSummary,
    OCRExtractedField,
    OCRExtractedLineItem,
    OCRExtractionResult,
    OCRProviderMetadata,
    OCRProviderName,
)


class OCRSpaceOCRAdapter:
    provider_name = OCRProviderName.OCR_SPACE

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_provider_name(self) -> str:
        return self.provider_name

    def is_configured(self) -> bool:
        return bool(self.settings.ocr_space_api_key and self.settings.ocr_space_api_url)

    def health_check(self) -> dict:
        configured = self.is_configured()
        return {
            "provider": self.provider_name,
            "configured": configured,
            "status": "ok" if configured else "missing_credentials",
            "api_url_configured": bool(self.settings.ocr_space_api_url),
            "language": self.settings.ocr_space_language or "eng",
            "engine": str(self.settings.ocr_space_engine or "2"),
        }

    def extract_invoice(self, document_reference: dict, tenant_id: UUID) -> OCRExtractionResult:
        if not self.is_configured():
            return self.normalize_provider_response(
                {"error": "OCR.space API key is not configured"},
                tenant_id,
            )
        content = document_reference.get("content")
        if content is None:
            return self.normalize_provider_response(
                {"error": "OCR.space OCR requires invoice bytes in the current runtime"},
                tenant_id,
            )
        body = content if isinstance(content, bytes) else str(content).encode("utf-8")
        try:
            raw_response = self._post_to_ocr_space(
                file_name=str(document_reference.get("file_name") or "invoice"),
                content=body,
                content_type=str(document_reference.get("mime_type") or "application/octet-stream"),
            )
            return self.normalize_provider_response(raw_response, tenant_id)
        except Exception as exc:
            return self.normalize_provider_response(
                {"error": f"OCR.space extraction failed: {exc.__class__.__name__}"},
                tenant_id,
            )

    def normalize_provider_response(self, raw_response: dict, tenant_id: UUID) -> OCRExtractionResult:
        if raw_response.get("error"):
            return self._error_result(str(raw_response["error"]), tenant_id)
        if raw_response.get("IsErroredOnProcessing"):
            message = self._provider_error_message(raw_response)
            return self._error_result(message, tenant_id, raw_provider_status="provider_error")

        parsed_text = self._parsed_text(raw_response)
        fields = self._fields_from_text(parsed_text)
        line_items = self._line_items_from_fields(fields)
        return OCRExtractionResult(
            tenant_id=tenant_id,
            provider_metadata=OCRProviderMetadata(
                provider_name=OCRProviderName.OCR_SPACE,
                configured=self.is_configured(),
                model_version=f"engine-{self.settings.ocr_space_engine or '2'}",
                raw_provider_status="ok",
            ),
            fields=fields,
            line_items=line_items,
            confidence_summary=self._summary(fields),
            raw_response={
                "provider": "ocr_space",
                "parsed_result_count": len(raw_response.get("ParsedResults") or []),
                "text_sample": parsed_text[:1000],
            },
        )

    def _post_to_ocr_space(self, file_name: str, content: bytes, content_type: str) -> dict:
        boundary = "----apflow-ocr-space-boundary"
        data_fields = {
            "language": self.settings.ocr_space_language or "eng",
            "isOverlayRequired": "false",
            "OCREngine": str(self.settings.ocr_space_engine or "2"),
            "scale": "true",
            "detectOrientation": "true",
        }
        chunks: list[bytes] = []
        for name, value in data_fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    str(value).encode(),
                    b"\r\n",
                ]
            )
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ]
        )
        request = urllib.request.Request(
            self.settings.ocr_space_api_url,
            data=b"".join(chunks),
            method="POST",
            headers={
                "apikey": self.settings.ocr_space_api_key,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.ocr_space_timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OCR.space HTTP {exc.code}") from exc

    def _fields_from_text(self, text: str) -> list[OCRExtractedField]:
        return [
            self._field("invoice_number", text, self._find(text, [
                r"\b(?:invoice\s*(?:number|no\.?|#)|inv(?:oice)?\s*#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9\-\/]+)",
            ]), required=True),
            self._field("supplier_name", text, self._find(text, [
                r"(?im)^\s*(?:vendor|supplier|from)\s*[:#-]\s*(.+?)\s*$",
            ]), required=True),
            self._field("supplier_tax_id", text, self._find(text, [
                r"\b(?:vendor\s*)?(?:tax\s*id|vat\s*id|tin)\s*[:#-]?\s*([A-Z0-9\-]+)",
            ])),
            self._field("invoice_date", text, self._find(text, [
                r"\b(?:invoice\s*)?date\s*[:#-]?\s*(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4})",
            ]), required=True),
            self._field("due_date", text, self._find(text, [
                r"\bdue\s*date\s*[:#-]?\s*(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4})",
            ])),
            self._field("currency", text, self._currency(text), required=True),
            self._field("subtotal", text, self._money(text, [r"\bsubtotal\s*[:#-]?\s*([A-Z]{3}?\s*[$]?\s*[\d,]+(?:\.\d{2})?|\s*[$]?\s*[\d,]+(?:\.\d{2})?)"])),
            self._field("tax_total", text, self._money(text, [r"\b(?:tax|vat)\s*[:#-]?\s*([A-Z]{3}?\s*[$]?\s*[\d,]+(?:\.\d{2})?|\s*[$]?\s*[\d,]+(?:\.\d{2})?)"])),
            self._field("grand_total", text, self._money(text, [
                r"\b(?:grand\s*)?total\s*[:#-]?\s*([A-Z]{3}?\s*[$]?\s*[\d,]+(?:\.\d{2})?|\s*[$]?\s*[\d,]+(?:\.\d{2})?)",
                r"\bamount\s*due\s*[:#-]?\s*([A-Z]{3}?\s*[$]?\s*[\d,]+(?:\.\d{2})?|\s*[$]?\s*[\d,]+(?:\.\d{2})?)",
            ]), required=True),
            self._field("po_number", text, self._find(text, [
                r"\b(?:purchase\s*order|po)\s*(?:number|no\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9\-\/]+)",
            ])),
        ]

    def _field(
        self,
        field_name: str,
        text: str,
        match: tuple[str | float | None, str | None, float] | None,
        required: bool = False,
    ) -> OCRExtractedField:
        value, raw_text, confidence = match if match is not None else (None, None, 0)
        return OCRExtractedField(
            field_name=field_name,
            value=value,
            confidence=confidence,
            raw_text=raw_text,
            requires_review=confidence < 0.75 or (required and value in (None, "")),
        )

    def _find(self, text: str, patterns: list[str]) -> tuple[str | None, str | None, float] | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip().strip(" .,:;")
                return value, match.group(0).strip(), 0.86
        return None

    def _money(self, text: str, patterns: list[str]) -> tuple[float | None, str | None, float] | None:
        found = self._find(text, patterns)
        if found is None or found[0] is None:
            return None
        value = self._parse_amount(found[0])
        return value, found[1], 0.84 if value is not None else 0

    def _parse_amount(self, value: str) -> float | None:
        cleaned = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _currency(self, text: str) -> tuple[str | None, str | None, float] | None:
        explicit = self._find(text, [r"\bcurrency\s*[:#-]?\s*([A-Z]{3})\b"])
        if explicit:
            return explicit[0], explicit[1], 0.88
        symbols = {"$": "USD"}
        for symbol, code in symbols.items():
            if symbol in text:
                return code, symbol, 0.76
        code_match = re.search(r"\b(USD|EUR|GBP|ILS|NIS|CAD|AUD)\b", text, flags=re.IGNORECASE)
        if code_match:
            return code_match.group(1).upper(), code_match.group(0), 0.8
        return None

    def _line_items_from_fields(self, fields: list[OCRExtractedField]) -> list[OCRExtractedLineItem]:
        field_map = {field.field_name: field for field in fields}
        subtotal = field_map["subtotal"].value
        tax_total = field_map["tax_total"].value
        grand_total = field_map["grand_total"].value
        if subtotal is None and tax_total is None and grand_total is None:
            return []
        item_fields = [
            OCRExtractedField(field_name="description", value="OCR.space extracted invoice line", confidence=0.7, requires_review=True),
            OCRExtractedField(field_name="quantity", value=1, confidence=0.7, requires_review=True),
            OCRExtractedField(field_name="unit_price", value=subtotal, confidence=field_map["subtotal"].confidence),
            OCRExtractedField(field_name="tax_amount", value=tax_total, confidence=field_map["tax_total"].confidence),
            OCRExtractedField(field_name="total", value=grand_total, confidence=field_map["grand_total"].confidence),
        ]
        average = round(sum(field.confidence for field in item_fields) / len(item_fields), 4)
        return [OCRExtractedLineItem(fields=item_fields, confidence=average, requires_review=average < 0.75)]

    def _parsed_text(self, raw_response: dict) -> str:
        results = raw_response.get("ParsedResults") or []
        texts = [str(result.get("ParsedText") or "") for result in results if isinstance(result, dict)]
        return "\n".join(text for text in texts if text)

    def _provider_error_message(self, raw_response: dict) -> str:
        message = raw_response.get("ErrorMessage") or raw_response.get("ErrorDetails")
        if isinstance(message, list):
            return "; ".join(str(item) for item in message if item)
        if message:
            return str(message)
        return "OCR.space returned an OCR processing error"

    def _error_result(
        self,
        message: str,
        tenant_id: UUID,
        raw_provider_status: str = "missing_credentials",
    ) -> OCRExtractionResult:
        return OCRExtractionResult(
            tenant_id=tenant_id,
            provider_metadata=OCRProviderMetadata(
                provider_name=OCRProviderName.OCR_SPACE,
                configured=self.is_configured(),
                raw_provider_status=raw_provider_status,
            ),
            fields=[],
            line_items=[],
            confidence_summary=OCRConfidenceSummary(
                average_confidence=0,
                required_fields_missing=[
                    "invoice_number",
                    "supplier_name",
                    "invoice_date",
                    "currency",
                    "grand_total",
                ],
            ),
            raw_response={},
            error=message,
        )

    def _summary(self, fields: list[OCRExtractedField]) -> OCRConfidenceSummary:
        required = ["invoice_number", "supplier_name", "invoice_date", "currency", "grand_total"]
        missing = [
            field_name
            for field_name in required
            if not any(field.field_name == field_name and field.value not in (None, "") for field in fields)
        ]
        low_required = [
            field.field_name
            for field in fields
            if field.field_name in required and field.confidence < 0.75
        ]
        average = round(sum(field.confidence for field in fields) / len(fields), 4) if fields else 0
        return OCRConfidenceSummary(
            average_confidence=average,
            high_confidence_fields=sum(1 for field in fields if self._band(field.confidence) == ConfidenceBand.HIGH),
            medium_confidence_fields=sum(1 for field in fields if self._band(field.confidence) == ConfidenceBand.MEDIUM),
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
