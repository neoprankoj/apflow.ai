from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.core.schemas import (
    ApprovalRoute,
    ApprovalTaskStatus,
    CanonicalInvoice,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
)
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


def test_authorized_owner_can_approve_blocked_invoice_and_emit_events(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "approval-owner@example.com")
    repository = dependencies.get_repository()
    invoice_id = _seed_blocked_invoice(repository, owner["tenant"]["id"])

    response = client.post(
        f"/invoices/{invoice_id}/approval-decision",
        json={"tenant_id": owner["tenant"]["id"], "action": "approve"},
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"
    assert response.json()["workflow_status"] == "approval_ready"
    assert response.json()["erp_export_ready"] is True
    tenant_id = UUID(owner["tenant"]["id"])
    assert repository.get_latest_approval_task(tenant_id, invoice_id).status == ApprovalTaskStatus.APPROVED
    assert repository.list_notification_events(tenant_id)[-1].notification_type == "approval_decision_recorded"
    assert repository.list_audit_events(tenant_id)[-2].action == "invoice.approval_approve"


def test_unauthorized_viewer_cannot_approve_blocked_invoice(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "approval-admin@example.com")
    viewer = _create_member(client, owner, "approval-viewer@example.com", "viewer")
    repository = dependencies.get_repository()
    invoice_id = _seed_blocked_invoice(repository, owner["tenant"]["id"])

    response = client.post(
        f"/invoices/{invoice_id}/approval-decision",
        json={"tenant_id": owner["tenant"]["id"], "action": "approve"},
        headers=_auth_headers(viewer["token"]),
    )

    assert response.status_code == 403
    assert repository.get_latest_approval_task(UUID(owner["tenant"]["id"]), invoice_id).status == ApprovalTaskStatus.BLOCKED


def test_rejected_invoice_remains_non_exportable_with_reason(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "reject-owner@example.com")
    repository = dependencies.get_repository()
    invoice_id = _seed_blocked_invoice(repository, owner["tenant"]["id"])

    response = client.post(
        f"/invoices/{invoice_id}/approval-decision",
        json={
            "tenant_id": owner["tenant"]["id"],
            "action": "reject",
            "reason": "Duplicate confirmed by AP.",
        },
        headers=_auth_headers(owner["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"
    assert response.json()["workflow_status"] == "rejected"
    assert response.json()["erp_export_ready"] is False
    assert response.json()["blocker_reason"] == "Duplicate confirmed by AP."


def _seed_blocked_invoice(repository, tenant_id):
    tenant_id = UUID(str(tenant_id))
    vendor = repository.add_vendor(tenant_id, "Blocked Vendor")
    output = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number=f"INV-BLOCKED-{uuid4()}",
            supplier_name="Blocked Vendor",
            invoice_date="2026-05-16",
            currency="USD",
            subtotal=100,
            tax_total=17,
            grand_total=117,
            line_items=[
                InvoiceLineItem(
                    description="Blocked service",
                    quantity=1,
                    unit_price=100,
                    tax_amount=17,
                    total=117,
                )
            ],
        ),
    )
    repository.store_invoice(output)
    repository.update_invoice_vendor(tenant_id, output.invoice_id, vendor.vendor_id)
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=output.invoice_id,
        route=ApprovalRoute.BLOCKED,
        assigned_role="ap_admin",
        status=ApprovalTaskStatus.BLOCKED,
        reason="High-risk invoice requires review.",
    )
    return output.invoice_id


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
    return {"token": login.json()["access_token"]}


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
