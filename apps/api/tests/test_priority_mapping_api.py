from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.integrations.erp.priority import PriorityODataAdapter
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


def test_priority_readiness_mock_mode_is_not_ready(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-readiness-mock@example.com")

    response = client.get(
        f"/erp/priority/readiness?tenant_id={owner['tenant']['id']}",
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mock"
    assert body["status"] == "not_ready"
    assert body["read_only_fetch_enabled"] is False
    assert "secret" not in str(body).lower()


def test_priority_readiness_real_missing_config_lists_missing_checks(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", False)
    monkeypatch.setattr(settings, "priority_erp_base_url", "")
    monkeypatch.setattr(settings, "priority_erp_username", "")
    monkeypatch.setattr(settings, "priority_erp_password", "")
    monkeypatch.setattr(settings, "priority_erp_api_key", "")
    client = TestClient(create_app())
    owner = _register(client, "priority-readiness-missing@example.com")

    response = client.get(
        f"/erp/priority/readiness?tenant_id={owner['tenant']['id']}",
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    checks = {check["key"]: check for check in body["checks"]}
    assert body["status"] == "not_ready"
    assert checks["base_url"]["status"] == "missing"
    assert checks["auth"]["status"] == "missing"
    assert checks["read_only_fetch"]["status"] == "disabled"


def test_priority_readiness_remote_drill_mock_mode_blocked(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-readiness-drill-mock@example.com")

    response = client.get(
        f"/erp/priority/readiness?tenant_id={owner['tenant']['id']}&check_remote=true",
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert any(check["key"] == "remote_drill" and check["status"] == "disabled" for check in body["checks"])


def test_priority_readiness_remote_drill_missing_credentials_blocked(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", True)
    monkeypatch.setattr(settings, "priority_erp_base_url", "https://priority.example.test/odata")
    monkeypatch.setattr(settings, "priority_erp_username", "")
    monkeypatch.setattr(settings, "priority_erp_password", "")
    monkeypatch.setattr(settings, "priority_erp_api_key", "")
    client = TestClient(create_app())
    owner = _register(client, "priority-readiness-drill-creds@example.com")

    response = client.get(
        f"/erp/priority/readiness?tenant_id={owner['tenant']['id']}&check_remote=true",
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert any("username" in error.lower() or "password" in error.lower() for error in body["errors"])
    assert "secret" not in str(body).lower()


def test_priority_readiness_remote_drill_reports_success(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", True)
    monkeypatch.setattr(settings, "priority_erp_base_url", "https://priority.example.test/odata")
    monkeypatch.setattr(settings, "priority_erp_username", "api-user")
    monkeypatch.setattr(settings, "priority_erp_password", "secret-password")

    def fake_service_root(self):
        return {
            "status": "ok",
            "message": "Priority OData service root is reachable.",
            "base_url_host": "priority.example.test",
            "metadata_available": False,
        }

    def fake_metadata(self):
        return {
            "status": "ok",
            "message": "Priority OData metadata endpoint is reachable.",
            "base_url_host": "priority.example.test",
            "metadata_available": True,
        }

    monkeypatch.setattr(PriorityODataAdapter, "check_service_root", fake_service_root)
    monkeypatch.setattr(PriorityODataAdapter, "check_metadata", fake_metadata)
    client = TestClient(create_app())
    owner = _register(client, "priority-readiness-drill-ok@example.com")

    response = client.get(
        f"/erp/priority/readiness?tenant_id={owner['tenant']['id']}&check_remote=true",
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service_root_available"] is True
    assert body["metadata_available"] is True
    assert "secret-password" not in str(body)


def test_priority_readiness_remote_drill_reports_unauthorized(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", True)
    monkeypatch.setattr(settings, "priority_erp_base_url", "https://priority.example.test/odata")
    monkeypatch.setattr(settings, "priority_erp_username", "api-user")
    monkeypatch.setattr(settings, "priority_erp_password", "secret-password")

    def fake_service_root(self):
        return {
            "status": "unauthorized",
            "message": "Priority rejected the configured credentials.",
            "base_url_host": "priority.example.test",
            "metadata_available": False,
        }

    monkeypatch.setattr(PriorityODataAdapter, "check_service_root", fake_service_root)
    client = TestClient(create_app())
    owner = _register(client, "priority-readiness-drill-unauth@example.com")

    response = client.get(
        f"/erp/priority/readiness?tenant_id={owner['tenant']['id']}&check_remote=true",
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["service_root_available"] is False
    assert any("rejected" in error for error in body["errors"])
    assert "secret-password" not in str(body)


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


def test_priority_preview_priority_source_requires_real_mode(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-real-mode@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/sync-preview/vendors",
        json={"tenant_id": owner["tenant"]["id"], "source": "priority"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "real_mode_required"
    assert response.json()["source"] == "priority"


def test_priority_preview_priority_source_respects_read_only_gate(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", False)
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-disabled@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/sync-preview/vendors",
        json={"tenant_id": owner["tenant"]["id"], "source": "priority"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "read_only_fetch_disabled"
    assert response.json()["records_previewed"] == 0


def test_priority_preview_priority_source_reports_missing_credentials(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", True)
    monkeypatch.setattr(settings, "priority_erp_base_url", "")
    monkeypatch.setattr(settings, "priority_erp_username", "")
    monkeypatch.setattr(settings, "priority_erp_password", "")
    monkeypatch.setattr(settings, "priority_erp_api_key", "")
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-missing-creds@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/sync-preview/vendors",
        json={"tenant_id": owner["tenant"]["id"], "source": "priority"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "missing_credentials"
    assert "password" not in str(response.json()).lower()


def test_priority_preview_priority_source_maps_mocked_vendor_rows(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", True)
    monkeypatch.setattr(settings, "priority_erp_base_url", "https://priority.example.test/odata")
    monkeypatch.setattr(settings, "priority_erp_username", "api-user")
    monkeypatch.setattr(settings, "priority_erp_password", "secret-password")
    captured = {}

    def fake_fetch(self, entity_name: str, limit: int = 50):
        captured["entity_name"] = entity_name
        captured["limit"] = limit
        return [{"SUPNAME": "SUP-LIVE-1", "SUPDES": "Live Supplier", "VATNUM": "LIVE-TAX"}]

    monkeypatch.setattr(PriorityODataAdapter, "fetch_entity_rows_read_only", fake_fetch)
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-live-vendor@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/sync-preview/vendors",
        json={"tenant_id": owner["tenant"]["id"], "source": "priority", "limit": 25},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview_ready"
    assert body["mode"] == "real"
    assert body["source"] == "priority"
    assert body["mapped_records"][0]["external_id"] == "SUP-LIVE-1"
    assert captured == {"entity_name": "SUPPLIERS", "limit": 10}
    assert "secret-password" not in str(body)


def test_priority_preview_priority_source_maps_mocked_purchase_order_rows(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", True)
    monkeypatch.setattr(settings, "priority_erp_base_url", "https://priority.example.test/odata")
    monkeypatch.setattr(settings, "priority_erp_username", "api-user")
    monkeypatch.setattr(settings, "priority_erp_password", "secret-password")

    def fake_fetch(self, entity_name: str, limit: int = 50):
        return [
            {
                "ORDNAME": "PO-LIVE-1",
                "SUPNAME": "SUP-LIVE-1",
                "ORDSTATUSDES": "Open",
                "TOTPRICE": 321.5,
                "CODE": "USD",
            }
        ]

    monkeypatch.setattr(PriorityODataAdapter, "fetch_entity_rows_read_only", fake_fetch)
    client = TestClient(create_app())
    owner = _register(client, "priority-preview-live-po@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/sync-preview/purchase-orders",
        json={"tenant_id": owner["tenant"]["id"], "source": "priority"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "preview_ready"
    assert body["mapped_records"][0]["po_number"] == "PO-LIVE-1"
    assert body["mapped_records"][0]["total_amount"] == 321.5


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


def test_priority_vendor_import_plan_requires_mapping(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-missing@example.com")

    response = client.post(
        "/erp/priority/import-plan",
        json={"tenant_id": owner["tenant"]["id"], "kind": "vendors"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "mapping_required"
    assert response.json()["records_planned"] == 0


def test_priority_import_plan_default_still_uses_sample(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-default-source@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/import-plan/vendors",
        json={"tenant_id": owner["tenant"]["id"]},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "plan_ready"
    assert response.json()["source"] == "sample"


def test_priority_import_plan_priority_source_honors_read_only_gate(auth_enabled, monkeypatch):
    monkeypatch.setattr(settings, "priority_erp_mode", "real")
    monkeypatch.setattr(settings, "priority_erp_read_only_fetch_enabled", False)
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-disabled-source@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/import-plan/vendors",
        json={"tenant_id": owner["tenant"]["id"], "source": "priority"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "read_only_fetch_disabled"
    assert response.json()["records_planned"] == 0


def test_priority_purchase_order_import_plan_requires_mapping(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-missing-pos@example.com")

    response = client.post(
        "/erp/priority/import-plan",
        json={"tenant_id": owner["tenant"]["id"], "kind": "purchase_orders"},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "mapping_required"
    assert response.json()["records_planned"] == 0


def test_priority_vendor_import_plan_creates_without_existing_records(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-create@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()

    response = client.post(
        "/erp/priority/import-plan/vendors",
        json={"tenant_id": owner["tenant"]["id"]},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "plan_ready"
    assert body["summary"]["would_create"] == 2
    assert body["items"][0]["action"] == "would_create"
    assert repository.list_vendors(tenant_id) == []
    assert "secret" not in str(body).lower()


def test_priority_vendor_import_plan_skips_same_existing_vendor(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-skip@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(
        tenant_id=tenant_id,
        name="Demo Office Supplies Ltd.",
        tax_id="DEMO-TAX-999999999",
    )
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")

    response = client.post(
        "/erp/priority/import-plan/vendors",
        json={"tenant_id": owner["tenant"]["id"], "limit": 1},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["action"] == "would_skip"
    assert body["items"][0]["matched_existing_id"] == str(vendor.vendor_id)
    assert len(repository.list_vendors(tenant_id)) == 1


def test_priority_vendor_import_plan_updates_changed_existing_vendor(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-update@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Old Supplier Name", tax_id="OLD-TAX")
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")

    response = client.post(
        "/erp/priority/import-plan/vendors",
        json={"tenant_id": owner["tenant"]["id"], "limit": 1},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["action"] == "would_update"
    assert "name" in item["diff"]
    assert len(repository.list_vendors(tenant_id)) == 1


def test_priority_vendor_import_plan_flags_ambiguous_vendor_matches(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-conflict@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    repository.add_vendor(tenant_id=tenant_id, name="Candidate A", tax_id="DEMO-TAX-999999999")
    repository.add_vendor(tenant_id=tenant_id, name="Candidate B", tax_id="DEMO-TAX-999999999")

    response = client.post(
        "/erp/priority/import-plan/vendors",
        json={"tenant_id": owner["tenant"]["id"], "limit": 1},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["action"] == "would_conflict"
    assert len(repository.list_vendors(tenant_id)) == 2


def test_priority_purchase_order_import_plan_creates_without_existing_records(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-po-create@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()

    response = client.post(
        "/erp/priority/import-plan/purchase-orders",
        json={"tenant_id": owner["tenant"]["id"]},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["would_create"] == 2
    assert body["items"][0]["action"] == "would_create"
    assert repository.list_purchase_orders(tenant_id) == []


def test_priority_purchase_order_import_plan_skips_same_existing_po(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-po-skip@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Demo Office Supplies Ltd.")
    po = repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-240001",
        vendor_id=vendor.vendor_id,
        total_amount=1170.0,
        currency="USD",
    )
    repository.link_external_purchase_order_id(tenant_id, po.purchase_order_id, "PO-240001")

    response = client.post(
        "/erp/priority/import-plan/purchase-orders",
        json={"tenant_id": owner["tenant"]["id"], "limit": 1},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["action"] == "would_skip"
    assert len(repository.list_purchase_orders(tenant_id)) == 1


def test_priority_purchase_order_import_plan_updates_changed_existing_po(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-po-update@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Demo Office Supplies Ltd.")
    po = repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-240001",
        vendor_id=vendor.vendor_id,
        total_amount=999.0,
        currency="USD",
    )
    repository.link_external_purchase_order_id(tenant_id, po.purchase_order_id, "PO-240001")

    response = client.post(
        "/erp/priority/import-plan/purchase-orders",
        json={"tenant_id": owner["tenant"]["id"], "limit": 1},
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["action"] == "would_update"
    assert "total_amount" in item["diff"]
    assert len(repository.list_purchase_orders(tenant_id)) == 1


def test_viewer_cannot_generate_priority_import_plan(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-plan-owner@example.com")
    client.post(
        "/admin/users",
        json={
            "email": "priority-plan-viewer@example.com",
            "full_name": "Viewer",
            "password": "password-123",
            "role": "viewer",
        },
        headers=_headers(owner["access_token"]),
    )
    login = client.post(
        "/auth/login",
        json={"email": "priority-plan-viewer@example.com", "password": "password-123"},
    )

    response = client.post(
        "/erp/priority/import-plan",
        json={"tenant_id": owner["tenant"]["id"], "kind": "vendors"},
        headers=_headers(login.json()["access_token"]),
    )

    assert response.status_code == 403


def test_priority_vendor_import_requires_confirmation(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-confirm@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/import/vendors",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 400
    assert "IMPORT_SELECTED" in response.json()["detail"]


def test_priority_vendor_import_creates_selected_vendor_only(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-vendor-create@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()

    response = client.post(
        "/erp/priority/import/vendors",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "imported"
    assert body["summary"]["created"] == 1
    assert body["items"][0]["result"] == "created"
    vendors = repository.list_vendors(tenant_id)
    assert [vendor.name for vendor in vendors] == ["Demo Office Supplies Ltd."]
    assert repository.list_external_vendor_ids(tenant_id)[vendors[0].vendor_id] == "SUP-1001"
    assert "secret" not in str(body).lower()


def test_priority_vendor_import_blocks_updates_unless_enabled(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-vendor-block-update@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Old Supplier Name", tax_id="OLD-TAX")
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")

    response = client.post(
        "/erp/priority/import/vendors",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
            "allow_updates": False,
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["summary"]["blocked"] == 1
    assert repository.list_vendors(tenant_id)[0].name == "Old Supplier Name"


def test_priority_vendor_import_updates_when_enabled(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-vendor-update@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Old Supplier Name", tax_id="OLD-TAX")
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")

    response = client.post(
        "/erp/priority/import/vendors",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
            "allow_updates": True,
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["updated"] == 1
    updated = repository.list_vendors(tenant_id)[0]
    assert updated.name == "Demo Office Supplies Ltd."
    assert updated.tax_id == "DEMO-TAX-999999999"
    assert any(event.action == "priority.vendor_updated" for event in repository.list_audit_events(tenant_id))


def test_priority_vendor_import_skips_unchanged_vendor(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-vendor-skip@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(
        tenant_id=tenant_id,
        name="Demo Office Supplies Ltd.",
        tax_id="DEMO-TAX-999999999",
    )
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")

    response = client.post(
        "/erp/priority/import/vendors",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["summary"]["skipped"] == 1
    assert len(repository.list_vendors(tenant_id)) == 1


def test_priority_vendor_import_blocks_conflicts(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-vendor-conflict@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    repository.add_vendor(tenant_id=tenant_id, name="Candidate A", tax_id="DEMO-TAX-999999999")
    repository.add_vendor(tenant_id=tenant_id, name="Candidate B", tax_id="DEMO-TAX-999999999")

    response = client.post(
        "/erp/priority/import/vendors",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["summary"]["conflicts"] == 1
    assert len(repository.list_vendors(tenant_id)) == 2
    assert any(event.action == "priority.vendor_import_conflict" for event in repository.list_audit_events(tenant_id))


def test_priority_purchase_order_import_requires_confirmation(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-po-confirm@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )

    response = client.post(
        "/erp/priority/import/purchase-orders",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["PO-240001"],
            "confirmation": "IMPORT",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 400


def test_priority_purchase_order_import_blocks_when_vendor_missing(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-po-missing-vendor@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()

    response = client.post(
        "/erp/priority/import/purchase-orders",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["PO-240001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["summary"]["blocked"] == 1
    assert repository.list_purchase_orders(tenant_id) == []


def test_priority_purchase_order_import_creates_selected_po(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-po-create@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Demo Office Supplies Ltd.")
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")

    response = client.post(
        "/erp/priority/import/purchase-orders",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["PO-240001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["created"] == 1
    assert len(repository.list_purchase_orders(tenant_id)) == 1
    po = repository.list_purchase_orders(tenant_id)[0]
    assert po.po_number == "PO-240001"
    assert po.status == "Open"
    assert repository.list_external_purchase_order_ids(tenant_id)[po.purchase_order_id] == "PO-240001"
    assert any(event.action == "priority.purchase_order_created" for event in repository.list_audit_events(tenant_id))


def test_priority_purchase_order_import_does_not_create_unselected_po(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-po-selected@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Demo Facilities Services Ltd.")
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1002")

    response = client.post(
        "/erp/priority/import/purchase-orders",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["PO-240002"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    pos = repository.list_purchase_orders(tenant_id)
    assert [po.po_number for po in pos] == ["PO-240002"]


def test_priority_purchase_order_import_update_respects_allow_updates(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-po-update@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Demo Office Supplies Ltd.")
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")
    po = repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-240001",
        vendor_id=vendor.vendor_id,
        total_amount=999.0,
        currency="USD",
    )
    repository.link_external_purchase_order_id(tenant_id, po.purchase_order_id, "PO-240001")

    blocked = client.post(
        "/erp/priority/import/purchase-orders",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["PO-240001"],
            "confirmation": "IMPORT_SELECTED",
            "allow_updates": False,
        },
        headers=_headers(owner["access_token"]),
    )
    updated = client.post(
        "/erp/priority/import/purchase-orders",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["PO-240001"],
            "confirmation": "IMPORT_SELECTED",
            "allow_updates": True,
        },
        headers=_headers(owner["access_token"]),
    )

    assert blocked.status_code == 200
    assert blocked.json()["summary"]["blocked"] == 1
    assert updated.status_code == 200
    assert updated.json()["summary"]["updated"] == 1
    assert repository.list_purchase_orders(tenant_id)[0].total_amount == 1170.0


def test_viewer_cannot_import_priority_records(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-import-owner@example.com")
    client.post(
        "/admin/users",
        json={
            "email": "priority-import-viewer@example.com",
            "full_name": "Viewer",
            "password": "password-123",
            "role": "viewer",
        },
        headers=_headers(owner["access_token"]),
    )
    login = client.post(
        "/auth/login",
        json={"email": "priority-import-viewer@example.com", "password": "password-123"},
    )

    response = client.post(
        "/erp/priority/import",
        json={
            "tenant_id": owner["tenant"]["id"],
            "kind": "vendors",
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(login.json()["access_token"]),
    )

    assert response.status_code == 403


def test_priority_imported_vendor_records_show_controlled_import(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-imported-vendors@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()

    imported = client.post(
        "/erp/priority/import/vendors",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )
    before_count = len(repository.list_vendors(tenant_id))
    response = client.get(
        f"/erp/priority/imported/vendors?tenant_id={owner['tenant']['id']}",
        headers=_headers(owner["access_token"]),
    )

    assert imported.status_code == 200
    assert response.status_code == 200
    assert len(repository.list_vendors(tenant_id)) == before_count
    body = response.json()
    assert body["kind"] == "vendors"
    assert body["records"][0]["external_id"] == "SUP-1001"
    assert body["records"][0]["name"] == "Demo Office Supplies Ltd."
    assert body["records"][0]["imported_from_priority"] is True
    assert body["records"][0]["last_import_action"] == "created"
    assert body["records"][0]["last_imported_at"] is not None
    assert "secret" not in str(body).lower()


def test_priority_imported_purchase_order_records_show_controlled_import(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-imported-pos@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner["tenant"]["id"]),
        headers=_headers(owner["access_token"]),
    )
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Demo Office Supplies Ltd.")
    repository.link_external_vendor_id(tenant_id, vendor.vendor_id, "SUP-1001")

    imported = client.post(
        "/erp/priority/import/purchase-orders",
        json={
            "tenant_id": owner["tenant"]["id"],
            "selected_external_ids": ["PO-240001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner["access_token"]),
    )
    before_count = len(repository.list_purchase_orders(tenant_id))
    response = client.get(
        f"/erp/priority/imported/purchase-orders?tenant_id={owner['tenant']['id']}",
        headers=_headers(owner["access_token"]),
    )

    assert imported.status_code == 200
    assert response.status_code == 200
    assert len(repository.list_purchase_orders(tenant_id)) == before_count
    body = response.json()
    assert body["kind"] == "purchase_orders"
    assert body["records"][0]["external_id"] == "PO-240001"
    assert body["records"][0]["po_number"] == "PO-240001"
    assert body["records"][0]["vendor_external_id"] == "SUP-1001"
    assert body["records"][0]["imported_from_priority"] is True
    assert body["records"][0]["last_import_action"] == "created"


def test_priority_imported_records_include_local_records_without_external_reference(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-imported-local-record@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_in_memory_repository()
    repository.add_vendor(tenant_id=tenant_id, name="Local Vendor", tax_id="LOCAL-TAX")

    response = client.get(
        f"/erp/priority/imported/vendors?tenant_id={owner['tenant']['id']}",
        headers=_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    record = response.json()["records"][0]
    assert record["name"] == "Local Vendor"
    assert record["external_id"] is None
    assert record["imported_from_priority"] is False


def test_priority_imported_records_are_tenant_scoped(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "priority-imported-tenant-a@example.com")
    owner_b = _register(client, "priority-imported-tenant-b@example.com")
    tenant_a = UUID(owner_a["tenant"]["id"])
    repository = dependencies.get_in_memory_repository()
    vendor = repository.add_vendor(tenant_id=tenant_a, name="Tenant A Vendor")
    repository.link_external_vendor_id(tenant_a, vendor.vendor_id, "SUP-A")

    forbidden = client.get(
        f"/erp/priority/imported/vendors?tenant_id={owner_a['tenant']['id']}",
        headers=_headers(owner_b["access_token"]),
    )
    own_records = client.get(
        f"/erp/priority/imported/vendors?tenant_id={owner_b['tenant']['id']}",
        headers=_headers(owner_b["access_token"]),
    )

    assert forbidden.status_code == 403
    assert own_records.status_code == 200
    assert own_records.json()["records"] == []


def test_viewer_can_read_priority_imported_records(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-imported-owner@example.com")
    client.post(
        "/admin/users",
        json={
            "email": "priority-imported-viewer@example.com",
            "full_name": "Viewer",
            "password": "password-123",
            "role": "viewer",
        },
        headers=_headers(owner["access_token"]),
    )
    login = client.post(
        "/auth/login",
        json={"email": "priority-imported-viewer@example.com", "password": "password-123"},
    )

    response = client.get(
        f"/erp/priority/imported/vendors?tenant_id={owner['tenant']['id']}",
        headers=_headers(login.json()["access_token"]),
    )

    assert response.status_code == 200


def test_priority_import_is_tenant_scoped(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "priority-import-tenant-a@example.com")
    owner_b = _register(client, "priority-import-tenant-b@example.com")
    client.put(
        "/erp/priority/mapping",
        json=_mapping_payload(owner_a["tenant"]["id"]),
        headers=_headers(owner_a["access_token"]),
    )

    response = client.post(
        "/erp/priority/import",
        json={
            "tenant_id": owner_a["tenant"]["id"],
            "kind": "vendors",
            "selected_external_ids": ["SUP-1001"],
            "confirmation": "IMPORT_SELECTED",
        },
        headers=_headers(owner_b["access_token"]),
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
