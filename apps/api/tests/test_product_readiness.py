from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
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
    settings.priority_erp_read_only_fetch_enabled = False
    _clear_dependency_caches()
    yield
    _restore_settings(previous)
    _clear_dependency_caches()


def test_product_readiness_requires_auth(auth_enabled):
    response = TestClient(create_app()).get("/ready/product")

    assert response.status_code == 401


def test_owner_can_read_product_readiness(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "readiness-owner@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert {"demo_ready", "pilot_ready", "production_ready", "checks"}.issubset(body)
    assert body["demo_ready"]["status"] == "ready"
    assert body["pilot_ready"]["status"] == "not_ready"
    assert body["production_ready"]["status"] == "not_ready"
    assert "Readiness does not enable production" in body["message"]


def test_viewer_cannot_read_product_readiness(auth_enabled):
    client = TestClient(create_app())
    viewer = _create_member(client, "readiness-viewer@example.com", "viewer")

    response = client.get("/ready/product", headers=_auth_headers(viewer["token"]))

    assert response.status_code == 403


def test_staging_config_does_not_claim_production_ready(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "staging-readiness@example.com")
    settings.app_env = "staging"
    settings.demo_mode = True

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["production_ready"]["status"] == "not_ready"
    assert "Production environment" in body["production_ready"]["blockers"]
    assert "Demo mode disabled for production" in body["production_ready"]["blockers"]


def test_priority_writes_disabled_is_demo_safety_pass(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "priority-safe@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    checks = {item["key"]: item for item in response.json()["checks"]}
    assert checks["priority_writes_disabled"]["status"] == "pass"
    assert checks["priority_live_write_not_enabled"]["status"] == "pass"


def test_payment_and_vendor_gaps_are_pilot_or_production_blockers(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "pilot-blockers@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    body = response.json()
    checks = {item["key"]: item for item in body["checks"]}
    assert checks["production_access_hardening"]["status"] == "fail"
    assert checks["payment_status_foundation_available"]["status"] == "pass"
    assert checks["real_payment_sync_configured"]["status"] == "fail"
    assert checks["payment_status_sync_ready"]["status"] == "fail"
    assert checks["vendor_access_lifecycle_available"]["status"] == "pass"
    assert checks["vendor_access_token_hashing_available"]["status"] == "pass"
    assert checks["vendor_access_expiry_revocation_available"]["status"] == "pass"
    assert checks["production_vendor_access_ready"]["status"] == "warning"
    assert "Production access hardening" in body["pilot_ready"]["blockers"]
    assert "Payment status sync" in body["pilot_ready"]["blockers"]


def test_product_readiness_response_does_not_expose_secrets(auth_enabled):
    previous = _snapshot_settings()
    settings.auth_secret_key = "super-secret-auth-key-for-readiness-tests"
    settings.ocr_space_api_key = "secret-ocr-key"
    settings.database_url = "postgresql+psycopg://apflow:secret-password@postgres:5432/apflow"
    settings.priority_erp_username = "priority-user"
    settings.priority_erp_password = "priority-password"
    settings.priority_erp_api_key = "priority-api-key"
    try:
        client = TestClient(create_app())
        owner = _register(client, "secret-safe@example.com")

        response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))
    finally:
        _restore_settings(previous)

    assert response.status_code == 200
    serialized = response.text
    assert "super-secret-auth-key-for-readiness-tests" not in serialized
    assert "secret-ocr-key" not in serialized
    assert "secret-password" not in serialized
    assert "priority-user" not in serialized
    assert "priority-password" not in serialized
    assert "priority-api-key" not in serialized


def test_existing_ready_endpoint_shape_is_unchanged(auth_enabled):
    response = TestClient(create_app()).get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert "checks" in body
    assert "demo_ready" not in body
    assert "pilot_ready" not in body
    assert "production_ready" not in body


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
    return {
        "token": login.json()["access_token"],
        "tenant_id": owner["tenant"]["id"],
        "user": created.json()["user"],
    }


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _snapshot_settings() -> dict:
    return {
        "app_env": settings.app_env,
        "auth_enabled": settings.auth_enabled,
        "demo_mode": settings.demo_mode,
        "use_in_memory_repositories": settings.use_in_memory_repositories,
        "ocr_provider": settings.ocr_provider,
        "ocr_space_api_key": settings.ocr_space_api_key,
        "auth_secret_key": settings.auth_secret_key,
        "database_url": settings.database_url,
        "priority_erp_mode": settings.priority_erp_mode,
        "priority_erp_enable_writes": settings.priority_erp_enable_writes,
        "priority_erp_read_only_fetch_enabled": settings.priority_erp_read_only_fetch_enabled,
        "priority_erp_username": settings.priority_erp_username,
        "priority_erp_password": settings.priority_erp_password,
        "priority_erp_api_key": settings.priority_erp_api_key,
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
        dependencies.get_auth_service,
    ):
        provider.cache_clear()
