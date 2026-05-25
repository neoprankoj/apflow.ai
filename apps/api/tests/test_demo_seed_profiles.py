from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.services.demo_seed_service import CONFIRM_TEXT
from main import create_app


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous = _snapshot_settings()
    settings.auth_enabled = True
    settings.demo_mode = False
    settings.use_in_memory_repositories = True
    settings.ocr_provider = "mock"
    settings.priority_erp_mode = "mock"
    settings.priority_erp_enable_writes = False
    settings.allow_demo_reset = False
    settings.app_env = "local"
    _clear_dependency_caches()
    yield
    _restore_settings(previous)
    _clear_dependency_caches()


@pytest.fixture
def seed_enabled(auth_enabled) -> Iterator[None]:
    previous_app_env = settings.app_env
    previous_allow_demo_reset = settings.allow_demo_reset
    settings.app_env = "staging"
    settings.allow_demo_reset = True
    yield
    settings.app_env = previous_app_env
    settings.allow_demo_reset = previous_allow_demo_reset


def test_seed_profile_list_requires_auth(auth_enabled):
    response = TestClient(create_app()).get("/admin/demo/seed-profiles")

    assert response.status_code == 401


def test_viewer_cannot_list_or_run_seed_profiles(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    viewer = _create_member(client, "seed-viewer@example.com", "viewer")

    listed = client.get("/admin/demo/seed-profiles", headers=_auth_headers(viewer["token"]))
    seeded = client.post(
        "/admin/demo/seed-profile",
        headers=_auth_headers(viewer["token"]),
        json={
            "tenant_id": viewer["tenant_id"],
            "profile_key": "clean_minimal",
            "confirm_text": CONFIRM_TEXT,
        },
    )

    assert listed.status_code == 403
    assert seeded.status_code == 403


def test_owner_can_list_seed_profiles(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-list-owner@example.com")

    response = client.get("/admin/demo/seed-profiles", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    keys = {profile["key"] for profile in response.json()}
    assert {
        "clean_minimal",
        "ap_manager_demo",
        "vendor_self_service_demo",
        "priority_connector_demo",
        "compliance_demo",
        "analytics_rich_demo",
    }.issubset(keys)


def test_seed_profile_requires_allow_demo_reset(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-disabled@example.com")

    response = _run_seed(client, owner, "clean_minimal")

    assert response.status_code == 403
    assert response.json()["detail"] == "Demo seeding is disabled"


def test_seed_profile_is_blocked_in_production(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-production@example.com")
    settings.app_env = "production"
    settings.allow_demo_reset = True

    response = _run_seed(client, owner, "clean_minimal")

    assert response.status_code == 403
    assert response.json()["detail"] == "Demo seed profiles are disabled in production"


def test_seed_profile_requires_confirmation(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-confirm@example.com")

    response = client.post(
        "/admin/demo/seed-profile",
        headers=_auth_headers(owner["access_token"]),
        json={
            "tenant_id": owner["tenant"]["id"],
            "profile_key": "clean_minimal",
            "confirm_text": "RESET",
        },
    )

    assert response.status_code == 400
    assert CONFIRM_TEXT in response.json()["detail"]


def test_seed_profile_rejects_unknown_profile(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-unknown@example.com")

    response = _run_seed(client, owner, "unknown_profile")

    assert response.status_code == 400
    assert "Unknown demo seed profile" in response.json()["detail"]


def test_clean_minimal_seeds_baseline_and_audit(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-clean@example.com")
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])

    response = _run_seed(client, owner, "clean_minimal")
    invoices = client.get(f"/invoices?tenant_id={tenant_id}", headers=headers).json()
    audit_events = client.get(f"/invoices/audit-events?tenant_id={tenant_id}", headers=headers).json()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "seeded"
    assert body["created_counts"]["vendors"] >= 1
    assert body["created_counts"]["purchase_orders"] >= 1
    assert invoices == []
    assert any(event["action"] == "demo.seed_profile_completed" for event in audit_events)


def test_ap_manager_demo_creates_workflow_state_examples(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-ap-manager@example.com")
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])

    response = _run_seed(client, owner, "ap_manager_demo")
    invoices = client.get(f"/invoices?tenant_id={tenant_id}", headers=headers).json()
    tasks = client.get(f"/invoices/approval-tasks?tenant_id={tenant_id}", headers=headers).json()
    review_tasks = client.get(f"/review/tasks?tenant_id={tenant_id}", headers=headers).json()
    invoice_numbers = {invoice["canonical_invoice"]["invoice_number"] for invoice in invoices}
    task_statuses = {task["status"] for task in tasks}

    assert response.status_code == 200
    assert {"AP-DEMO-REVIEW-100", "AP-DEMO-DISCOUNT-200", "AP-DEMO-EXPORTED-300", "AP-DEMO-BLOCKED-400"}.issubset(invoice_numbers)
    assert {"pending", "approved", "blocked"}.issubset(task_statuses)
    assert len(review_tasks) == 1


def test_vendor_self_service_demo_returns_one_time_vendor_access_safely(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-vendor@example.com")
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])

    response = _run_seed(client, owner, "vendor_self_service_demo")
    payment_statuses = client.get(f"/payments/statuses?tenant_id={tenant_id}", headers=headers).json()

    assert response.status_code == 200
    body = response.json()
    assert body["created_counts"]["vendor_access"] == 1
    assert body["generated_vendor_links"]
    access = body["generated_vendor_links"][0]
    assert access["access_token"]
    assert "token_hash" not in access
    assert access["matching_invoice_count"] == 3
    assert {item["status"] for item in payment_statuses} >= {"scheduled", "paid", "disputed"}
    serialized = response.text
    assert "access_token_hash" not in serialized


def test_priority_connector_demo_keeps_priority_writes_disabled(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-priority@example.com")
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])

    response = _run_seed(client, owner, "priority_connector_demo")
    mapping = client.get(f"/erp/priority/mapping?tenant_id={tenant_id}", headers=headers)
    readiness = client.get("/ready/product", headers=headers).json()

    assert response.status_code == 200
    assert mapping.status_code == 200
    assert mapping.json()["mapping"]["vendors"]["entity_name"] == "SUPPLIERS"
    checks = {check["key"]: check for check in readiness["checks"]}
    assert checks["priority_writes_disabled"]["status"] == "pass"
    assert response.json()["created_counts"]["priority_imported_vendors"] == 1


def test_compliance_demo_creates_ready_and_warning_invoices(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-compliance@example.com")
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])

    response = _run_seed(client, owner, "compliance_demo")
    invoices = client.get(f"/invoices?tenant_id={tenant_id}", headers=headers).json()
    invoice_numbers = {invoice["canonical_invoice"]["invoice_number"] for invoice in invoices}

    assert response.status_code == 200
    assert {"COMP-GENERIC-READY", "COMP-MISSING-TAX", "COMP-VAT-WARNING"}.issubset(invoice_numbers)
    assert response.json()["warnings"]


def test_analytics_rich_demo_populates_activity_foundations(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-analytics@example.com")
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])

    response = _run_seed(client, owner, "analytics_rich_demo")
    analytics = client.get(f"/analytics/accuracy?tenant_id={tenant_id}", headers=headers)
    usage = client.get(f"/usage/summary?tenant_id={tenant_id}", headers=headers)
    notifications = client.get(f"/notifications/deliveries?tenant_id={tenant_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["created_counts"]["usage_events"] >= 9
    assert analytics.status_code == 200
    assert usage.status_code == 200
    assert notifications.status_code == 200
    assert notifications.json()
    assert usage.json()["usage_by_event_type"]["invoice_uploaded"] >= 1


def test_seed_profile_is_tenant_scoped(auth_enabled, seed_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "seed-tenant-a@example.com")
    owner_b = _register(client, "seed-tenant-b@example.com")
    headers_b = _auth_headers(owner_b["access_token"])
    tenant_b = owner_b["tenant"]["id"]

    b_seed = _run_seed(client, owner_b, "ap_manager_demo")
    a_seed = _run_seed(client, owner_a, "clean_minimal")
    b_invoices = client.get(f"/invoices?tenant_id={tenant_b}", headers=headers_b).json()

    assert b_seed.status_code == 200
    assert a_seed.status_code == 200
    assert {invoice["canonical_invoice"]["invoice_number"] for invoice in b_invoices}


def test_product_readiness_reflects_seed_profiles(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "seed-readiness@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    checks = {check["key"]: check for check in response.json()["checks"]}
    assert checks["demo_seed_profiles_available"]["status"] == "pass"
    assert checks["pilot_data_packs_available"]["status"] == "pass"
    assert checks["production_demo_reset_blocked"]["status"] == "pass"


def _run_seed(client: TestClient, owner: dict, profile_key: str):
    return client.post(
        "/admin/demo/seed-profile",
        headers=_auth_headers(owner["access_token"]),
        json={
            "tenant_id": owner["tenant"]["id"],
            "profile_key": profile_key,
            "confirm_text": CONFIRM_TEXT,
        },
    )


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


def _create_member(client: TestClient, email: str, role: str) -> dict:
    owner = _register(client, f"owner-{email}")
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
    return {"token": login.json()["access_token"], "tenant_id": owner["tenant"]["id"]}


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _snapshot_settings() -> dict:
    return {
        "app_env": settings.app_env,
        "allow_demo_reset": settings.allow_demo_reset,
        "auth_enabled": settings.auth_enabled,
        "demo_mode": settings.demo_mode,
        "use_in_memory_repositories": settings.use_in_memory_repositories,
        "ocr_provider": settings.ocr_provider,
        "priority_erp_mode": settings.priority_erp_mode,
        "priority_erp_enable_writes": settings.priority_erp_enable_writes,
    }


def _restore_settings(snapshot: dict) -> None:
    for key, value in snapshot.items():
        setattr(settings, key, value)


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
        dependencies.get_vendor_communication_agent,
        dependencies.get_payment_status_chatbot_agent,
        dependencies.get_auth_service,
    ):
        provider.cache_clear()
