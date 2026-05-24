from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import settings
from app.core.schemas import (
    ApprovalRoute,
    ApprovalTaskStatus,
    CanonicalInvoice,
    ERPOperation,
    ERPSyncLog,
    ERPSyncStatus,
    HumanReviewFieldIssue,
    HumanReviewStatus,
    HumanReviewTask,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    PaymentStatusSource,
    PaymentStatusValue,
    UserRole,
    VendorSafeStatus,
)
from app.core.vendor_portal import map_vendor_invoice_status
from main import create_app


@pytest.fixture(autouse=True)
def clear_dependency_caches():
    for provider in (
        dependencies.get_repository,
        dependencies.get_audit_agent,
        dependencies.get_monitoring_agent,
        dependencies.get_error_handler_agent,
        dependencies.get_vendor_communication_agent,
        dependencies.get_payment_status_chatbot_agent,
    ):
        provider.cache_clear()
    yield
    for provider in (
        dependencies.get_repository,
        dependencies.get_audit_agent,
        dependencies.get_monitoring_agent,
        dependencies.get_error_handler_agent,
        dependencies.get_vendor_communication_agent,
        dependencies.get_payment_status_chatbot_agent,
    ):
        provider.cache_clear()


@pytest.fixture
def auth_enabled() -> Iterator[None]:
    previous_auth_enabled = settings.auth_enabled
    settings.auth_enabled = True
    try:
        yield
    finally:
        settings.auth_enabled = previous_auth_enabled


def test_vendor_safe_status_mapping():
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Northstar Components")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-VENDOR-MAP")

    assert map_vendor_invoice_status(repository, tenant_id, invoice) == VendorSafeStatus.RECEIVED

    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=ApprovalRoute.MANAGER_APPROVAL,
        assigned_role="manager",
        status=ApprovalTaskStatus.PENDING,
        reason="Amount requires approval.",
    )
    assert map_vendor_invoice_status(repository, tenant_id, invoice) == VendorSafeStatus.UNDER_REVIEW

    blocked_invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-BLOCKED-MAP")
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=blocked_invoice.invoice_id,
        route=ApprovalRoute.BLOCKED,
        assigned_role="ap_admin",
        status=ApprovalTaskStatus.BLOCKED,
        reason="High-risk invoice requires AP review.",
    )
    assert map_vendor_invoice_status(repository, tenant_id, blocked_invoice) == VendorSafeStatus.UNDER_REVIEW

    rejected_invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-REJECTED-MAP")
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=rejected_invoice.invoice_id,
        route=ApprovalRoute.BLOCKED,
        assigned_role="ap_admin",
        status=ApprovalTaskStatus.REJECTED,
        reason="Rejected by AP reviewer.",
    )
    assert map_vendor_invoice_status(repository, tenant_id, rejected_invoice) == VendorSafeStatus.REJECTED

    repository.store_erp_sync_log(
        ERPSyncLog(
            tenant_id=tenant_id,
            adapter_type="priority",
            operation=ERPOperation.SYNC_PAYMENT_STATUS,
            status=ERPSyncStatus.SUCCESS,
            invoice_id=invoice.invoice_id,
            metadata={"payment_status": "paid"},
        )
    )
    assert map_vendor_invoice_status(repository, tenant_id, invoice) == VendorSafeStatus.PAID


def test_vendor_can_see_own_invoices_only_and_detail_hides_internal_fields():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor_a = repository.add_vendor(tenant_id, "Vendor A")
    vendor_b = repository.add_vendor(tenant_id, "Vendor B")
    own_invoice = _seed_invoice(repository, tenant_id, vendor_a.vendor_id, "INV-OWN")
    other_invoice = _seed_invoice(repository, tenant_id, vendor_b.vendor_id, "INV-OTHER")
    token = _vendor_token(client, tenant_id, vendor_a.vendor_id)

    listed = client.get(f"/vendor/invoices?tenant_id={tenant_id}", headers=_vendor_headers(token))
    own_detail = client.get(
        f"/vendor/invoices/{own_invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(token),
    )
    other_detail = client.get(
        f"/vendor/invoices/{other_invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(token),
    )

    assert listed.status_code == 200
    assert [item["invoice_number"] for item in listed.json()] == ["INV-OWN"]
    assert own_detail.status_code == 200
    assert "fraud_risk_result" not in own_detail.json()
    assert "audit_events" not in own_detail.json()
    assert "erp_sync_logs" not in own_detail.json()
    assert other_detail.status_code == 403


