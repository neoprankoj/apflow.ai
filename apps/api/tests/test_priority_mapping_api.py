from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from main import create_app


def _mapping_payload(tenant_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "mapping": {
            "vendors": {
                "entity_name": "SUPPLIERS",
                "external_id_field": "SUPNAME",
                "fields": {"name": "SUPDES", "tax_id": "VATNUM"},
            },
            "purchase_orders": {
                "entity_name": "PORDERS",
                "external_id_field": "ORDNAME",
                "fields": {
                    "po_number": "ORDNAME",
                    "vendor_external_id": "SUPNAME",
                    "status": "ORDSTATUSDES",
                    "total_amount": "TOTPRICE",
                    "currency": "CODE",
                },
            },
            "invoice_export": {
                "entity_name": "APINVOICES",
                "external_id_field": "IVNUM",
                "fields": {
                    "invoice_number": "IVNUM",
                    "invoice_date": "IVDATE",
                    "vendor_external_id": "SUPNAME",
                    "total_amount": "TOTPRICE",
                    "currency": "CODE",
                },
            },
        },
    }


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous_auth_enabled = settings.auth_enabled
    previous_demo_mode = settings.demo_mode
    settings.auth_enabled = True
    settings.demo_mode = False
    _clear_dependency_caches()
    yield
    settings.auth_enabled = previous_auth_enabled
    settings.demo_mode = previous_demo_mode
    _clear_dependency_caches()


def test_owner_can_save_and_read_priority_mapping(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-owner@example.com")
    payload = _mapping_payload(owner["tenant"]["id"])

    saved = client.put(
        "/erp/priority/mapping",
        json=payload,
        headers=_headers(owner["access_token"]),
    )
    loaded = client.get(
        f"/erp/priority/mapping?tenant_id={owner['tenant']['id']}",
        headers=_headers(owner["access_token"]),
    )

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["mapping"]["vendors"]["entity_name"] == "SUPPLIERS"


def test_viewer_cannot_save_priority_mapping(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-owner-viewer@example.com")
    created = client.post(
        "/admin/users",
        json={
            "email": "priority-viewer@example.com",
            "full_name": "Viewer",
            "password": "password-123",
            "role": "viewer",
        },
        headers=_headers(owner["access_token"]),
    )
    login = client.post(
        "/auth/login",
        json={"email": "priority-viewer@example.com", "password": "password-123"},
    )

    response = client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(login.json()["access_token"]),
    )

    assert created.status_code == 200
    assert response.status_code == 403


def test_priority_mapping_is_tenant_scoped(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "priority-tenant-a@example.com")
    owner_b = _register(client, "priority-tenant-b@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner_a["tenant"]["id"]),
        headers=_headers(owner_a["access_token"]),
    )

    response = client.get(
        f"/erp/priority/mapping?tenant_id={owner_a['tenant']['id']}",
        headers=_headers(owner_b["access_token"]),
    )

    assert response.status_code == 403


def test_priority_mapping_validation_endpoint_returns_structural_warning(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-validate@example.com")

    response = client.post(
        "/erp/priority/validate-mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert "validated structurally only" in response.json()["warnings"][-1]


def test_priority_vendor_preview_requires_mapping(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-missing@example.com")

    response = client.post(
        "/erp/priority/sync-preview",
        json={"tenant_id": owner["tenant"]["id"], "kind": "vendors"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "mapping_required"
    assert response.json()["records_previewed"] == 0


def test_priority_vendor_preview_maps_sample_without_import(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-vendors@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()

    response = client.post(
        "/erp/priority/sync-preview/vendors",
        json={"tenant_id": owner["tenant"]["id"]},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview_ready"
    assert body["source"] == "sample"
    assert body["mapped_records"][0]["external_id"] == "SUP-1001"
    assert body["mapped_records"][0]["name"] == "Demo Office Supplies Ltd."
    assert repository.list_vendors(UUID(owner["tenant"]["id"])) == []
    assert "secret" not in str(body).lower()


def test_priority_purchase_order_preview_maps_sample_without_import(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-pos@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()

    response = client.post(
        "/erp/priority/sync-preview/purchase-orders",
        json={"tenant_id": owner["tenant"]["id"]},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview_ready"
    assert body["kind"] == "purchase_orders"
    assert body["mapped_records"][0]["po_number"] == "PO-240001"
    assert body["mapped_records"][0]["total_amount"] == 1170.0
    assert repository.list_purchase_orders(UUID(owner["tenant"]["id"])) == []


def test_priority_preview_missing_raw_fields_warns(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-warnings@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/sync-preview",
        json={
            "tenant_id": owner["tenant"]["id"],
            "kind": "vendors",
            "sample_records": [{"SUPNAME": "SUP-MISSING"}],
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview_ready"
    assert any("SUPDES" in warning for warning in body["warnings"])
    assert body["mapped_records"][0]["name"] is None


def test_viewer_cannot_run_priority_preview(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-owner@example.com")
    client.post(
        "/admin/users",
        json={
            "email": "priority-preview-viewer@example.com",
            "full_name": "Viewer",
            "password": "password-123",
            "role": "viewer",
        },
        headers=_headers(owner["access_token"]),
    )
    login = client.post(
        "/auth/login",
        json={"email": "priority-preview-viewer@example.com", "password": "password-123"},
    )

    response = client.post(
        "/erp/priority/sync-preview",
        json={"tenant_id": owner["tenant"]["id"], "kind": "vendors"},
        headers=_headers(login.json()["access_token"]),
    )

    assert response.status_code == 403


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
    ):
        provider.cache_clear()
