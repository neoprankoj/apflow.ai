from datetime import date, datetime
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


class SafePlaceholderOCRAdapter:
    provider_name: OCRProviderName

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_provider_name(self) -> str:
        return self.provider_name

    def is_configured(self) -> bool:
        return False

    def health_check(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": self.is_configured(),
            "status": "missing_credentials" if not self.is_configured() else "ok",
        }

    def extract_invoice(self, document_reference: dict, tenant_id: UUID) -> OCRExtractionResult:
        return self.normalize_provider_response(
            {"error": f"{self.provider_name} OCR adapter is not configured"},
            tenant_id,
        )

    def normalize_provider_response(self, raw_response: dict, tenant_id: UUID) -> OCRExtractionResult:
        return OCRExtractionResult(
            tenant_id=tenant_id,
            provider_metadata=OCRProviderMetadata(
                provider_name=self.provider_name,
                configured=self.is_configured(),
                raw_provider_status="missing_credentials" if not self.is_configured() else "placeholder",
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
            error=raw_response.get("error", "provider placeholder did not extract a document"),
        )


class AzureDocumentIntelligenceOCRAdapter(SafePlaceholderOCRAdapter):
    provider_name = OCRProviderName.AZURE

    def is_configured(self) -> bool:
        return bool(
            self.settings.azure_document_intelligence_endpoint
            and self.settings.azure_document_intelligence_key
        )

    def health_check(self) -> dict:
        configured = self.is_configured()
        return {
            "provider": self.provider_name,
            "configured": configured,
            "status": "ok" if configured else "missing_credentials",
            "model_id": "prebuilt-invoice",
        }

    def extract_invoice(self, document_reference: dict, tenant_id: UUID) -> OCRExtractionResult:
        if not self.is_configured():
            return self.normalize_provider_response(
                {"error": "Azure Document Intelligence endpoint/key are not configured"},
                tenant_id,
            )
        content = document_reference.get("content")
        if content is None:
            return self.normalize_provider_response(
                {"error": "Azure OCR requires invoice bytes in the current runtime"},
                tenant_id,
            )
        body = content if isinstance(content, bytes) else str(content).encode("utf-8")
        try:
            client = self._client()
            poller = client.begin_analyze_document(
                "prebuilt-invoice",
                body=body,
                content_type=document_reference.get("mime_type") or "application/octet-stream",
            )
            result = poller.result()
            return self.normalize_provider_response(result, tenant_id)
        except Exception as exc:
            return self.normalize_provider_response(
                {"error": f"Azure Document Intelligence extraction failed: {exc.__class__.__name__}"},
                tenant_id,
            )

    def normalize_provider_response(self, raw_response, tenant_id: UUID) -> OCRExtractionResult:
        if isinstance(raw_response, dict) and raw_response.get("error"):
            return super().normalize_provider_response(raw_response, tenant_id)

        document = self._first_document(raw_response)
        fields_by_name = getattr(document, "fields", {}) if document is not None else {}
        fields = [
            self._field("invoice_number", fields_by_name, "InvoiceId", "InvoiceID", "InvoiceNumber", "InvoiceNo"),
            self._field("supplier_name", fields_by_name, "VendorName", "SupplierName", "MerchantName"),
            self._field("supplier_tax_id", fields_by_name, "VendorTaxId", "VendorTaxID", "TaxId", "TaxID"),
            self._field("invoice_date", fields_by_name, "InvoiceDate"),
            self._field("due_date", fields_by_name, "DueDate", "PaymentDueDate"),
            self._currency_field(fields_by_name),
            self._field("subtotal", fields_by_name, "SubTotal", "Subtotal"),
            self._field("tax_total", fields_by_name, "TotalTax", "Tax", "TotalTaxAmount"),
            self._field("grand_total", fields_by_name, "InvoiceTotal", "AmountDue", "Total"),
            self._field("po_number", fields_by_name, "PurchaseOrder", "PurchaseOrderNumber", "PONumber"),
        ]
        line_items = self._line_items(fields_by_name)
        return OCRExtractionResult(
            tenant_id=tenant_id,
            provider_metadata=OCRProviderMetadata(
                provider_name=OCRProviderName.AZURE,
                configured=self.is_configured(),
                model_version="prebuilt-invoice",
                raw_provider_status="ok",
            ),
            fields=fields,
            line_items=line_items,
            confidence_summary=self._summary(fields),
            raw_response={"provider": "azure", "document_count": len(getattr(raw_response, "documents", []) or [])},
        )

    def _client(self):
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise RuntimeError("azure-ai-documentintelligence is not installed") from exc
        return DocumentIntelligenceClient(
            endpoint=self.settings.azure_document_intelligence_endpoint,
            credential=AzureKeyCredential(self.settings.azure_document_intelligence_key),
        )

    def _first_document(self, raw_response):
        documents = getattr(raw_response, "documents", None) or []
        return documents[0] if documents else None

    def _field(self, field_name: str, fields_by_name: dict, *azure_names: str) -> OCRExtractedField:
        raw = self._first_field(fields_by_name, *azure_names)
        value = self._field_value(raw)
        confidence = self._confidence(raw)
        return OCRExtractedField(
            field_name=field_name,
            value=value,
            confidence=confidence,
            source_page=self._source_page(raw),
            bounding_box=self._bounding_box(raw),
            raw_text=str(value) if value is not None else None,
            requires_review=confidence < 0.75 or (field_name in self._required_fields() and value in (None, "")),
        )

    def _currency_field(self, fields_by_name: dict) -> OCRExtractedField:
        raw = self._first_field(fields_by_name, "Currency")
        value = self._field_value(raw)
        if value in (None, ""):
            total = self._first_field(fields_by_name, "InvoiceTotal", "AmountDue", "Total")
            value = self._currency_code(total)
            raw = total if value else raw
        confidence = self._confidence(raw)
        return OCRExtractedField(
            field_name="currency",
            value=value,
            confidence=confidence,
            source_page=self._source_page(raw),
            bounding_box=self._bounding_box(raw),
            raw_text=str(value) if value is not None else None,
            requires_review=confidence < 0.75 or value in (None, ""),
        )

    def _line_items(self, fields_by_name: dict) -> list[OCRExtractedLineItem]:
        items_field = fields_by_name.get("Items")
        values = self._field_value(items_field) or []
        line_items: list[OCRExtractedLineItem] = []
        for item in values:
            properties = self._field_value(item) or getattr(item, "properties", {}) or {}
            if not isinstance(properties, dict):
                properties = {}
            item_fields = [
                self._line_field("description", properties, "Description", "ProductCode"),
                self._line_field("quantity", properties, "Quantity"),
                self._line_field("unit_price", properties, "UnitPrice", "UnitCost"),
                self._line_field("tax_amount", properties, "Tax", "TaxAmount"),
                self._line_field("total", properties, "Amount", "TotalPrice"),
            ]
            average = round(sum(field.confidence for field in item_fields) / len(item_fields), 4)
            line_items.append(
                OCRExtractedLineItem(
                    fields=item_fields,
                    confidence=average,
                    requires_review=average < 0.75,
                )
            )
        return line_items

    def _line_field(self, field_name: str, properties: dict, *azure_names: str) -> OCRExtractedField:
        raw = self._first_field(properties, *azure_names)
        value = self._field_value(raw)
        confidence = self._confidence(raw)
        return OCRExtractedField(
            field_name=field_name,
            value=value,
            confidence=confidence,
            source_page=self._source_page(raw),
            bounding_box=self._bounding_box(raw),
            raw_text=str(value) if value is not None else None,
            requires_review=confidence < 0.75,
        )

    def _first_field(self, fields: dict, *names: str):
        for name in names:
            raw = fields.get(name)
            if raw is not None and self._field_value(raw) not in (None, ""):
                return raw
        for name in names:
            raw = fields.get(name)
            if raw is not None:
                return raw
        return None

    def _field_value(self, field):
        if field is None:
            return None
        for attr in (
            "value",
            "value_string",
            "value_date",
            "value_number",
            "value_currency",
            "value_array",
            "value_object",
        ):
            if hasattr(field, attr):
                value = getattr(field, attr)
                if value is not None:
                    return self._normalize_value(value)
        if isinstance(field, dict):
            for key in (
                "value",
                "content",
                "valueString",
                "valueDate",
                "valueNumber",
                "valueCurrency",
                "valueArray",
                "valueObject",
            ):
                if key in field and field[key] is not None:
                    return self._normalize_value(field[key])
        return getattr(field, "content", None)

    def _normalize_value(self, value):
        if hasattr(value, "amount"):
            return float(value.amount)
        if isinstance(value, dict) and "amount" in value:
            return float(value["amount"])
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return value
        return value.isoformat() if isinstance(value, (date, datetime)) else value

    def _currency_code(self, field):
        if field is None:
            return None
        for attr in ("value_currency", "value"):
            currency = getattr(field, attr, None)
            code = self._currency_code_from_value(currency)
            if code:
                return code
        if isinstance(field, dict):
            for key in ("valueCurrency", "value"):
                code = self._currency_code_from_value(field.get(key))
                if code:
                    return code
        return None

    def _currency_code_from_value(self, value):
        if value is None:
            return None
        for attr in ("currency_code", "currencyCode", "code", "currency_symbol"):
            code = getattr(value, attr, None)
            if code:
                return str(code)
        if isinstance(value, dict):
            for key in ("currencyCode", "currency_code", "code", "currencySymbol", "currency_symbol"):
                if value.get(key):
                    return str(value[key])
        return None

    def _confidence(self, field) -> float:
        if field is None:
            return 0
        if isinstance(field, dict):
            return self._bounded_confidence(field.get("confidence"))
        return self._bounded_confidence(getattr(field, "confidence", 0))

    def _bounded_confidence(self, value) -> float:
        try:
            confidence = float(value if value is not None else 0)
        except (TypeError, ValueError):
            return 0
        return max(0, min(1, confidence))

    def _source_page(self, field) -> int | None:
        regions = getattr(field, "bounding_regions", None) or []
        if isinstance(field, dict):
            regions = field.get("boundingRegions") or field.get("bounding_regions") or []
        if not regions:
            return None
        page_number = getattr(regions[0], "page_number", None)
        if page_number is None and isinstance(regions[0], dict):
            page_number = regions[0].get("pageNumber") or regions[0].get("page_number")
        return int(page_number) if page_number is not None else None

    def _bounding_box(self, field) -> list[float] | None:
        regions = getattr(field, "bounding_regions", None) or []
        if isinstance(field, dict):
            regions = field.get("boundingRegions") or field.get("bounding_regions") or []
        if not regions:
            return None
        polygon = getattr(regions[0], "polygon", None)
        if polygon is None and isinstance(regions[0], dict):
            polygon = regions[0].get("polygon")
        if not polygon:
            return None
        box: list[float] = []
        for point in polygon:
            if isinstance(point, dict):
                if "x" in point and "y" in point:
                    box.extend([float(point["x"]), float(point["y"])])
            elif hasattr(point, "x") and hasattr(point, "y"):
                box.extend([float(point.x), float(point.y)])
            else:
                try:
                    box.append(float(point))
                except (TypeError, ValueError):
                    continue
        return box or None

    def _summary(self, fields: list[OCRExtractedField]) -> OCRConfidenceSummary:
        required = self._required_fields()
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

    def _required_fields(self) -> list[str]:
        return ["invoice_number", "supplier_name", "invoice_date", "currency", "grand_total"]


class GoogleDocumentAIOCRAdapter(SafePlaceholderOCRAdapter):
    provider_name = OCRProviderName.GOOGLE

    def is_configured(self) -> bool:
        return bool(
            self.settings.google_document_ai_project_id
            and self.settings.google_document_ai_location
            and self.settings.google_document_ai_processor_id
        )


class AWSTextractOCRAdapter(SafePlaceholderOCRAdapter):
    provider_name = OCRProviderName.AWS

    def is_configured(self) -> bool:
        return bool(
            self.settings.aws_region
            and self.settings.aws_access_key_id
            and self.settings.aws_secret_access_key
        )