def test_internal_vendor_preview_for_blocked_invoice_is_safe():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Preview Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-PREVIEW")
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=ApprovalRoute.BLOCKED,
        assigned_role="ap_admin",
        status=ApprovalTaskStatus.BLOCKED,
        reason="Internal high-risk policy block.",
    )

    response = client.get(f"/vendor/preview/invoices/{invoice.invoice_id}?tenant_id={tenant_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "under_review"
    assert body["public_message"] == "This invoice is under AP review."
    assert "risk" not in body
    assert "audit_events" not in body


def test_vendor_message_submission_creates_notification_event():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Message Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-MSG")
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    response = client.post(
        "/vendor/messages",
        json={
            "tenant_id": str(tenant_id),
            "invoice_id": str(invoice.invoice_id),
            "sender_email": "vendor@example.com",
            "message": "Please confirm the expected payment date.",
        },
        headers=_vendor_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    notifications = repository.list_notification_events(tenant_id)
    assert notifications[-1].notification_type == "vendor_message_received"


def test_chatbot_answers_received_and_payment_status_questions():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Chat Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-CHAT")
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    received = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_id": str(invoice.invoice_id), "question": "Did you receive my invoice?"},
        headers=_vendor_headers(token),
    )
    repository.store_erp_sync_log(
        ERPSyncLog(
            tenant_id=tenant_id,
            adapter_type="priority",
            operation=ERPOperation.SYNC_PAYMENT_STATUS,
            status=ERPSyncStatus.SUCCESS,
            invoice_id=invoice.invoice_id,
            metadata={"payment_status": "scheduled_for_payment"},
        )
    )
    payment = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_number": "INV-CHAT", "question": "What is the payment status?"},
        headers=_vendor_headers(token),
    )

    assert received.status_code == 200
    assert received.json()["intent"] == "invoice_received"
    assert "INV-CHAT" in received.json()["answer"]
    assert payment.status_code == 200
    assert payment.json()["intent"] == "invoice_payment_status"
    assert payment.json()["status"] == "scheduled_for_payment"
    assert payment.json()["refused"] is False


