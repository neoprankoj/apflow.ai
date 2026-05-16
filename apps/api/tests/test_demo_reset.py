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
    _create_demo_operational_data(client, owner)

    response = client.post("/admin/demo/reset", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reset"
    assert body["tenant_id"] == owner["tenant"]["id"]
    assert body["message"] == "Demo data reset successfully."
    assert body["cleared"]["invoices"] >= 1
    assert body["cleared"]["notification_events"] >= 1
    assert "notifications" not in body["cleared"]
    assert body["invoice_number"] is None
    assert body["workflow_status"] == "clean"
    assert body["seed_mode"] == "clean"
    assert body["erp_export_ready"] is False
    assert body["vendor_count"] >= 1
    assert body["purchase_order_count"] >= 1
    assert body["approval_task_count"] == 0
    assert body["notification_count"] == 0


def test_demo_reset_clears_operational_data_and_preserves_users(auth_enabled, staging_demo_reset):
    client = TestClient(create_app())
    owner = _register(client, "demo-reset-clear@example.com")
    _create_demo_operational_data(client, owner)
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])

    response = client.post("/admin/demo/reset", headers=headers)

    assert response.status_code == 200
    assert client.get(f"/invoices?tenant_id={tenant_id}", headers=headers).json() == []
    assert client.get(f"/invoices/approval-tasks?tenant_id={tenant_id}", headers=headers).json() == []
    assert client.get(f"/invoices/notification-events?tenant_id={tenant_id}", headers=headers).json() == []
    assert client.get(f"/invoices/workflows?tenant_id={tenant_id}", headers=headers).json() == []
    assert client.get(f"/review/tasks?tenant_id={tenant_id}", headers=headers).json() == []
    assert client.get(f"/documents/invoices?tenant_id={tenant_id}", headers=headers).json() == []
    users = client.get("/admin/users", headers=headers).json()
    assert [record["user"]["email"] for record in users] == ["demo-reset-clear@example.com"]


def test_demo_reset_succeeds_with_no_operational_data(auth_enabled, staging_demo_reset):
    client = TestClient(create_app())
    owner = _register(client, "demo-reset-empty@example.com")

    response = client.post("/admin/demo/reset", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reset"
    assert body["cleared"]["invoices"] == 0
    assert body["cleared"]["notification_events"] == 0


def test_demo_reset_is_repeatable_and_login_still_works(auth_enabled, staging_demo_reset):
    client = TestClient(create_app())
    owner = _register(client, "demo-reset-repeat@example.com")
    headers = _auth_headers(owner["access_token"])
    _create_demo_operational_data(client, owner)

    first = client.post("/admin/demo/reset", headers=headers)
    second = client.post("/admin/demo/reset", headers=headers)
    login = client.post(
        "/auth/login",
        json={"email": "demo-reset-repeat@example.com", "password": "password-123"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["cleared"]["invoices"] == 0
    assert login.status_code == 200


def test_demo_reset_does_not_call_ocr_provider(auth_enabled, staging_demo_reset):
    def fail_if_ocr_agent_requested():
        raise AssertionError("demo reset should not request OCR/extraction dependencies")

    dependencies.get_invoice_extraction_agent.cache_clear()
    app = create_app()
    app.dependency_overrides[dependencies.get_invoice_extraction_agent] = fail_if_ocr_agent_requested
    client = TestClient(app)
    owner = _register(client, "demo-reset-no-ocr@example.com")

    response = client.post("/admin/demo/reset", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    assert response.json()["workflow_status"] == "clean"


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


def _create_demo_operational_data(client: TestClient, owner: dict) -> None:
    tenant_id = owner["tenant"]["id"]
    headers = _auth_headers(owner["access_token"])
    pipeline = client.post(
        "/invoices/full-mock-pipeline",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "source": "upload",
            "file_url": "mock://demo/reset-before.pdf",
            "metadata": {
                "sender_email": "demo-ap@apflow.local",
                "original_filename": "reset-before.pdf",
                "mime_type": "application/pdf",
            },
            "content": (
                "invoice_number=INV-BEFORE-RESET supplier_name=Northstar Components "
                "supplier_tax_id=TAX-12345 subtotal=1000 tax_total=170 grand_total=1170 "
                "currency=USD invoice_date=2026-05-09 po_number=PO-100"
            ),
        },
    )
    assert pipeline.status_code == 200
    assert pipeline.json()["invoice"] is not None
    upload = client.post(
        "/documents/invoices/upload",
        headers=headers,
        data={"tenant_id": tenant_id},
        files={"file": ("review-before-reset.pdf", b"invoice_number=LOW confidence_invoice_number=0.4", "application/pdf")},
    )
    assert upload.status_code == 200
    process = client.post(
        f"/documents/invoices/{upload.json()['document']['document_id']}/process",
        headers=headers,
        json={"tenant_id": tenant_id},
    )
    assert process.status_code == 200
    assert client.get(f"/invoices?tenant_id={tenant_id}", headers=headers).json()
    assert client.get(f"/review/tasks?tenant_id={tenant_id}", headers=headers).json()


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
