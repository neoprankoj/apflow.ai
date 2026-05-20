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