def test_payment_chatbot_answers_scheduled_paid_pending_and_disputed_questions():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Payment Chat Vendor")
    scheduled_invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-SCHEDULED")
    paid_invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-PAID")
    pending_invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-PENDING")
    disputed_invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-DISPUTED")
    repository.upsert_payment_status(
        tenant_id,
        scheduled_invoice.invoice_id,
        status=PaymentStatusValue.SCHEDULED,
        source=PaymentStatusSource.MOCK,
        amount_due=117,
        amount_paid=0,
        currency="USD",
        scheduled_payment_date=datetime(2026, 6, 23, tzinfo=UTC),
        safe_vendor_message="Payment is scheduled by AP.",
        internal_note="internal scheduled note",
    )
    repository.upsert_payment_status(
        tenant_id,
        paid_invoice.invoice_id,
        status=PaymentStatusValue.PAID,
        source=PaymentStatusSource.MOCK,
        amount_due=117,
        amount_paid=117,
        currency="USD",
        paid_at=datetime(2026, 6, 24, tzinfo=UTC),
        safe_vendor_message="Payment has been marked as paid.",
        internal_note="internal paid note",
    )
    repository.upsert_payment_status(
        tenant_id,
        pending_invoice.invoice_id,
        status=PaymentStatusValue.PENDING,
        source=PaymentStatusSource.MOCK,
        amount_due=117,
        amount_paid=0,
        currency="USD",
        safe_vendor_message="Payment is pending AP processing.",
    )
    repository.upsert_payment_status(
        tenant_id,
        disputed_invoice.invoice_id,
        status=PaymentStatusValue.DISPUTED,
        source=PaymentStatusSource.MOCK,
        amount_due=117,
        amount_paid=0,
        currency="USD",
        safe_vendor_message="Payment is on hold while AP reviews a dispute.",
    )
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    scheduled = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_number": "INV-SCHEDULED", "question": "When is payment scheduled?"},
        headers=_vendor_headers(token),
    )
    paid = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_number": "INV-PAID", "question": "Has this invoice been paid?"},
        headers=_vendor_headers(token),
    )
    pending = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "question": "Which invoices are pending?"},
        headers=_vendor_headers(token),
    )
    disputed = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "question": "Do I have any disputed invoices?"},
        headers=_vendor_headers(token),
    )

    assert scheduled.status_code == 200
    assert scheduled.json()["intent"] == "invoice_due_or_scheduled_date"
    assert "Jun 23, 2026" in scheduled.json()["answer"]
    assert "internal scheduled note" not in scheduled.text
    assert paid.status_code == 200
    assert paid.json()["intent"] == "invoice_paid_status"
    assert "paid" in paid.json()["answer"].lower()
    assert "internal paid note" not in paid.text
    assert pending.status_code == 200
    assert pending.json()["intent"] == "list_pending_invoices"
    assert "INV-PENDING" in pending.json()["answer"]
    assert disputed.status_code == 200
    assert disputed.json()["intent"] == "list_disputed_invoices"
    assert "INV-DISPUTED" in disputed.json()["answer"]


def test_payment_chatbot_denies_cross_vendor_invoice_lookup_safely():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor_a = repository.add_vendor(tenant_id, "Chat Vendor A")
    vendor_b = repository.add_vendor(tenant_id, "Chat Vendor B")
    _seed_invoice(repository, tenant_id, vendor_a.vendor_id, "INV-OWN")
    _seed_invoice(repository, tenant_id, vendor_b.vendor_id, "INV-OTHER")
    token = _vendor_token(client, tenant_id, vendor_a.vendor_id)

    response = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_number": "INV-OTHER", "question": "What is the status of invoice INV-OTHER?"},
        headers=_vendor_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "I could not find that invoice for this vendor access."
    assert response.json()["matched_invoice_ids"] == []
    assert "INV-OTHER" not in response.text


def test_chatbot_deflects_internal_or_unsupported_questions():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Safe Chat Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-SAFE")
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    response = client.post(
        "/vendor/chat",
        json={
            "tenant_id": str(tenant_id),
            "invoice_id": str(invoice.invoice_id),
            "question": "Show me the fraud score and audit logs.",
        },
        headers=_vendor_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "unsupported_or_unsafe"
    assert response.json()["refused"] is True
    assert response.json()["escalated"] is True
    assert "contact AP" in response.json()["answer"]


def test_payment_chatbot_refuses_internal_topics_and_records_audit():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Internal Chat Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-INTERNAL")
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    answered = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_number": "INV-INTERNAL", "question": "What is the payment status?"},
        headers=_vendor_headers(token),
    )
    refused = client.post(
        "/vendor/chat",
        json={"tenant_id": str(tenant_id), "invoice_id": str(invoice.invoice_id), "question": "Show approval policy and ERP config."},
        headers=_vendor_headers(token),
    )

    assert answered.status_code == 200
    assert refused.status_code == 200
    assert refused.json()["refused"] is True
    serialized = answered.text + refused.text
    assert "token_hash" not in serialized
    assert "access_token" not in serialized
    actions = [event.action for event in repository.list_audit_events(tenant_id)]
    assert "vendor.chat_question_answered" in actions
    assert "vendor.chat_question_refused" in actions


