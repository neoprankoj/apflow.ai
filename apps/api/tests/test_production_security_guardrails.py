from collections.abc import Iterator
from uuid import UUID, uuid4
import json

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.schemas import (
    ActorType,
    ApprovalRoute,
    ApprovalTaskStatus,
    AuditEventInput,
    CanonicalInvoice,
    ERPOperation,
    ERPSyncLog,
    ERPSyncRequest,
    ERPSyncStatus,
    HumanReviewFieldIssue,
    HumanReviewStatus,
    HumanReviewTask,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    PaymentStatusSource,
    PaymentStatusValue,
    PriorityImportRequest,
    PriorityMappingConfig,
    PriorityMappingValidationRequest,
)
from app.core.config import settings
from main import create_app


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous_auth_enabled = settings.auth_enabled
    previous_demo_mode = settings.demo_mode
    previous_app_env = settings.app_env
    previous_allow_demo_reset = settings.allow_demo_reset
    previous_auth_secret = settings.auth_secret_key
    settings.auth_enabled = True
    settings.demo_mode = False
    settings.app_env = "local"
    settings.allow_demo_reset = False
    settings.auth_secret_key = "production-security-tests-secret-32-chars"
    _clear_dependency_caches()
    yield
    settings.auth_enabled = previous_auth_enabled
    settings.demo_mode = previous_demo_mode
    settings.app_env = previous_app_env
    settings.allow_demo_reset = previous_allow_demo_reset
    settings.auth_secret_key = previous_auth_secret
    _clear_dependency_caches()


def test_protected_routes_reject_unauthenticated_requests(auth_enabled):
    client = TestClient(create_app())
    tenant_id = uuid4()
    invoice_id = uuid4()
    payloads = [
        ("GET", "/invoices", None),
        ("GET", "/invoices/workflows", None),
        ("GET", "/invoices/approval-tasks", None),
        ("GET", "/invoices/audit-events", None),
        ("GET", "/review/tasks", None),
        ("GET", "/payments/statuses", None),
        ("GET", "/payments/summary", None),
        ("GET", "/admin/users", None),
        ("GET", "/erp/priority/mapping", None),
        ("GET", "/erp/priority/readiness", None),
        ("GET", "/ready/product", None),
        ("POST", f"/invoices/{invoice_id}/approval-decision", {"tenant_id": str(tenant_id), "action": "approve"}),
        ("POST", "/erp/export-invoice", ERPSyncRequest(tenant_id=tenant_id, invoice_id=invoice_id).model_dump(mode="json")),
        ("PUT", "/erp/priority/mapping", PriorityMappingValidationRequest(tenant_id=tenant_id, mapping=PriorityMappingConfig()).model_dump(mode="json")),
        ("POST", "/erp/priority/import", PriorityImportRequest(tenant_id=tenant_id, selected_external_ids=["SUP-1001"], confirmation="IMPORT_SELECTED").model_dump(mode="json")),
    ]

    for method, path, json_body in payloads:
        response = client.request(method, path, json=json_body)
        assert response.status_code in {401, 403}, f"{method} {path} returned {response.status_code}: {response.text}"


def test_viewer_role_cannot_approve_export_admin_or_configure(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "security-owner@example.com")
    viewer = _create_member(client, owner, "security-viewer@example.com", "viewer")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    invoice = _seed_invoice(repository, tenant_id, "SEC-INV-1")
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=ApprovalRoute.BLOCKED,
        assigned_role="ap_admin",
        status=ApprovalTaskStatus.BLOCKED,
        reason="Blocked for security test.",
    )
    headers = _auth_headers(viewer["token"])

    approval = client.post(
        f"/invoices/{invoice.invoice_id}/approval-decision",
        json={"tenant_id": str(tenant_id), "action": "approve"},
        headers=headers,
    )
    export = client.post(
        "/erp/export-invoice",
        json=ERPSyncRequest(tenant_id=tenant_id, invoice_id=invoice.invoice_id).model_dump(mode="json"),
        headers=headers,
    )
    configure = client.put(
        "/erp/priority/mapping",
        json=PriorityMappingValidationRequest(tenant_id=tenant_id, mapping=PriorityMappingConfig()).model_dump(mode="json"),
        headers=headers,
    )
    priority_import = client.post(
        "/erp/priority/import",
        json=PriorityImportRequest(tenant_id=tenant_id, selected_external_ids=["SUP-1001"], confirmation="IMPORT_SELECTED").model_dump(mode="json"),
        headers=headers,
    )
    payment_update = client.patch(
        f"/payments/statuses/{uuid4()}?tenant_id={tenant_id}",
        json={"status": "paid"},
        headers=headers,
    )
    admin_users = client.get("/admin/users", headers=headers)

    assert approval.status_code == 403
    assert export.status_code == 403
    assert configure.status_code == 403
    assert priority_import.status_code == 403
    assert payment_update.status_code == 403
    assert admin_users.status_code == 403


