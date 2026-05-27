from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from main import create_app


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous = {
        "auth_enabled": settings.auth_enabled,
        "demo_mode": settings.demo_mode,
        "use_in_memory_repositories": settings.use_in_memory_repositories,
        "ocr_provider": settings.ocr_provider,
        "notification_default_provider": settings.notification_default_provider,
        "notification_real_delivery_enabled": settings.notification_real_delivery_enabled,
        "email_from_address": settings.email_from_address,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_username": settings.smtp_username,
        "smtp_password": settings.smtp_password,
        "slack_webhook_url": settings.slack_webhook_url,
        "teams_webhook_url": settings.teams_webhook_url,
    }
    settings.auth_enabled = True
    settings.demo_mode = False
    settings.use_in_memory_repositories = True
    settings.ocr_provider = "mock"
    settings.notification_default_provider = "mock"
    settings.notification_real_delivery_enabled = False
    settings.email_from_address = ""
    settings.smtp_host = ""
    settings.smtp_port = ""
    settings.smtp_username = ""
    settings.smtp_password = ""
    settings.slack_webhook_url = ""
    settings.teams_webhook_url = ""
    _clear_dependency_caches()
    yield
    for key, value in previous.items():
        setattr(settings, key, value)
    _clear_dependency_caches()


def test_provider_list_returns_safe_placeholder_statuses(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "notifications-provider@example.com")

    response = client.get(
        f"/notifications/providers?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    providers = {item["channel"]: item for item in response.json()}
    assert providers["mock"]["configured"] is True
    assert providers["mock"]["enabled"] is True
    assert providers["email"]["configured"] is False
    assert providers["slack"]["configured"] is False
    assert providers["teams"]["configured"] is False
    assert "secret" not in response.text.casefold()
    assert "webhook" not in response.text.casefold()


def test_notification_readiness_requires_auth(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "notifications-readiness-auth@example.com")

    response = client.get(f"/notifications/readiness?tenant_id={owner['tenant']['id']}")

    assert response.status_code == 401


def test_notification_readiness_reports_mock_safe_and_real_missing(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "notifications-readiness@example.com")

    response = client.get(
        f"/notifications/readiness?tenant_id={owner['tenant']['id']}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    providers = {item["provider"]: item for item in body["providers"]}
    assert body["default_provider"] == "mock"
    assert body["real_delivery_enabled"] is False
    assert providers["mock"]["status"] == "mock_only"
    assert providers["mock"]["safe_to_test"] is True
    assert providers["email"]["configured"] is False
    assert providers["slack"]["configured"] is False
    assert providers["teams"]["configured"] is False
    assert providers["email"]["can_send_real_messages"] is False
    assert "SMTP_HOST" in providers["email"]["missing_requirements"]
    assert "SLACK_WEBHOOK_URL" in providers["slack"]["missing_requirements"]
    assert "TEAMS_WEBHOOK_URL" in providers["teams"]["missing_requirements"]


def test_real_delivery_disabled_blocks_partially_configured_provider(auth_enabled):
    previous = settings.slack_webhook_url
    settings.slack_webhook_url = "https://hooks.slack.example/secret-value"
    try:
        client = TestClient(create_app())
        owner = _register(client, "notifications-readiness-blocked@example.com")

        response = client.get(
            f"/notifications/readiness?tenant_id={owner['tenant']['id']}",
            headers=_auth_headers(owner["access_token"]),
        )
    finally:
        settings.slack_webhook_url = previous

    assert response.status_code == 200
    providers = {item["provider"]: item for item in response.json()["providers"]}
    assert providers["slack"]["configured"] is True
    assert providers["slack"]["enabled"] is False
    assert providers["slack"]["status"] == "blocked"
    assert providers["slack"]["can_send_real_messages"] is False
    assert "NOTIFICATION_REAL_DELIVERY_ENABLED=true" in providers["slack"]["missing_requirements"]


def test_notification_readiness_does_not_expose_provider_secrets(auth_enabled):
    previous = {
        "notification_real_delivery_enabled": settings.notification_real_delivery_enabled,
        "email_from_address": settings.email_from_address,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_username": settings.smtp_username,
        "smtp_password": settings.smtp_password,
        "slack_webhook_url": settings.slack_webhook_url,
        "teams_webhook_url": settings.teams_webhook_url,
    }
    settings.notification_real_delivery_enabled = True
    settings.email_from_address = "apflow@example.com"
    settings.smtp_host = "smtp.secret.example"
    settings.smtp_port = "587"
    settings.smtp_username = "smtp-user-secret"
    settings.smtp_password = "smtp-password-secret"
    settings.slack_webhook_url = "https://hooks.slack.example/secret-webhook"
    settings.teams_webhook_url = "https://outlook.office.example/secret-webhook"
    try:
        client = TestClient(create_app())
        owner = _register(client, "notifications-readiness-secrets@example.com")

        response = client.get(
            f"/notifications/readiness?tenant_id={owner['tenant']['id']}",
            headers=_auth_headers(owner["access_token"]),
        )
    finally:
        for key, value in previous.items():
            setattr(settings, key, value)

    assert response.status_code == 200
    serialized = response.text
    assert "smtp-password-secret" not in serialized
    assert "smtp-user-secret" not in serialized
    assert "secret-webhook" not in serialized
    assert "hooks.slack.example" not in serialized
    assert "outlook.office.example" not in serialized


def test_mock_provider_test_records_delivery_and_audit_event(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "notifications-mock@example.com")
    tenant_id = owner["tenant"]["id"]
    repository = dependencies.get_repository()

    response = client.post(
        "/notifications/test",
        json={
            "tenant_id": tenant_id,
            "channel": "mock",
            "recipient_label": "AP Manager",
            "recipient_address": "manager@example.local",
            "subject": "Approval reminder",
            "message": "Please review invoice INV-100.",
        },
        headers=_auth_headers(owner["access_token"]),
    )
    deliveries = client.get(
        f"/notifications/deliveries?tenant_id={tenant_id}",
        headers=_auth_headers(owner["access_token"]),
    )
    summary = client.get(
        f"/notifications/summary?tenant_id={tenant_id}",
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert response.json()["channel"] == "mock"
    assert response.json()["recipient_address_redacted"] == "ma***@example.local"
    assert deliveries.status_code == 200
    assert len(deliveries.json()) == 1
    assert summary.status_code == 200
    assert summary.json()["sent"] == 1
    audit_actions = [event.action for event in repository.list_audit_events(owner_tenant_uuid(owner))]
    assert "notification.test_sent" in audit_actions
    assert "notification.delivery_recorded" in audit_actions


def test_unconfigured_placeholders_return_safe_disabled_delivery(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "notifications-placeholder@example.com")

    for channel in ("email", "slack", "teams"):
        response = client.post(
            "/notifications/test",
            json={
                "tenant_id": owner["tenant"]["id"],
                "channel": channel,
                "recipient_label": "Approver",
                "recipient_address": "approver@example.local",
                "subject": "Provider test",
                "message": "Provider placeholder test.",
            },
            headers=_auth_headers(owner["access_token"]),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "disabled"
        assert "not configured" in body["reason"]
        assert "approver@example.local" not in response.text


def test_viewer_cannot_send_test_notification_but_can_read(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "notifications-owner@example.com")
    viewer = _create_member(client, owner, "notifications-viewer@example.com", "viewer")
    tenant_id = owner["tenant"]["id"]

    read_response = client.get(
        f"/notifications/providers?tenant_id={tenant_id}",
        headers=_auth_headers(viewer["token"]),
    )
    send_response = client.post(
        "/notifications/test",
        json={"tenant_id": tenant_id, "channel": "mock"},
        headers=_auth_headers(viewer["token"]),
    )

    assert read_response.status_code == 200
    assert send_response.status_code == 403


def test_unauthenticated_and_cross_tenant_access_are_denied(auth_enabled):
    client = TestClient(create_app())
    owner_a = _register(client, "notifications-a@example.com")
    owner_b = _register(client, "notifications-b@example.com")

    unauthenticated = client.get(f"/notifications/providers?tenant_id={owner_a['tenant']['id']}")
    cross_tenant = client.get(
        f"/notifications/deliveries?tenant_id={owner_a['tenant']['id']}",
        headers=_auth_headers(owner_b["access_token"]),
    )

    assert unauthenticated.status_code == 401
    assert cross_tenant.status_code == 403


def test_notification_responses_do_not_expose_secrets(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "notifications-secret@example.com")

    response = client.post(
        "/notifications/test",
        json={
            "tenant_id": owner["tenant"]["id"],
            "channel": "mock",
            "recipient_label": "Secret test",
            "recipient_address": "secret@example.local",
            "subject": "Secret safety",
            "message": "Do not include webhook URLs or provider keys in metadata.",
        },
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    serialized = response.text.casefold()
    assert "secret@example.local" not in serialized
    assert "token_hash" not in serialized
    assert "api_key" not in serialized
    assert "authorization" not in serialized


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


def owner_tenant_uuid(owner: dict):
    from uuid import UUID

    return UUID(owner["tenant"]["id"])


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