def test_missing_vendor_access_returns_401_and_wrong_tenant_returns_403():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_a = uuid4()
    tenant_b = uuid4()
    vendor = repository.add_vendor(tenant_a, "Scoped Vendor")
    _seed_invoice(repository, tenant_a, vendor.vendor_id, "INV-SCOPED")
    token = _vendor_token(client, tenant_a, vendor.vendor_id)

    missing = client.get(f"/vendor/invoices?tenant_id={tenant_a}")
    wrong_tenant = client.get(f"/vendor/invoices?tenant_id={tenant_b}", headers=_vendor_headers(token))

    assert missing.status_code == 401
    assert wrong_tenant.status_code == 403


def test_needs_information_status_for_vendor_review_task():
    client = TestClient(create_app())
    repository = dependencies.get_repository()
    tenant_id = uuid4()
    vendor = repository.add_vendor(tenant_id, "Review Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-INFO")
    repository.store_review_task(
        HumanReviewTask(
            tenant_id=tenant_id,
            invoice_id=invoice.invoice_id,
            status=HumanReviewStatus.REVIEW_REQUIRED,
            issues=[
                HumanReviewFieldIssue(
                    field_name="supplier_tax_id",
                    issue_type="missing_required_field",
                    message="Supplier tax ID is required.",
                )
            ],
        )
    )
    token = _vendor_token(client, tenant_id, vendor.vendor_id)

    response = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "needs_information"
    assert response.json()["missing_information"] == ["supplier_tax_id"]


