from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.core.schemas import (
    ActorType,
    ApprovalRoute,
    ApprovalTaskStatus,
    AuditEventInput,
    CanonicalInvoice,
    ERPOperation,
    ERPAdapterType,
    ERPSyncLog,
    ERPSyncStatus,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationRecipientType,
    PaymentStatusSource,
    PaymentStatusValue,
)
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


def test_analytics_requires_auth(auth_enabled):
    response = TestClient(create_app()).get(f"/analytics/accuracy?tenant_id={uuid4()}")

    assert response.status_code == 401


def test_owner_and_viewer_can_read_invoice_scoped_analytics(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "analytics-owner@example.com")
    viewer = _create_member(client, owner, "analytics-viewer@example.com", "viewer")

    owner_response = client.get(
        f"/analytics/accuracy?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(owner["access_token"]),
    )
    viewer_response = client.get(
        f"/analytics/accuracy?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(viewer["token"]),
    )

    assert owner_response.status_code == 200
    assert viewer_response.status_code == 200


def test_cross_tenant_analytics_access_is_denied(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "analytics-a@example.com")
    owner_b = _register(client, "analytics-b@example.com")

    response = client.get(
        f"/analytics/accuracy?tenant_id={owner_a['tenant']['id']}",
        headers=_auth_headers(owner_b["access_token"]),
    )

    assert response.status_code == 403


def test_empty_tenant_returns_zero_metrics(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "analytics-empty@example.com")

    response = client.get(
        f"/analytics/accuracy?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    metrics = {item["key"]: item for item in body["invoice_volume"]}
    assert metrics["total_invoices"]["value"] == 0
    assert body["top_blockers"] == []
    assert body["date_range"] == {"start": None, "end": None}


def test_populated_tenant_analytics_summarizes_workflow_and_recommendations(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "analytics-populated@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    invoice_id, vendor_id = _seed_invoice(repository, tenant_id)
    access = repository.create_vendor_portal_access(
        tenant_id=tenant_id,
        vendor_id=vendor_id,
        email="supplier@example.local",
        access_token_hash="hash-only",
        token_prefix="tok-prefix",
    )
    repository.mark_vendor_access_used(tenant_id, access.access_id)
    repository.create_approval_task(
        tenant_id,
        invoice_id,
        ApprovalRoute.BLOCKED,
        "ap_manager",
        ApprovalTaskStatus.BLOCKED,
        "Missing PO and validation blocker.",
    )
    repository.store_erp_sync_log(
        ERPSyncLog(
            tenant_id=tenant_id,
            adapter_type=ERPAdapterType.PRIORITY,
            operation=ERPOperation.EXPORT_INVOICE,
            status=ERPSyncStatus.SUCCESS,
            records_processed=1,
            invoice_id=invoice_id,
        )
    )
    repository.upsert_payment_status(
        tenant_id,
        invoice_id,
        status=PaymentStatusValue.SCHEDULED,
        source=PaymentStatusSource.MOCK,
        amount_due=117,
        currency="USD",
    )
    repository.store_notification_delivery(
        tenant_id,
        event_type="notification.test",
        channel=NotificationChannel.MOCK,
        provider="mock",
        recipient_type=NotificationRecipientType.ADMIN,
        recipient_label="AP Manager",
        status=NotificationDeliveryStatus.SENT,
    )
    for action, metadata in [
        ("invoice.extracted", {"provider_error_code": "invalid_file_signature"}),
        ("review.corrected", {}),
        ("vendor.chat_question_answered", {}),
        ("vendor.chat_question_refused", {}),
        ("vendor.invoice_preview_viewed", {}),
        ("invoice.duplicate_scored", {"status": "possible_duplicate"}),
        ("invoice.validation_failed", {"reason": "grand total mismatch"}),
    ]:
        repository.store_audit_event(
            AuditEventInput(
                tenant_id=tenant_id,
                actor_type=ActorType.SYSTEM,
                actor_id="test",
                action=action,
                entity_type="invoice",
                entity_id=invoice_id,
                metadata=metadata,
            ),
            uuid4(),
        )

    response = client.get(
        f"/analytics/accuracy?tenant_id={tenant_id}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    invoice_metrics = {item["key"]: item for item in body["invoice_volume"]}
    ocr_metrics = {item["key"]: item for item in body["ocr_accuracy"]}
    vendor_metrics = {item["key"]: item for item in body["vendor_self_service"]}
    notification_metrics = {item["key"]: item for item in body["notification_health"]}
    payment = {item["key"]: item for item in body["payment_status_health"]}
    exceptions = {item["key"]: item for item in body["exception_breakdown"]}
    assert invoice_metrics["total_invoices"]["value"] == 1
    assert invoice_metrics["exported_invoices"]["value"] == 1
    assert ocr_metrics["invalid_files"]["value"] == 1
    assert vendor_metrics["used_vendor_access"]["value"] == 1
    assert vendor_metrics["chatbot_answered"]["value"] == 1
    assert notification_metrics["mock_notifications_sent"]["value"] == 1
    assert payment["scheduled"]["count"] == 1
    assert exceptions["blocked_invoices"]["count"] >= 1
    assert any("OCR" in recommendation or "upload" in recommendation for recommendation in body["recommendations"])


def test_analytics_response_does_not_expose_tokens_or_secrets(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "analytics-safe@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    _, vendor_id = _seed_invoice(repository, tenant_id)
    repository.create_vendor_portal_access(
        tenant_id=tenant_id,
        vendor_id=vendor_id,
        email="supplier@example.local",
        access_token_hash="super-secret-token-hash",
        token_prefix="tok-prefix",
    )

    response = client.get(
        f"/analytics/accuracy?tenant_id={tenant_id}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    serialized = response.text.casefold()
    assert "super-secret-token-hash" not in serialized
    assert "access_token" not in serialized
    assert "token_hash" not in serialized
    assert "api_key" not in serialized


def _seed_invoice(repository, tenant_id: UUID):
    vendor = repository.add_vendor(tenant_id, "Analytics Supplier")
    invoice_id = uuid4()
    repository.store_invoice(
        InvoiceNormalizationOutput(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            canonical_invoice=CanonicalInvoice(
                invoice_number=f"AN-{invoice_id.hex[:6]}",
                supplier_name="Analytics Supplier",
                invoice_date="2026-05-01",
                due_date="2026-06-01",
                subtotal=100,
                tax_total=17,
                grand_total=117,
                currency="USD",
                line_items=[InvoiceLineItem(description="Service", quantity=1, unit_price=100, total=100)],
            ),
        )
    )
    repository.update_invoice_vendor(tenant_id, invoice_id, vendor.vendor_id)
    return invoice_id, vendor.vendor_id


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
        dependencies.get_auth_service,
    ):
        provider.cache_clear()