def test_approver_can_approve_but_cannot_admin_or_configure_erp(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "approver-owner@example.com")
    approver = _create_member(client, owner, "security-approver@example.com", "approver")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    invoice = _seed_invoice(repository, tenant_id, "SEC-INV-2")
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=ApprovalRoute.BLOCKED,
        assigned_role="ap_admin",
        status=ApprovalTaskStatus.BLOCKED,
        reason="Blocked for approver test.",
    )
    headers = _auth_headers(approver["token"])

    approval = client.post(
        f"/invoices/{invoice.invoice_id}/approval-decision",
        json={"tenant_id": str(tenant_id), "action": "approve"},
        headers=headers,
    )
    configure = client.put(
        "/erp/priority/mapping",
        json=PriorityMappingValidationRequest(tenant_id=tenant_id, mapping=PriorityMappingConfig()).model_dump(mode="json"),
        headers=headers,
    )
    admin_users = client.get("/admin/users", headers=headers)

    assert approval.status_code == 200
    assert approval.json()["approval_status"] == "approved"
    assert configure.status_code == 403
    assert admin_users.status_code == 403


def test_tenant_a_cannot_read_or_configure_tenant_b_resources(auth_enabled):
    client = TestClient(create_app())
    tenant_a = _register(client, "tenant-a-security@example.com")
    tenant_b = _register(client, "tenant-b-security@example.com")
    repository = dependencies.get_repository()
    tenant_b_id = UUID(tenant_b["tenant"]["id"])
    tenant_b_invoice = _seed_invoice(repository, tenant_b_id, "TENANT-B-INV")
    repository.upsert_payment_status(
        tenant_b_id,
        tenant_b_invoice.invoice_id,
        status=PaymentStatusValue.SCHEDULED,
        source=PaymentStatusSource.MOCK,
    )
    repository.store_review_task(
        HumanReviewTask(
            tenant_id=tenant_b_id,
            status=HumanReviewStatus.REVIEW_REQUIRED,
            issues=[HumanReviewFieldIssue(field_name="invoice_number", issue_type="low_confidence", message="Needs review.")],
        )
    )
    headers_a = _auth_headers(tenant_a["access_token"])
    tenant_b_query = f"tenant_id={tenant_b_id}"

    denied_reads = [
        f"/invoices?{tenant_b_query}",
        f"/invoices/workflows?{tenant_b_query}",
        f"/invoices/approval-tasks?{tenant_b_query}",
        f"/invoices/audit-events?{tenant_b_query}",
        f"/invoices/notification-events?{tenant_b_query}",
        f"/review/tasks?{tenant_b_query}",
        f"/payments/statuses?{tenant_b_query}",
        f"/payments/summary?{tenant_b_query}",
        f"/erp/priority/mapping?{tenant_b_query}",
        f"/erp/priority/imported/vendors?{tenant_b_query}",
        f"/erp/priority/imported/purchase-orders?{tenant_b_query}",
    ]

    for path in denied_reads:
        response = client.get(path, headers=headers_a)
        assert response.status_code == 403, f"{path} returned {response.status_code}: {response.text}"

    body_denied = client.post(
        "/erp/priority/import-plan",
        json={"tenant_id": str(tenant_b_id), "kind": "vendors"},
        headers=headers_a,
    )
    assert body_denied.status_code == 403

    own_invoices = client.get(f"/invoices?tenant_id={tenant_a['tenant']['id']}", headers=headers_a)
    tenant_b_invoices = client.get(f"/invoices?tenant_id={tenant_b_id}", headers=_auth_headers(tenant_b["access_token"]))
    assert own_invoices.status_code == 200
    assert "TENANT-B-INV" not in json.dumps(own_invoices.json())
    assert "TENANT-B-INV" in json.dumps(tenant_b_invoices.json())


