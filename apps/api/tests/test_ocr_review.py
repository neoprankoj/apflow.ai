from uuid import uuid4

from app.core.config import Settings
from app.core.schemas import (
    HumanReviewCorrectionRequest,
    HumanReviewStatus,
    OCRProviderName,
)
from app.integrations.ocr.cloud import (
    AWSTextractOCRAdapter,
    AzureDocumentIntelligenceOCRAdapter,
    GoogleDocumentAIOCRAdapter,
)
from app.integrations.ocr.factory import OCRProviderFactory
from app.integrations.ocr.mock import MockOCRProvider
from app.integrations.ocr.ocr_space import OCRSpaceOCRAdapter


def test_mock_ocr_returns_field_level_confidence(tenant_id):
    result = MockOCRProvider().extract_invoice(
        {
            "mime_type": "application/pdf",
            "content": (
                "invoice_number=INV-OCR-1 supplier_name=Northstar Components "
                "subtotal=1000 tax_total=170 grand_total=1170 currency=USD"
            ),
        },
        tenant_id,
    )

    assert result.provider_metadata.provider_name == OCRProviderName.MOCK
    assert result.confidence_summary.high_confidence_fields >= 1
    assert all(field.confidence >= 0 for field in result.fields)


def test_ocr_provider_factory_selects_provider():
    factory = OCRProviderFactory(Settings(ocr_provider="mock"))

    provider = factory.get_provider()

    assert provider.get_provider_name() == OCRProviderName.MOCK
    assert {"mock", "azure", "google", "aws", "ocr_space"}.issubset(set(factory.available_providers()))


