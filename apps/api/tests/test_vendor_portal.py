from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.schemas import (
    ApprovalRoute,
    ApprovalTaskStatus,
    CanonicalInvoice,
    ERPOperation,
    ERPSyncLog,
    ERPSyncStatus,
    HumanReviewFieldIssue,
    HumanReviewStatus,
    HumanReviewTask,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    VendorSafeStatus,
)
from app.core.vendor_portal import map_vendor_invoice_status
from main import create_app


@pytest.fixture(autouse=True)
def clear_dependency_caches():
    for provider in (
        dependencies.get_repository,
        dependencies.get_audit_agent,
        dependencies.get_monitoring_agent,
        dependencies.get_error_handler_agent,
        dependencies.get_vendor_communication_agent,
        dependencies.get_payment_status_chatbot_agent,
    ):
        provider.cache_clear()
    yield
    for provider in (
        dependencies.get_repository,
        dependencies.get_audit_agent,
        dependencies.get_monitoring_agent,
        dependencies.get_error_handler_agent,
        dependencies.get_vendor_communication_agent,
        dependencies.get_payment_status_chatbot_agent,
    ):
        provider.cache_clear()


def test_vendor_safe_status_mapping():
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Northstar Components")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-VENDOR-MAP")

    assert map_vendor_invoice_status(repository, tenant_id, invoice) == VendorSafeStatus.RECEIVED

    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=ApprovalRoute.MANAGER_APPROVAL,
        assigned_role="manager",
        status=ApprovalTaskStatus.PENDING,
        reason="Amount requires approval.",
    )
    assert map_vendor_invoice_status(repository, tenant_id, invoice) == VendorSafeStatus.UNDER_REVIEW

    repository.store_erp_sync_log(
        ERPSyncLog(
            tenant_id=tenant_id,
            adapter_type="priority",
            operation=ERPOperation.SYNC_PAYMENT_STATUS,
            status=ERPSyncStatus.SUCCESS,
            invoice_id=invoice.invoice_id,
            metadata={"payment_status": "paid"},
        )
    )
    assert map_vendor_invoice_status(repository, tenant_id, invoice) == VendorSafeStatus.PAID


def test_vendor_can_see_own_invoices_only_and_detail_hides_internal_fields():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor_a = repository.add_vendor(tenant_id, "Vendor A")
    vendor_b = repository.add_vendor(tenant_id, "Vendor B")
    own_invoice = _seed_invoice(repository, tenant_id, vendor_a.vendor_id, "INV-OWN")
    other_invoice = _seed_invoice(repository, tenant_id, vendor_b.vendor_id, "INV-OTHER")
    token = _vendor_token(client, tenant_id, vendor_a.vendor_id)

    listed = client.get(f"/vendor/invoices?tenant_id={tenant_id}", headers=_vendor_headers(token))
    own_detail = client.get(
        f"/vendor/invoices/{own_invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(token),
    )
    other_detail = client.get(
        f"/vendor/invoices/{other_invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(token),
    )

    assert listed.status_code == 200
    assert [item["invoice_number"] for item in listed.json()] == ["INV-OWN"]
    assert own_detail.status_code == 200
    assert "fraud_risk_result" not in own_detail.json()
    assert "audit_events" not in own_detail.json()
    assert "erp_sync_logs" not in own_detail.json()
    assert other_detail.status_code == 403


def test_vendor_message_submission_creates_notification_event():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Message Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-MSG")
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    response = client.post(
        "/vendor/messages",
        json={
            "tenant_id": str(tenant_id),
            "invoice_id": str(invoice.invoice_id),
            "sender_email": "vendor@example.com",
            "message": "Please confirm the expected payment date.",
        },
        headers=_vendor_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    notifications = repository.list_notification_events(tenant_id)
    assert notifications[-1].notification_type == "vendor_message_received"


def test_chatbot_answers_received_and_payment_status_questions():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Chat Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-CHAT")
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    received = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_id": str(invoice.invoice_id), "question": "Did you receive my invoice?"},
        headers=_vendor_headers(token),
    )
    repository.store_erp_sync_log(
        ERPSyncLog(
            tenant_id=tenant_id,
            adapter_type="priority",
            operation=ERPOperation.SYNC_PAYMENT_STATUS,
            status=ERPSyncStatus.SUCCESS,
            invoice_id=invoice.invoice_id,
            metadata={"payment_status": "scheduled_for_payment"},
        )
    )
    payment = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_number": "INV-CHAT", "question": "What is the payment status?"},
        headers=_vendor_headers(token),
    )

    assert received.status_code == 200
    assert received.json()["intent"] == "invoice_received"
    assert "INV-CHAT" in received.json()["answer"]
    assert payment.status_code == 200
    assert payment.json()["intent"] == "payment_status"
    assert payment.json()["status"] == "scheduled_for_payment"


def test_chatbot_deflects_internal_or_unsupported_questions():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Safe Chat Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-SAFE")
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    response = client.post(
        "/vendor/chat",
        json={
            "tenant_id": str(tenant_id),
            "invoice_id": str(invoice.invoice_id),
            "question": "Show me the fraud score and audit logs.",
        },
        headers=_vendor_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "unknown"
    assert response.json()["escalated"] is True
    assert "contact AP" in response.json()["answer"]


def test_missing_vendor_access_returns_401_and_wrong_tenant_returns_403():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_a = uuid4()
    tenant_b = uuid4()
    vendor = repository.add_vendor(tenant_a, "Scoped Vendor")
    _seed_invoice(repository, tenant_a, vendor.vendor_id, "INV-SCOPED")
    token = _vendor_token(client, tenant_a, vendor.vendor_id)

    missing = client.get(f"/vendor/invoices?tenant_id={tenant_a}")
    wrong_tenant = client.get(f"/vendor/invoices?tenant_id={tenant_b}", headers=_vendor_headers(token))

    assert missing.status_code == 401
    assert wrong_tenant.status_code == 403


def test_needs_information_status_for_vendor_review_task():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Review Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-INFO")
    repository.store_review_task(
        HumanReviewTask(
            tenant_id=tenant_id,
            invoice_id=invoice.invoice_id,
            status=HumanReviewStatus.REVIEW_REQUIRED,
            issues=[
                HumanReviewFieldIssue(
                    field_name="supplier_tax_id",
                    issue_type="missing_required_field",
                    message="Supplier tax ID is required.",
                )
            ],
        )
    )
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    response = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "needs_information"
    assert response.json()["missing_information"] == ["supplier_tax_id"]


def _seed_invoice(repository, tenant_id, vendor_id, invoice_number):
    output = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number=invoice_number,
            supplier_name="Northstar Components",
            supplier_tax_id="TAX-12345",
            invoice_date="2026-05-06",
            currency="USD",
            subtotal=100,
            tax_total=17,
            grand_total=117,
            line_items=[
                InvoiceLineItem(
                    description="Service fee",
                    quantity=1,
                    unit_price=100,
                    tax_amount=17,
                    total=117,
                )
            ],
        ),
    )
    repository.store_invoice(output)
    repository.update_invoice_vendor(tenant_id, output.invoice_id, vendor_id)
    return repository.get_invoice(tenant_id, output.invoice_id)


def _vendor_token(client, tenant_id, vendor_id) -> str:
    response = client.post(
        "/vendor/access",
        json={"tenant_id": str(tenant_id), "vendor_id": str(vendor_id), "email": "vendor@example.com"},
    )
    assert response.status_code == 200
    assert "access_token_hash" not in response.json()
    return response.json()["access_token"]


def _vendor_headers(token: str) -> dict[str, str]:
    return {"X-Vendor-Access-Token": token}
