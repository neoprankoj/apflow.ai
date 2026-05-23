from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.core.schemas import (
    CanonicalInvoice,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    PaymentStatusSource,
    PaymentStatusValue,
)
from app.core.vendor_portal import vendor_invoice_status
from main import create_app


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous = {
        "auth_enabled": settings.auth_enabled,
        "demo_mode": settings.demo_mode,
        "use_in_memory_repositories": settings.use_in_memory_repositories,
        "ocr_provider": settings.ocr_provider,
    }
    settings.auth_enabled = True
    settings.demo_mode = False
    settings.use_in_memory_repositories = True
    settings.ocr_provider = "mock"
    _clear_dependency_caches()
    yield
    for key, value in previous.items():
        setattr(settings, key, value)
    _clear_dependency_caches()


def test_mock_sync_creates_tenant_scoped_payment_statuses_and_audit_events(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "payments-owner@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    invoice_id = _seed_invoice(repository, tenant_id)

    response = client.post(
        "/payments/sync/mock",
        json={"tenant_id": str(tenant_id), "mode": "mock", "invoice_id": str(invoice_id)},
        headers=_auth_headers(owner["access_token"]),
    )
    listed = client.get(f"/payments/statuses?tenant_id={tenant_id}", headers=_auth_headers(owner["access_token"]))
    summary = client.get(f"/payments/summary?tenant_id={tenant_id}", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    assert response.json()[0]["invoice_id"] == str(invoice_id)
    assert response.json()[0]["source"] == "mock"
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert summary.status_code == 200
    assert summary.json()["scheduled_count"] == 1
    assert repository.list_audit_events(tenant_id)[-1].action == "payment.mock_sync_run"


def test_owner_can_update_payment_status_and_viewer_cannot(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "payments-update-owner@example.com")
    viewer = _create_member(client, owner, "payments-viewer@example.com", "viewer")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    invoice_id = _seed_invoice(repository, tenant_id)
    payment = repository.upsert_payment_status(
        tenant_id,
        invoice_id,
        status=PaymentStatusValue.PENDING,
        source=PaymentStatusSource.MOCK,
        amount_due=117,
        amount_paid=0,
        currency="USD",
        safe_vendor_message="Payment is pending AP processing.",
    )

    viewer_response = client.patch(
        f"/payments/statuses/{payment.id}?tenant_id={tenant_id}",
        json={"status": "paid", "amount_paid": 117},
        headers=_auth_headers(viewer["token"]),
    )
    owner_response = client.patch(
        f"/payments/statuses/{payment.id}?tenant_id={tenant_id}",
        json={"status": "paid", "amount_paid": 117, "internal_note": "Internal AP note"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert viewer_response.status_code == 403
    assert owner_response.status_code == 200
    assert owner_response.json()["status"] == "paid"
    assert owner_response.json()["amount_paid"] == 117
    assert repository.list_audit_events(tenant_id)[-1].action == "payment.status_updated"


def test_cross_tenant_payment_status_access_is_denied(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "payments-a@example.com")
    owner_b = _register(client, "payments-b@example.com")
    repository = dependencies.get_repository()
    tenant_a = UUID(owner_a["tenant"]["id"])
    invoice_id = _seed_invoice(repository, tenant_a)
    payment = repository.upsert_payment_status(
        tenant_a,
        invoice_id,
        status=PaymentStatusValue.SCHEDULED,
        source=PaymentStatusSource.MOCK,
    )

    response = client.get(
        f"/payments/statuses/{payment.id}?tenant_id={owner_b['tenant']['id']}",
        headers=_auth_headers(owner_b["access_token"]),
    )

    assert response.status_code == 404


def test_vendor_safe_preview_includes_safe_payment_status_only(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "payments-vendor-owner@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor = repository.add_vendor(tenant_id, "Vendor Safe")
    invoice_id = _seed_invoice(repository, tenant_id, vendor.vendor_id)
    repository.upsert_payment_status(
        tenant_id,
        invoice_id,
        status=PaymentStatusValue.SCHEDULED,
        source=PaymentStatusSource.MANUAL,
        amount_due=117,
        amount_paid=0,
        currency="USD",
        external_payment_reference="internal-ref-123",
        safe_vendor_message="Payment is scheduled by AP.",
        internal_note="Never show this to vendors.",
    )

    response = client.get(
        f"/vendor/preview/invoices/{invoice_id}?tenant_id={tenant_id}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payment_status"] == "scheduled"
    assert body["payment_status_detail"]["safe_message"] == "Payment is scheduled by AP."
    serialized = response.text
    assert "Never show this" not in serialized
    assert "internal-ref-123" not in serialized
    assert "internal_note" not in serialized
    assert "external_payment_reference" not in serialized


def test_product_readiness_reflects_payment_foundation(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "payments-readiness@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    checks = {item["key"]: item for item in response.json()["checks"]}
    assert checks["payment_status_foundation_available"]["status"] == "pass"
    assert checks["real_payment_sync_configured"]["status"] == "fail"
    assert checks["payment_status_sync_ready"]["status"] == "fail"


def _seed_invoice(repository, tenant_id: UUID, vendor_id=None):
    if vendor_id is None:
        vendor_id = repository.add_vendor(tenant_id, "Payment Vendor").vendor_id
    output = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number=f"INV-PAY-{uuid4()}",
            supplier_name="Payment Vendor",
            invoice_date="2026-05-23",
            due_date="2026-05-30",
            currency="USD",
            subtotal=100,
            tax_total=17,
            grand_total=117,
            line_items=[
                InvoiceLineItem(
                    description="Payment status test",
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
    return output.invoice_id


def _register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/auth/register-demo-tenant",
        json={
            "tenant_name": f"Tenant {email}",
            "tenant_slug": email.split("@")[0],
            "email": email,
            "full_name": "Owner User",
            "password": "password-123",
        },
    )
    assert response.status_code == 200
    return response.json()


def _create_member(client: TestClient, owner: dict, email: str, role: str) -> dict:
    created = client.post(
        "/admin/users",
        json={
            "email": email,
            "full_name": "Tenant Member",
            "password": "password-123",
            "role": role,
        },
        headers=_auth_headers(owner["access_token"]),
    )
    assert created.status_code == 200
    login = client.post("/auth/login", json={"email": email, "password": "password-123"})
    assert login.status_code == 200
    return {"token": login.json()["access_token"], "user": created.json()["user"]}


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
        dependencies.get_payment_status_chatbot_agent,
    ):
        provider.cache_clear()