def test_ocr_provider_factory_selects_azure_when_configured_provider():
    factory = OCRProviderFactory(
        Settings(
            ocr_provider="azure",
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    )

    provider = factory.get_provider()

    assert provider.get_provider_name() == OCRProviderName.AZURE
    assert provider.is_configured() is True


def test_ocr_provider_factory_selects_ocr_space_when_configured_provider():
    factory = OCRProviderFactory(Settings(ocr_provider="ocr_space", ocr_space_api_key="test-key"))

    provider = factory.get_provider()

    assert provider.get_provider_name() == OCRProviderName.OCR_SPACE
    assert provider.is_configured() is True


def test_mock_ocr_handles_binary_pdf_and_invalid_utf8(tenant_id):
    provider = MockOCRProvider()

    for content in (b"%PDF-1.7\xff\xfe\x00binary", b"\xff\xfe\xfa", b""):
        result = provider.extract_invoice({"mime_type": "application/pdf", "content": content}, tenant_id)

        field_map = {field.field_name: field.value for field in result.fields}
        assert result.error is None
        assert field_map["invoice_number"] == "INV-MOCK-001"
        assert result.confidence_summary.average_confidence > 0.9


def test_cloud_ocr_adapters_fail_safely_without_credentials(tenant_id):
    adapters = [
        AzureDocumentIntelligenceOCRAdapter(Settings()),
        GoogleDocumentAIOCRAdapter(Settings()),
        AWSTextractOCRAdapter(Settings()),
    ]

    for adapter in adapters:
        result = adapter.extract_invoice({"mime_type": "application/pdf", "content": "x"}, tenant_id)
        assert adapter.is_configured() is False
        assert result.error
        assert result.confidence_summary.required_fields_missing


def test_ocr_space_adapter_reports_missing_credentials(tenant_id):
    adapter = OCRSpaceOCRAdapter(Settings())

    health = adapter.health_check()
    result = adapter.extract_invoice({"mime_type": "application/pdf", "content": b"pdf"}, tenant_id)

    assert health["provider"] == OCRProviderName.OCR_SPACE
    assert health["configured"] is False
    assert health["status"] == "missing_credentials"
    assert result.error == "OCR.space API key is not configured"


def test_ocr_space_maps_parsed_text_to_extraction_result(tenant_id):
    adapter = OCRSpaceOCRAdapter(Settings(ocr_space_api_key="test-key"))

    result = adapter.normalize_provider_response(
        {
            "IsErroredOnProcessing": False,
            "ParsedResults": [
                {
                    "ParsedText": (
                        "Vendor: Northstar Components\n"
                        "Invoice Number: INV-SPACE-1\n"
                        "Invoice Date: 2026-05-05\n"
                        "Due Date: 2026-06-04\n"
                        "Currency: USD\n"
                        "Subtotal: 1000.00\n"
                        "Tax: 170.00\n"
                        "Total: 1170.00\n"
                        "PO Number: PO-100\n"
                    )
                }
            ],
        },
        tenant_id,
    )
    field_map = {field.field_name: field for field in result.fields}

    assert result.provider_metadata.provider_name == OCRProviderName.OCR_SPACE
    assert field_map["invoice_number"].value == "INV-SPACE-1"
    assert field_map["supplier_name"].value == "Northstar Components"
    assert field_map["grand_total"].value == 1170.0
    assert field_map["po_number"].value == "PO-100"
    assert result.confidence_summary.required_fields_missing == []
    assert result.confidence_summary.average_confidence >= 0.75


def test_ocr_space_provider_error_is_safe(tenant_id):
    adapter = OCRSpaceOCRAdapter(Settings(ocr_space_api_key="test-key"))

    result = adapter.normalize_provider_response(
        {
            "IsErroredOnProcessing": True,
            "ErrorMessage": ["Unable to recognize the file"],
        },
        tenant_id,
    )

    assert result.error == "Unable to recognize the file"
    assert result.provider_metadata.raw_provider_status == "provider_error"
    assert result.confidence_summary.required_fields_missing


def test_ocr_space_extract_uses_multipart_without_logging_key(tenant_id, caplog, monkeypatch):
    adapter = OCRSpaceOCRAdapter(Settings(ocr_space_api_key="secret-test-key"))

    def fake_post(file_name: str, content: bytes, content_type: str) -> dict:
        assert file_name == "invoice.pdf"
        assert content == b"pdf-bytes"
        assert content_type == "application/pdf"
        return {
            "IsErroredOnProcessing": False,
            "ParsedResults": [{"ParsedText": "Invoice Number: INV-SPACE-2\nTotal: 10.00"}],
        }

    monkeypatch.setattr(adapter, "_post_to_ocr_space", fake_post)

    result = adapter.extract_invoice(
        {"file_name": "invoice.pdf", "mime_type": "application/pdf", "content": b"pdf-bytes"},
        tenant_id,
    )

    assert result.error is None
    assert "secret-test-key" not in caplog.text


def test_azure_adapter_health_check_reports_missing_credentials():
    adapter = AzureDocumentIntelligenceOCRAdapter(Settings())

    health = adapter.health_check()

    assert health["provider"] == OCRProviderName.AZURE
    assert health["configured"] is False
    assert health["status"] == "missing_credentials"


def test_azure_provider_status_reports_configured_and_unconfigured():
    unconfigured = OCRProviderFactory(Settings(ocr_provider="azure")).provider_statuses()
    configured = OCRProviderFactory(
        Settings(
            ocr_provider="azure",
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    ).provider_statuses()

    azure_unconfigured = next(item for item in unconfigured if item["provider"] == "azure")
    azure_configured = next(item for item in configured if item["provider"] == "azure")

    assert azure_unconfigured["configured"] is False
    assert azure_unconfigured["status"] == "missing_credentials"
    assert azure_configured["configured"] is True
    assert azure_configured["selected"] is True


def test_azure_response_mapping_includes_fields_confidence_and_line_items(tenant_id):
    adapter = AzureDocumentIntelligenceOCRAdapter(
        Settings(
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    )

    result = adapter.normalize_provider_response(_azure_result(), tenant_id)
    field_map = {field.field_name: field for field in result.fields}

    assert result.provider_metadata.provider_name == OCRProviderName.AZURE
    assert field_map["invoice_number"].value == "INV-AZ-1"
    assert field_map["invoice_number"].confidence == 0.99
    assert field_map["grand_total"].value == 1170.0
    assert result.line_items[0].confidence > 0.9
    assert result.confidence_summary.average_confidence > 0.9


def test_azure_mapping_handles_alternative_names_missing_optional_fields_and_null_confidence(tenant_id):
    adapter = AzureDocumentIntelligenceOCRAdapter(
        Settings(
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    )

    result = adapter.normalize_provider_response(_azure_result_with_alternative_names(), tenant_id)
    field_map = {field.field_name: field for field in result.fields}

    assert field_map["invoice_number"].value == "INV-ALT-1"
    assert field_map["supplier_name"].value == "Alternative Vendor"
    assert field_map["currency"].value == "USD"
    assert field_map["grand_total"].value == 222.5
    assert field_map["due_date"].value is None
    assert field_map["due_date"].confidence == 0
    assert field_map["due_date"].requires_review is True
    assert field_map["po_number"].value == "PO-ALT-1"
    assert result.confidence_summary.required_fields_missing == []


def test_azure_line_item_mapping_supports_dict_response_shapes(tenant_id):
    adapter = AzureDocumentIntelligenceOCRAdapter(
        Settings(
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    )

    result = adapter.normalize_provider_response(_azure_result_with_dict_line_items(), tenant_id)
    first = {field.field_name: field for field in result.line_items[0].fields}

    assert first["description"].value == "Widget"
    assert first["quantity"].value == 2
    assert first["unit_price"].value == 50
    assert first["tax_amount"].value == 10
    assert first["total"].value == 110


def test_azure_low_confidence_fields_route_to_human_review(tenant_id, human_review_agent, repository):
    adapter = AzureDocumentIntelligenceOCRAdapter(
        Settings(
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    )
    result = adapter.normalize_provider_response(
        _azure_result(invoice_number_confidence=0.41),
        tenant_id,
    )

    task = human_review_agent.inspect_extraction(result, raw_invoice_id=uuid4())

    assert task.status == HumanReviewStatus.REVIEW_REQUIRED
    assert task.issues[0].field_name == "invoice_number"
    assert repository.list_review_tasks(tenant_id)


def test_azure_adapter_extract_uses_mocked_client_response(tenant_id, monkeypatch):
    adapter = AzureDocumentIntelligenceOCRAdapter(
        Settings(
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    )

    class Poller:
        def result(self):
            return _azure_result()

    class Client:
        def begin_analyze_document(self, model_id, body, content_type):
            assert model_id == "prebuilt-invoice"
            assert body == b"pdf-bytes"
            assert content_type == "application/pdf"
            return Poller()

    monkeypatch.setattr(adapter, "_client", lambda: Client())

    result = adapter.extract_invoice({"content": b"pdf-bytes", "mime_type": "application/pdf"}, tenant_id)

    assert result.error is None
    assert {field.field_name: field.value for field in result.fields}["invoice_number"] == "INV-AZ-1"


def test_azure_adapter_extract_routes_provider_errors_safely(tenant_id, monkeypatch):
    adapter = AzureDocumentIntelligenceOCRAdapter(
        Settings(
            azure_document_intelligence_endpoint="https://example.cognitiveservices.azure.com/",
            azure_document_intelligence_key="test-key",
        )
    )

    class Client:
        def begin_analyze_document(self, model_id, body, content_type):
            raise TimeoutError("network timed out")

    monkeypatch.setattr(adapter, "_client", lambda: Client())

    result = adapter.extract_invoice({"content": b"pdf-bytes", "mime_type": "application/pdf"}, tenant_id)

    assert result.error == "Azure Document Intelligence extraction failed: TimeoutError"
    assert result.provider_metadata.raw_provider_status == "placeholder"
    assert result.confidence_summary.required_fields_missing


def test_human_review_agent_creates_task_for_low_confidence_required_field(
    tenant_id,
    human_review_agent,
    repository,
):
    ocr = MockOCRProvider().extract_invoice(
        {
            "mime_type": "application/pdf",
            "content": (
                "invoice_number=INV-LOW supplier_name=Northstar Components currency=USD "
                "invoice_date=2026-05-05 grand_total=1170 confidence_invoice_number=0.5"
            ),
        },
        tenant_id,
    )

    task = human_review_agent.inspect_extraction(ocr, raw_invoice_id=uuid4())

    assert task.status == HumanReviewStatus.REVIEW_REQUIRED
    assert repository.list_review_tasks(tenant_id)
    assert task.issues[0].field_name == "invoice_number"


def test_human_review_agent_skips_high_confidence_extraction(tenant_id, human_review_agent, repository):
    ocr = MockOCRProvider().extract_invoice(
        {
            "mime_type": "application/pdf",
            "content": (
                "invoice_number=INV-HIGH supplier_name=Northstar Components currency=USD "
                "invoice_date=2026-05-05 grand_total=1170 confidence=0.98"
            ),
        },
        tenant_id,
    )

    task = human_review_agent.inspect_extraction(ocr, raw_invoice_id=uuid4())

    assert task.status == HumanReviewStatus.NOT_REQUIRED
    assert repository.list_review_tasks(tenant_id) == []


def test_human_review_correction_submission_updates_status(tenant_id, human_review_agent):
    ocr = MockOCRProvider().extract_invoice(
        {
            "mime_type": "application/pdf",
            "content": (
                "invoice_number=INV-LOW supplier_name=Northstar Components currency=USD "
                "invoice_date=2026-05-05 grand_total=1170 confidence_invoice_number=0.4"
            ),
        },
        tenant_id,
    )
    task = human_review_agent.inspect_extraction(ocr, raw_invoice_id=uuid4())

    result = human_review_agent.submit_corrections(
        task.task_id,
        HumanReviewCorrectionRequest(
            tenant_id=tenant_id,
            corrections={"invoice_number": "INV-CORRECTED"},
            reviewer_id="reviewer-1",
        ),
    )

    assert result.status == HumanReviewStatus.CORRECTED
    assert result.corrected_fields["invoice_number"] == "INV-CORRECTED"


def test_review_tasks_are_tenant_scoped(repository, human_review_agent):
    tenant_a = uuid4()
    tenant_b = uuid4()
    ocr = MockOCRProvider().extract_invoice(
        {
            "mime_type": "application/pdf",
            "content": "invoice_number=INV-LOW confidence_invoice_number=0.4",
        },
        tenant_a,
    )

    human_review_agent.inspect_extraction(ocr, raw_invoice_id=uuid4())

    assert len(repository.list_review_tasks(tenant_a)) == 1
    assert repository.list_review_tasks(tenant_b) == []


class FakeCurrency:
    def __init__(self, amount, currency_code=None):
        self.amount = amount
        self.currency_code = currency_code


class FakeField:
    def __init__(self, value=None, confidence=0.97, **values):
        self.value = value
        self.confidence = confidence
        for key, item in values.items():
            setattr(self, key, item)


class FakeDocument:
    def __init__(self, fields):
        self.fields = fields


class FakeAnalyzeResult:
    def __init__(self, fields):
        self.documents = [FakeDocument(fields)]


def _azure_result(invoice_number_confidence=0.99):
    item = FakeField(
        value_object={
            "Description": FakeField(value="Mock extracted invoice line", confidence=0.97),
            "Quantity": FakeField(value=1, confidence=0.96),
            "UnitPrice": FakeField(value=1000.0, confidence=0.96),
            "Tax": FakeField(value=170.0, confidence=0.96),
            "Amount": FakeField(value=1170.0, confidence=0.96),
        },
        confidence=0.96,
    )
    return FakeAnalyzeResult(
        {
            "InvoiceId": FakeField(value="INV-AZ-1", confidence=invoice_number_confidence),
            "VendorName": FakeField(value="Northstar Components", confidence=0.98),
            "VendorTaxId": FakeField(value="TAX-12345", confidence=0.97),
            "InvoiceDate": FakeField(value="2026-05-06", confidence=0.98),
            "DueDate": FakeField(value="2026-06-05", confidence=0.97),
            "Currency": FakeField(value="USD", confidence=0.96),
            "SubTotal": FakeField(value=1000.0, confidence=0.97),
            "TotalTax": FakeField(value=170.0, confidence=0.96),
            "InvoiceTotal": FakeField(value=FakeCurrency(1170.0), confidence=0.99),
            "PurchaseOrder": FakeField(value="PO-100", confidence=0.95),
            "Items": FakeField(value=[item], confidence=0.96),
        }
    )


def _azure_result_with_alternative_names():
    return FakeAnalyzeResult(
        {
            "InvoiceNumber": FakeField(value="INV-ALT-1", confidence=None),
            "SupplierName": FakeField(value="Alternative Vendor", confidence=0.92),
            "InvoiceDate": FakeField(value="2026-05-07", confidence=0.9),
            "Subtotal": FakeField(value=200, confidence=0.88),
            "TotalTaxAmount": FakeField(value=22.5, confidence=0.86),
            "AmountDue": FakeField(value=FakeCurrency(222.5, currency_code="USD"), confidence=0.93),
            "PurchaseOrderNumber": FakeField(value="PO-ALT-1", confidence=0.85),
        }
    )


def _azure_result_with_dict_line_items():
    return FakeAnalyzeResult(
        {
            "InvoiceId": FakeField(value="INV-DICT-1", confidence=0.99),
            "VendorName": FakeField(value="Northstar Components", confidence=0.98),
            "InvoiceDate": FakeField(value="2026-05-07", confidence=0.98),
            "Currency": FakeField(value="USD", confidence=0.96),
            "InvoiceTotal": FakeField(value=110, confidence=0.98),
            "Items": {
                "valueArray": [
                    {
                        "valueObject": {
                            "Description": {"valueString": "Widget", "confidence": 0.91},
                            "Quantity": {"valueNumber": 2, "confidence": 0.9},
                            "UnitCost": {"valueNumber": 50, "confidence": 0.9},
                            "TaxAmount": {"valueNumber": 10, "confidence": 0.84},
                            "TotalPrice": {"valueNumber": 110, "confidence": 0.88},
                        },
                        "confidence": 0.9,
                    }
                ],
                "confidence": 0.9,
            },
        }
    )
