from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.core.schemas import HumanReviewFieldIssue, HumanReviewStatus, HumanReviewTask
from main import create_app


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


@pytest.fixture
def demo_mode() -> Iterator[None]:
    previous_auth_enabled = settings.auth_enabled
    previous_demo_mode = settings.demo_mode
    settings.auth_enabled = False
    settings.demo_mode = True
    _clear_dependency_caches()
    yield
    settings.auth_enabled = previous_auth_enabled
    settings.demo_mode = previous_demo_mode
    _clear_dependency_caches()


def test_register_demo_tenant_login_and_me(auth_enabled):
    client = TestClient(create_app())
    registered = _register(client, "owner1@example.com")

    login = client.post(
        "/auth/login",
        json={"email": "owner1@example.com", "password": "password-123"},
    )
    me = client.get("/auth/me", headers=_auth_headers(registered["access_token"]))

    assert registered["role"] == "owner"
    assert login.status_code == 200
    assert login.json()["access_token"]
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner1@example.com"
    assert "invoice:approve" in me.json()["permissions"]


def test_login_failure_returns_401(auth_enabled):
    client = TestClient(create_app())
    _register(client, "owner2@example.com")

    response = client.post(
        "/auth/login",
        json={"email": "owner2@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_missing_auth_on_protected_endpoint_returns_401(auth_enabled):
    client = TestClient(create_app())

    response = client.post(
        "/erp/config",
        json={"tenant_id": "11111111-1111-1111-1111-111111111111", "adapter_type": "priority"},
    )

    assert response.status_code == 401


def test_tenant_membership_enforced_for_query_tenant(auth_enabled):
    client = TestClient(create_app())
    tenant_a = _register(client, "tenant-a@example.com")
    tenant_b = _register(client, "tenant-b@example.com")

    response = client.get(
        f"/invoices?tenant_id={tenant_b['tenant']['id']}",
        headers=_auth_headers(tenant_a["access_token"]),
    )

    assert response.status_code == 403


def test_admin_user_management_and_role_permission_checks(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "admin-owner@example.com")
    owner_headers = _auth_headers(owner["access_token"])

    created = client.post(
        "/admin/users",
        json={
            "email": "viewer@example.com",
            "full_name": "Viewer User",
            "password": "password-123",
            "role": "viewer",
        },
        headers=owner_headers,
    )
    listed = client.get("/admin/users", headers=owner_headers)
    role_updated = client.patch(
        f"/admin/users/{created.json()['user']['id']}/role",
        json={"role": "approver"},
        headers=owner_headers,
    )
    deactivated = client.delete(f"/admin/users/{created.json()['user']['id']}", headers=owner_headers)

    assert created.status_code == 200
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert role_updated.json()["role"] == "approver"
    assert deactivated.json()["is_active"] is False


def test_erp_config_blocked_for_unauthorized_role(auth_enabled):
    client = TestClient(create_app())
    viewer = _create_member(client, "erp-viewer@example.com", "viewer")

    response = client.post(
        "/erp/config",
        json={"tenant_id": viewer["tenant_id"], "adapter_type": "priority"},
        headers=_auth_headers(viewer["token"]),
    )

    assert response.status_code == 403


def test_review_correction_and_audit_logs_blocked_for_viewer(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "review-owner@example.com")
    viewer = _create_member(client, "review-viewer@example.com", "viewer", owner)
    repository = dependencies.get_repository()
    task = repository.store_review_task(
        HumanReviewTask(
            tenant_id=owner["tenant"]["id"],
            status=HumanReviewStatus.REVIEW_REQUIRED,
            issues=[
                HumanReviewFieldIssue(
                    field_name="invoice_number",
                    issue_type="low_confidence",
                    message="Needs review.",
                    confidence=0.4,
                )
            ],
        )
    )

    correction = client.post(
        f"/review/tasks/{task.task_id}/corrections",
        json={"tenant_id": owner["tenant"]["id"], "corrections": {"invoice_number": "INV-1"}},
        headers=_auth_headers(viewer["token"]),
    )
    audit_logs = client.get(
        f"/invoices/audit-events?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(viewer["token"]),
    )

    assert correction.status_code == 403
    assert audit_logs.status_code == 403


def test_demo_mode_preserves_existing_unprotected_flow(demo_mode):
    client = TestClient(create_app())

    response = client.post(
        "/erp/test-connection",
        json={"tenant_id": "33333333-3333-3333-3333-333333333333", "adapter_type": "priority"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"


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


def _create_member(
    client: TestClient,
    email: str,
    role: str,
    owner: dict | None = None,
) -> dict:
    owner = owner or _register(client, f"owner-{email}")
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
    return {
        "token": login.json()["access_token"],
        "tenant_id": owner["tenant"]["id"],
        "user": created.json()["user"],
    }


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
    ):
        provider.cache_clear()