def test_admin_vendor_access_lifecycle_shows_raw_token_once_and_hides_hash(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-owner@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor = repository.add_vendor(tenant_id, "Lifecycle Vendor")
    headers = _auth_headers(owner["access_token"])

    created = client.post(
        "/vendor/accesses",
        json={
            "tenant_id": str(tenant_id),
            "vendor_id": str(vendor.vendor_id),
            "email": "vendor@example.com",
            "label": "Lifecycle portal access",
            "ttl_days": 7,
        },
        headers=headers,
    )
    listed = client.get(f"/vendor/accesses?tenant_id={tenant_id}", headers=headers)

    assert created.status_code == 200
    body = created.json()
    assert body["access_token"]
    assert body["token_prefix"]
    assert body["access_token"].startswith(body["token_prefix"])
    assert "token_hash" not in body
    assert "access_token_hash" not in body
    assert listed.status_code == 200
    assert listed.json()[0]["token_prefix"] == body["token_prefix"]
    assert "access_token" not in listed.json()[0]
    assert "access_token_hash" not in listed.json()[0]
    stored = repository.get_vendor_portal_access(tenant_id, UUID(body["id"]))
    assert stored.access_token_hash
    assert stored.access_token_hash != body["access_token"]


def test_vendor_access_link_and_supplier_name_matching_returns_invoices(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-superstore@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor = repository.add_vendor(tenant_id, "SuperStore")
    _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-SUPERSTORE", supplier_name="SuperStore")
    headers = _auth_headers(owner["access_token"])

    created = client.post(
        "/vendor/accesses",
        json={"tenant_id": str(tenant_id), "vendor_name": "SuperStore", "email": "ap@superstore.example"},
        headers=headers,
    )
    listed = client.get(
        f"/vendor/invoices?tenant_id={tenant_id}&access_token={created.json()['access_token']}",
    )

    assert created.status_code == 200
    assert created.json()["access_url"].startswith(f"{settings.public_app_url.rstrip('/')}/vendor?tenant_id={tenant_id}")
    assert created.json()["matching_invoice_count"] == 1
    assert listed.status_code == 200
    assert [invoice["invoice_number"] for invoice in listed.json()] == ["INV-SUPERSTORE"]


def test_vendor_access_normalized_supplier_name_matching_is_safe(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-normalized@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor = repository.add_vendor(tenant_id, "Super Store")
    other_vendor = repository.add_vendor(tenant_id, "Different Supplier")
    _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-NORMALIZED", supplier_name="SuperStore")
    _seed_invoice(repository, tenant_id, other_vendor.vendor_id, "INV-DIFFERENT", supplier_name="Different Supplier")
    headers = _auth_headers(owner["access_token"])

    created = client.post(
        "/vendor/accesses",
        json={"tenant_id": str(tenant_id), "vendor_name": "SuperStore", "email": "ap@superstore.example"},
        headers=headers,
    )
    listed = client.get(
        f"/vendor/invoices?tenant_id={tenant_id}&access_token={created.json()['access_token']}",
    )

    assert created.status_code == 200
    assert created.json()["matching_invoice_count"] == 1
    assert listed.status_code == 200
    assert [invoice["invoice_number"] for invoice in listed.json()] == ["INV-NORMALIZED"]


def test_vendor_access_zero_match_supplier_is_empty_but_valid(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-empty@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    headers = _auth_headers(owner["access_token"])

    created = client.post(
        "/vendor/accesses",
        json={"tenant_id": str(tenant_id), "vendor_name": "No Invoice Supplier", "email": "empty@example.com"},
        headers=headers,
    )
    listed = client.get(
        f"/vendor/invoices?tenant_id={tenant_id}&access_token={created.json()['access_token']}",
    )

    assert created.status_code == 200
    assert created.json()["matching_invoice_count"] == 0
    assert listed.status_code == 200
    assert listed.json() == []


def test_vendor_access_revoke_and_rotate(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-rotate@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor = repository.add_vendor(tenant_id, "Rotate Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-ROTATE")
    headers = _auth_headers(owner["access_token"])
    created = client.post(
        "/vendor/accesses",
        json={"tenant_id": str(tenant_id), "vendor_id": str(vendor.vendor_id), "email": "rotate@example.com"},
        headers=headers,
    ).json()
    old_token = created["access_token"]

    rotate = client.post(f"/vendor/accesses/{created['id']}/rotate?tenant_id={tenant_id}", headers=headers)
    old_after_rotate = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(old_token),
    )
    new_token = rotate.json()["access_token"]
    new_after_rotate = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(new_token),
    )
    revoke = client.post(
        f"/vendor/accesses/{rotate.json()['new_access']['id']}/revoke?tenant_id={tenant_id}",
        headers=headers,
    )
    new_after_revoke = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(new_token),
    )

    assert rotate.status_code == 200
    assert old_after_rotate.status_code == 403
    assert new_after_rotate.status_code == 200
    assert revoke.status_code == 200
    assert new_after_revoke.status_code == 403


def test_vendor_access_expired_token_denied_and_last_used_updates(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-expire@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor = repository.add_vendor(tenant_id, "Expire Vendor")
    invoice = _seed_invoice(repository, tenant_id, vendor.vendor_id, "INV-EXPIRE")
    headers = _auth_headers(owner["access_token"])
    expired = client.post(
        "/vendor/accesses",
        json={
            "tenant_id": str(tenant_id),
            "vendor_id": str(vendor.vendor_id),
            "email": "expired@example.com",
            "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        },
        headers=headers,
    ).json()
    active = client.post(
        "/vendor/accesses",
        json={"tenant_id": str(tenant_id), "vendor_id": str(vendor.vendor_id), "email": "active@example.com"},
        headers=headers,
    ).json()

    expired_response = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(expired["access_token"]),
    )
    active_response = client.get(
        f"/vendor/invoices/{invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(active["access_token"]),
    )
    listed = client.get(f"/vendor/accesses?tenant_id={tenant_id}", headers=headers).json()
    active_record = next(item for item in listed if item["id"] == active["id"])

    assert expired_response.status_code == 403
    assert active_response.status_code == 200
    assert active_record["last_used_at"] is not None


def test_vendor_access_is_vendor_scoped_and_payment_safe(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-scope@example.com")
    tenant_id = UUID(owner["tenant"]["id"])
    repository = dependencies.get_repository()
    vendor_a = repository.add_vendor(tenant_id, "Vendor Scope A")
    vendor_b = repository.add_vendor(tenant_id, "Vendor Scope B")
    own_invoice = _seed_invoice(repository, tenant_id, vendor_a.vendor_id, "INV-SCOPE-A")
    other_invoice = _seed_invoice(repository, tenant_id, vendor_b.vendor_id, "INV-SCOPE-B")
    repository.upsert_payment_status(
        tenant_id,
        own_invoice.invoice_id,
        status=PaymentStatusValue.SCHEDULED,
        source=PaymentStatusSource.MANUAL,
        amount_due=117,
        amount_paid=0,
        currency="USD",
        safe_vendor_message="Payment is scheduled by AP.",
        internal_note="Do not expose this internal note.",
        external_payment_reference="INTERNAL-REF-123",
    )
    headers = _auth_headers(owner["access_token"])
    created = client.post(
        "/vendor/accesses",
        json={"tenant_id": str(tenant_id), "vendor_id": str(vendor_a.vendor_id), "email": "scope@example.com"},
        headers=headers,
    ).json()

    own = client.get(
        f"/vendor/invoices/{own_invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(created["access_token"]),
    )
    other = client.get(
        f"/vendor/invoices/{other_invoice.invoice_id}?tenant_id={tenant_id}",
        headers=_vendor_headers(created["access_token"]),
    )

    assert own.status_code == 200
    assert other.status_code == 403
    serialized = str(own.json()).lower()
    assert "payment is scheduled by ap" in serialized
    assert "internal note" not in serialized
    assert "internal-ref-123" not in serialized
    assert "risk_score" not in serialized


def test_viewer_cannot_manage_vendor_access(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-viewer-owner@example.com")
    viewer = _create_member(client, owner, "vendor-access-viewer@example.com", UserRole.VIEWER)
    tenant_id = owner["tenant"]["id"]

    response = client.post(
        "/vendor/accesses",
        json={"tenant_id": tenant_id, "vendor_name": "Viewer Vendor", "email": "viewer@example.com"},
        headers=_auth_headers(viewer["token"]),
    )

    assert response.status_code == 403


def test_product_readiness_reflects_vendor_access_foundation(auth_enabled):
    client = TestClient(create_app())
    owner = _register(client, "vendor-access-readiness@example.com")

    response = client.get("/ready/product", headers=_auth_headers(owner["access_token"]))

    assert response.status_code == 200
    checks = {check["key"]: check for check in response.json()["checks"]}
    assert checks["vendor_access_lifecycle_available"]["status"] == "pass"
    assert checks["vendor_access_token_hashing_available"]["status"] == "pass"
    assert checks["vendor_access_expiry_revocation_available"]["status"] == "pass"


def _seed_invoice(repository, tenant_id, vendor_id, invoice_number, supplier_name="Northstar Components"):
    output = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number=invoice_number,
            supplier_name=supplier_name,
            supplier_tax_id="TAX-12345",
            invoice_date="2026-05-06",
            currency="USD",
            subtotal=100,
            tax_total=17,
            grand_total=117,
            line_items=[
                InvoiceLineItem(
                    description="Service fee",
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


def _vendor_token(client, tenant_id, vendor_id) -> str:
    response = client.post(
        "/vendor/access",
        json={"tenant_id": str(tenant_id), "vendor_id": str(vendor_id), "email": "vendor@example.com"},
    )
    assert response.status_code == 200
    assert "access_token_hash" not in response.json()
    return response.json()["access_token"]


def _vendor_headers(token: str) -> dict[str, str]:
    return {"X-Vendor-Access-Token": token}


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


def _create_member(client: TestClient, owner: dict, email: str, role: UserRole) -> dict:
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