def test_vendor_safe_response_does_not_expose_internal_metadata(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-safe-owner@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor = repository.add_vendor(tenant_id, "Vendor Safe Inc.")
    invoice = _seed_invoice(repository, tenant_id, "SAFE-INV-1", vendor_id=vendor.vendor_id)
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=ApprovalRoute.BLOCKED,
        assigned_role="ap_admin",
        status=ApprovalTaskStatus.BLOCKED,
        reason="Internal high-risk policy block.",
    )
    repository.store_erp_sync_log(
        ERPSyncLog(
            tenant_id=tenant_id,
            adapter_type="priority",
            operation=ERPOperation.EXPORT_INVOICE,
            status=ERPSyncStatus.FAILED,
            invoice_id=invoice.invoice_id,
            metadata={"adapter_config": "internal", "fraud_score": 99},
        )
    )
    repository.store_audit_event(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id="internal-user@example.com",
            action="invoice.risk_scored",
            entity_type="invoice",
            entity_id=invoice.invoice_id,
            metadata={"risk_score": 99, "risk_reason": "internal policy", "approval_policy": "blocked"},
        ),
        uuid4(),
    )
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    detail = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers={"X-Vendor-Access-Token": token},
    )

    assert detail.status_code == 200
    serialized = json.dumps(detail.json()).lower()
    forbidden = [
        "fraud_score",
        "risk_score",
        "risk_reason",
        "approval_policy",
        "audit",
        "metadata",
        "adapter_config",
        "token_hash",
        "access_token",
        "internal-user@example.com",
    ]
    for key in forbidden:
        assert key not in serialized
    assert detail.json()["status"] == "under_review"


def test_demo_reset_blocks_unauthenticated_and_production_even_if_flag_mutated(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "demo-reset-prod-owner@example.com")
    unauthenticated = client.post("/admin/demo/reset")

    previous_env = settings.app_env
    previous_reset = settings.allow_demo_reset
    settings.app_env = "production"
    settings.allow_demo_reset = True
    try:
        production = client.post("/admin/demo/reset", headers=_auth_headers(owner["access_token"]))
    finally:
        settings.app_env = previous_env
        settings.allow_demo_reset = previous_reset

    assert unauthenticated.status_code == 401
    assert production.status_code == 403
    assert production.json()["detail"] == "Demo reset is disabled"


def test_product_readiness_reflects_security_guardrails(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "readiness-security-owner@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    checks = {check["key"]: check for check in response.json()["checks"]}
    assert checks["tenant_isolation_tests_documented"]["status"] == "pass"
    assert checks["vendor_safe_protections_documented"]["status"] == "pass"
    assert checks["demo_reset_disabled_for_production"]["status"] == "pass"
    assert checks["auth_required_for_production"]["status"] == "pass"
    assert checks["jwt_secret_non_default"]["status"] == "pass"


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


def _seed_invoice(repository, tenant_id, invoice_number: str, vendor_id=None):
    tenant_id = UUID(str(tenant_id))
    if vendor_id is None:
        vendor_id = repository.add_vendor(tenant_id, "Security Vendor").vendor_id
    output = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number=invoice_number,
            supplier_name="Security Vendor",
            supplier_tax_id="SEC-TAX",
            invoice_date="2026-05-20",
            currency="USD",
            subtotal=100,
            tax_total=17,
            grand_total=117,
            line_items=[
                InvoiceLineItem(
                    description="Security service",
                    quantity=1,
                    unit_price=100,
                    tax_amount=17,
                    total=117,
                )
            ],
        ),
    )
    repository.store_invoice(output)
    repository.update_invoice_vendor(tenant_id, output.invoice_id, vendor_id)
    return repository.get_invoice(tenant_id, output.invoice_id)


def _vendor_token(client: TestClient, tenant_id, vendor_id) -> str:
    response = client.post(
        "/vendor/access",
        json={"tenant_id": str(tenant_id), "vendor_id": str(vendor_id), "email": "vendor@example.com"},
    )
    assert response.status_code == 200
    assert "access_token_hash" not in response.json()
    return response.json()["access_token"]


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
        dependencies.get_vendor_communication_agent,
        dependencies.get_payment_status_chatbot_agent,
        dependencies.get_erp_connector_agent,
        dependencies.get_auth_service,
    ):
        provider.cache_clear()
