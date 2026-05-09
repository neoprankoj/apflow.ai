from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from main import create_app


@pytest.fixture(autouse=True)
def isolated_dependencies() -> Iterator[None]:
    previous_auth_enabled = settings.auth_enabled
    previous_demo_mode = settings.demo_mode
    previous_max_upload = settings.max_invoice_upload_bytes
    previous_storage_provider = settings.document_storage_provider
    settings.auth_enabled = False
    settings.demo_mode = True
    settings.max_invoice_upload_bytes = 10 * 1024 * 1024
    settings.document_storage_provider = "memory"
    _clear_dependency_caches()
    yield
    settings.auth_enabled = previous_auth_enabled
    settings.demo_mode = previous_demo_mode
    settings.max_invoice_upload_bytes = previous_max_upload
    settings.document_storage_provider = previous_storage_provider
    _clear_dependency_caches()


def test_successful_pdf_upload_stores_document_metadata():
    client = TestClient(create_app())
    tenant_id = str(uuid4())

    response = _upload(client, tenant_id, _invoice_content("INV-UPLOAD-1"))

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["tenant_id"] == tenant_id
    assert body["document"]["content_type"] == "application/pdf"
    assert body["document"]["size_bytes"] > 0
    assert body["document_reference"]["storage_provider"] == "memory"


def test_unsupported_file_type_is_rejected():
    client = TestClient(create_app())

    response = client.post(
        "/documents/invoices/upload",
        data={"tenant_id": str(uuid4())},
        files={"file": ("invoice.txt", b"not an invoice", "text/plain")},
    )

    assert response.status_code == 415


def test_oversized_upload_is_rejected():
    settings.max_invoice_upload_bytes = 8
    client = TestClient(create_app())

    response = _upload(client, str(uuid4()), b"0123456789")

    assert response.status_code == 413


def test_uploaded_document_metadata_is_tenant_scoped():
    client = TestClient(create_app())
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    uploaded = _upload(client, tenant_a, _invoice_content("INV-TENANT-A")).json()
    document_id = uploaded["document"]["document_id"]

    listed_a = client.get(f"/documents/invoices?tenant_id={tenant_a}")
    listed_b = client.get(f"/documents/invoices?tenant_id={tenant_b}")
    fetched_b = client.get(f"/documents/invoices/{document_id}?tenant_id={tenant_b}")

    assert len(listed_a.json()) == 1
    assert listed_b.json() == []
    assert fetched_b.status_code == 404


def test_extract_uploaded_document_with_mock_ocr():
    client = TestClient(create_app())
    tenant_id = str(uuid4())
    uploaded = _upload(client, tenant_id, _invoice_content("INV-EXTRACT-1")).json()

    response = client.post(
        f"/documents/invoices/{uploaded['document']['document_id']}/extract?tenant_id={tenant_id}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ocr_result"]["provider_metadata"]["provider_name"] == "mock"
    assert body["confidence_summary"]["average_confidence"] > 0.9
    assert body["review_status"] == "not_required"


def test_process_uploaded_document_through_full_pipeline():
    client = TestClient(create_app())
    tenant_id = str(uuid4())
    uploaded = _upload(client, tenant_id, _invoice_content("INV-PROCESS-1")).json()

    response = client.post(
        f"/documents/invoices/{uploaded['document']['document_id']}/process",
        json={"tenant_id": tenant_id},
    )

    assert response.status_code == 200
    body = response.json()
    pipeline = body["pipeline_result"]
    assert body["workflow_status"] == "approval_ready"
    assert pipeline["po_match_result"]["match_status"] == "matched"
    assert pipeline["fraud_risk_result"]["risk_level"] == "low"
    assert pipeline["erp_export_ready"] is True


def test_low_confidence_uploaded_document_creates_review_task():
    client = TestClient(create_app())
    tenant_id = str(uuid4())
    uploaded = _upload(
        client,
        tenant_id,
        _invoice_content("INV-UPLOAD-LOW", extra="confidence_invoice_number=0.4"),
    ).json()

    response = client.post(
        f"/documents/invoices/{uploaded['document']['document_id']}/process",
        json={"tenant_id": tenant_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_status"] == "review_required"
    assert body["review_status"] == "review_required"
    assert body["pipeline_result"]["review_tasks"]


def test_tenant_cannot_process_another_tenant_uploaded_document():
    client = TestClient(create_app())
    tenant_a = str(uuid4())
    tenant_b = str(uuid4())
    uploaded = _upload(client, tenant_a, _invoice_content("INV-XTENANT")).json()

    response = client.post(
        f"/documents/invoices/{uploaded['document']['document_id']}/process",
        json={"tenant_id": tenant_b},
    )

    assert response.status_code == 404


def test_unauthorized_upload_blocked_when_auth_enabled():
    settings.auth_enabled = True
    settings.demo_mode = False
    _clear_dependency_caches()
    client = TestClient(create_app())

    response = _upload(client, str(uuid4()), _invoice_content("INV-AUTH-BLOCKED"))

    assert response.status_code == 401


def test_existing_mock_pipeline_still_works_after_upload_flow():
    client = TestClient(create_app())
    tenant_id = str(uuid4())

    response = client.post(
        "/invoices/full-mock-pipeline",
        json={
            "tenant_id": tenant_id,
            "source": "upload",
            "file_url": "mock://incoming/invoice.pdf",
            "metadata": {"original_filename": "invoice.pdf", "mime_type": "application/pdf"},
            "content": _invoice_content("INV-MOCK-STILL-WORKS").decode(),
        },
    )

    assert response.status_code == 200
    assert response.json()["workflow_status"] == "approval_ready"


def _upload(
    client: TestClient,
    tenant_id: str,
    content: bytes,
    content_type: str = "application/pdf",
):
    return client.post(
        "/documents/invoices/upload",
        data={"tenant_id": tenant_id},
        files={"file": ("invoice.pdf", content, content_type)},
    )


def _invoice_content(invoice_number: str, extra: str = "") -> bytes:
    content = (
        f"invoice_number={invoice_number} supplier_name=Northstar supplier_tax_id=TAX-12345 "
        "subtotal=1000 tax_total=170 grand_total=1170 currency=USD "
        f"invoice_date=2026-05-05 po_number=PO-100 {extra}"
    )
    return content.encode()


def _clear_dependency_caches() -> None:
    for provider in (
        dependencies.get_repository,
        dependencies.get_in_memory_repository,
        dependencies.get_audit_agent,
        dependencies.get_monitoring_agent,
        dependencies.get_error_handler_agent,
        dependencies.get_tenant_security_agent,
        dependencies.get_orchestrator_agent,
        dependencies.get_invoice_ingestion_agent,
        dependencies.get_invoice_extraction_agent,
        dependencies.get_human_review_agent,
        dependencies.get_ocr_provider_factory,
        dependencies.get_storage_adapter,
        dependencies.get_invoice_normalization_agent,
        dependencies.get_supplier_identity_agent,
        dependencies.get_invoice_validation_agent,
        dependencies.get_duplicate_detection_agent,
        dependencies.get_purchase_order_matching_agent,
        dependencies.get_fraud_risk_scoring_agent,
        dependencies.get_approval_routing_agent,
        dependencies.get_notification_agent,
        dependencies.get_erp_connector_agent,
        dependencies.get_auth_service,
    ):
        provider.cache_clear()
