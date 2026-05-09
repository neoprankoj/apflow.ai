from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import dependencies
from app.core.config import Settings, settings
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
def staging_demo_reset() -> Iterator[None]:
    previous_app_env = settings.app_env
    previous_allow_demo_reset = settings.allow_demo_reset
    settings.app_env = "staging"
    settings.allow_demo_reset = True
    _clear_dependency_caches()
    yield
    settings.app_env = previous_app_env
    settings.allow_demo_reset = previous_allow_demo_reset
    _clear_dependency_caches()


def test_demo_reset_disabled_outside_staging(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "demo-reset-disabled@example.com")

    response = client.post("/admin/demo/reset", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 403


def test_demo_reset_requires_admin_or_owner(auth_enabled, staging_demo_reset):
    client = TestClient(create_app())
    viewer = _create_member(client, "demo-reset-viewer@example.com", "viewer")

    response = client.post("/admin/demo/reset", headers=_auth_headers(viewer["token"]))

    assert response.status_code == 403


def test_demo_reset_creates_demo_records_for_owner(auth_enabled, staging_demo_reset):
    client = TestClient(create_app())
    owner = _register(client, "demo-reset-owner@example.com")

    response = client.post("/admin/demo/reset", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == owner["tenant"]["id"]
    assert body["invoice_number"].startswith("INV-DEMO-")
    assert body["workflow_status"] == "approval_ready"
    assert body["erp_export_ready"] is True
    assert body["vendor_count"] >= 1
    assert body["purchase_order_count"] >= 1
    assert body["approval_task_count"] >= 1
    assert body["notification_count"] >= 1


def test_production_config_rejects_demo_reset():
    with pytest.raises(ValidationError, match="ALLOW_DEMO_RESET"):
        Settings(
            app_env="production",
            public_app_url="https://apflow.example.com",
            api_public_url="https://api.apflow.example.com",
            cors_allowed_origins="https://apflow.example.com",
            auth_enabled=True,
            demo_mode=False,
            allow_demo_reset=True,
            auth_secret_key="production-secret-key-change-me-32-chars",
            minio_root_user="apflow-minio",
            minio_root_password="apflow-minio-password",
            database_url="postgresql+psycopg://apflow:secret@postgres:5432/apflow",
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


def _clear_dependency_caches() -> None:
    for provider in (
        dependencies.get_repository,
        dependencies.get_audit_agent,
        dependencies.get_monitoring_agent,
        dependencies.get_error_handler_agent,
        dependencies.get_tenant_security_agent,
        dependencies.get_invoice_ingestion_agent,
        dependencies.get_invoice_extraction_agent,
        dependencies.get_human_review_agent,
        dependencies.get_invoice_normalization_agent,
        dependencies.get_supplier_identity_agent,
        dependencies.get_invoice_validation_agent,
        dependencies.get_duplicate_detection_agent,
        dependencies.get_purchase_order_matching_agent,
        dependencies.get_fraud_risk_scoring_agent,
        dependencies.get_approval_routing_agent,
        dependencies.get_notification_agent,
        dependencies.get_auth_service,
    ):
        provider.cache_clear()
