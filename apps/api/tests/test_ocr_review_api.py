from fastapi.testclient import TestClient

from main import create_app


def _tenant() -> str:
    return "44444444-4444-4444-4444-444444444444"


def _ocr_payload(content: str) -> dict:
    return {
        "tenant_id": _tenant(),
        "source": "upload",
        "file_url": "mock://incoming/invoice.pdf",
        "metadata": {
            "sender_email": "ap@example.com",
            "original_filename": "invoice.pdf",
            "mime_type": "application/pdf",
        },
        "content": content,
    }


def test_ocr_providers_endpoint():
    response = TestClient(create_app()).get("/ocr/providers")

    assert response.status_code == 200
    providers = {provider["provider"]: provider for provider in response.json()}
    assert {"mock", "azure", "google", "aws"}.issubset(set(providers))
    assert providers["azure"]["configured"] is False
    assert providers["azure"]["status"] == "missing_credentials"


def test_ocr_providers_endpoint_can_return_legacy_provider_names():
    response = TestClient(create_app()).get("/ocr/providers?include_status=false")

    assert response.status_code == 200
    assert {"mock", "azure", "google", "aws"}.issubset(set(response.json()))


def test_ocr_test_provider_endpoint():
    response = TestClient(create_app()).post("/ocr/test-provider?provider_name=mock")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ocr_extract_endpoint_uses_mock_provider():
    response = TestClient(create_app()).post(
        "/ocr/extract",
        json=_ocr_payload(
            "invoice_number=INV-OCR-API supplier_name=Northstar Components currency=USD "
            "invoice_date=2026-05-05 grand_total=1170"
        ),
    )

    assert response.status_code == 200
    assert response.json()["confidence_summary"]["average_confidence"] > 0.9


def test_pipeline_routes_low_confidence_to_review_required():
    response = TestClient(create_app()).post(
        "/invoices/full-mock-pipeline",
        json=_ocr_payload(
            "invoice_number=INV-REVIEW-API supplier_name=Northstar Components currency=USD "
            "invoice_date=2026-05-05 grand_total=1170 confidence_invoice_number=0.4"
        ),
    )

    assert response.status_code == 200
    assert response.json()["workflow_status"] == "review_required"
    assert response.json()["review_status"] == "review_required"
    assert response.json()["review_tasks"]


def test_pipeline_continues_for_high_confidence_mock_extraction():
    response = TestClient(create_app()).post(
        "/invoices/full-mock-pipeline",
        json=_ocr_payload(
            "invoice_number=INV-NORMAL-API supplier_name=Northstar Components supplier_tax_id=TAX-12345 "
            "subtotal=1000 tax_total=170 grand_total=1170 currency=USD invoice_date=2026-05-05 po_number=PO-100"
        ),
    )

    assert response.status_code == 200
    assert response.json()["workflow_status"] == "approval_ready"
    assert response.json()["review_status"] == "not_required"


def test_review_correction_approve_reject_endpoints():
    client = TestClient(create_app())
    pipeline = client.post(
        "/invoices/full-mock-pipeline",
        json=_ocr_payload(
            "invoice_number=INV-REVIEW-FLOW supplier_name=Northstar Components currency=USD "
            "invoice_date=2026-05-05 grand_total=1170 confidence_invoice_number=0.4"
        ),
    )
    task_id = pipeline.json()["review_tasks"][0]["task_id"]

    listed = client.get(f"/review/tasks?tenant_id={_tenant()}")
    correction = client.post(
        f"/review/tasks/{task_id}/corrections",
        json={
            "tenant_id": _tenant(),
            "corrections": {"invoice_number": "INV-REVIEW-CORRECTED"},
            "reviewer_id": "reviewer-1",
        },
    )
    approved = client.post(f"/review/tasks/{task_id}/approve?tenant_id={_tenant()}")
    rejected = client.post(f"/review/tasks/{task_id}/reject?tenant_id={_tenant()}")

    assert listed.status_code == 200
    assert correction.json()["status"] == "corrected"
    assert approved.status_code == 200
    assert rejected.json()["status"] == "rejected"
