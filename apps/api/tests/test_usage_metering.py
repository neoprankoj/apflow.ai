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
    UsageEventType,
)
from main import create_app


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous = {
        "auth_enabled": settings.auth_enabled,
        "demo_mode": settings.demo_mode,
        "use_in_memory_repositories": settings.use_in_memory_repositories,
        "ocr_provider": settings.ocr_provider,
        "document_storage_provider": settings.document_storage_provider,
    }
    settings.auth_enabled = True
    settings.demo_mode = False
    settings.use_in_memory_repositories = True
    settings.ocr_provider = "mock"
    settings.document_storage_provider = "memory"
    _clear_dependency_caches()
    yield
    for key, value in previous.items():
        setattr(settings, key, value)
    _clear_dependency_caches()


def test_usage_summary_requires_auth(auth_enabled):
    response = TestClient(create_app()).get(f"/usage/summary?tenant_id={uuid4()}")

    assert response.status_code == 401


def test_empty_usage_summary_returns_demo_plan_and_zero_counts(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "usage-empty@example.com")

    response = client.get(
        f"/usage/summary?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_plan"]["plan_key"] == "demo"
    assert body["usage_by_event_type"] == {}
    assert body["recent_events"] == []
    assert any(metric["key"] == "invoices" and metric["used"] == 0 for metric in body["limits"])


def test_manual_usage_event_can_be_created_and_listed_by_owner(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "usage-manual@example.com")

    created = client.post(
        "/usage/events/manual-test",
        json={
            "tenant_id": owner["tenant"]["id"],
            "event_type": "manual_test",
            "quantity": 3,
            "metadata": {"safe": "ok", "api_key": "secret-value"},
        },
        headers=_auth_headers(owner["access_token"]),
    )
    listed = client.get(
        f"/usage/events?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json()[0]["event_type"] == "manual_test"
    assert listed.json()[0]["quantity"] == 3
    serialized = listed.text.casefold()
    assert "secret-value" not in serialized
    assert "api_key" not in serialized


def test_invoice_upload_records_usage_event(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "usage-upload@example.com")

    upload = client.post(
        "/documents/invoices/upload",
        data={"tenant_id": owner["tenant"]["id"]},
        files={"file": ("invoice.pdf", b"%PDF-1.4\n%demo", "application/pdf")},
        headers=_auth_headers(owner["access_token"]),
    )
    events = _usage_events(client, owner)

    assert upload.status_code == 200
    assert _event_count(events, UsageEventType.INVOICE_UPLOADED) == 1


def test_payment_vendor_chatbot_notification_and_analytics_usage_are_metered(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "usage-flow@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    invoice_id, vendor_id = _seed_invoice(repository, tenant_id)

    payment_sync = client.post(
        "/payments/sync/mock",
        json={"tenant_id": str(tenant_id), "mode": "mock", "invoice_id": str(invoice_id)},
        headers=_auth_headers(owner["access_token"]),
    )
    notification = client.post(
        "/notifications/test",
        json={"tenant_id": str(tenant_id), "channel": "mock", "recipient_label": "AP Manager"},
        headers=_auth_headers(owner["access_token"]),
    )
    access = client.post(
        "/vendor/accesses",
        json={"tenant_id": str(tenant_id), "vendor_id": str(vendor_id), "email": "supplier@example.local"},
        headers=_auth_headers(owner["access_token"]),
    )
    access_token = access.json()["access_token"]
    vendor_list = client.get(f"/vendor/invoices?tenant_id={tenant_id}&access_token={access_token}")
    chat = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "access_token": access_token, "question": "What is the status of invoice U-100?"},
    )
    analytics = client.get(
        f"/analytics/accuracy?tenant_id={tenant_id}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert payment_sync.status_code == 200
    assert notification.status_code == 200
    assert access.status_code == 200
    assert vendor_list.status_code == 200
    assert chat.status_code == 200
    assert analytics.status_code == 200

    events = _usage_events(client, owner)
    assert _event_count(events, UsageEventType.PAYMENT_MOCK_SYNC_RUN) >= 1
    assert _event_count(events, UsageEventType.PAYMENT_STATUS_UPDATED) >= 1
    assert _event_count(events, UsageEventType.NOTIFICATION_MOCK_SENT) >= 1
    assert _event_count(events, UsageEventType.VENDOR_ACCESS_CREATED) >= 1
    assert _event_count(events, UsageEventType.VENDOR_ACCESS_USED) >= 1
    assert _event_count(events, UsageEventType.VENDOR_CHATBOT_QUESTION_ANSWERED) >= 1
    assert _event_count(events, UsageEventType.ANALYTICS_VIEWED) >= 1

    summary = client.get(
        f"/usage/summary?tenant_id={tenant_id}",
        headers=_auth_headers(owner["access_token"]),
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["usage_by_category"]["payments"] >= 1
    assert body["usage_by_category"]["vendor"] >= 1
    assert body["usage_by_category"]["chatbot"] >= 1
    assert body["usage_by_category"]["notifications"] >= 1


def test_usage_access_is_tenant_scoped_and_role_restricted(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "usage-a@example.com")
    owner_b = _register(client, "usage-b@example.com")
    viewer = _create_member(client, owner_a, "usage-viewer@example.com", "viewer")

    cross_tenant = client.get(
        f"/usage/summary?tenant_id={owner_a['tenant']['id']}",
        headers=_auth_headers(owner_b["access_token"]),
    )
    viewer_events = client.get(
        f"/usage/events?tenant_id={owner_a['tenant']['id']}",
        headers=_auth_headers(viewer["token"]),
    )
    viewer_summary = client.get(
        f"/usage/summary?tenant_id={owner_a['tenant']['id']}",
        headers=_auth_headers(viewer["token"]),
    )

    assert cross_tenant.status_code == 403
    assert viewer_events.status_code == 403
    assert viewer_summary.status_code == 200


def test_product_readiness_reflects_usage_foundation(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "usage-readiness@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    checks = {item["key"]: item for item in response.json()["checks"]}
    assert checks["usage_metering_foundation_available"]["status"] == "pass"
    assert checks["usage_metering_configured"]["status"] == "pass"
    assert checks["billing_provider_connected"]["status"] == "fail"
    assert checks["customer_subscription_management_available"]["status"] == "fail"


def _seed_invoice(repository, tenant_id: UUID):
    vendor = repository.add_vendor(tenant_id, "Usage Supplier")
    invoice_id = uuid4()
    repository.store_invoice(
        InvoiceNormalizationOutput(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            canonical_invoice=CanonicalInvoice(
                invoice_number="U-100",
                supplier_name="Usage Supplier",
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


def _usage_events(client: TestClient, owner: dict) -> list[dict]:
    response = client.get(
        f"/usage/events?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(owner["access_token"]),
    )
    assert response.status_code == 200
    return response.json()


def _event_count(events: list[dict], event_type: UsageEventType) -> int:
    return sum(event["quantity"] for event in events if event["event_type"] == str(event_type))


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
        dependencies.get_storage_adapter,
    ):
        provider.cache_clear()
