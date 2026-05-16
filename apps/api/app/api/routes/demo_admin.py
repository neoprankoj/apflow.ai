from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import (
    get_audit_agent,
    get_repository,
    require_permission,
)
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    ApprovalRoute,
    ApprovalTaskStatus,
    AuditEventInput,
    CanonicalInvoice,
    CurrentUserContext,
    HumanReviewFieldIssue,
    HumanReviewStatus,
    HumanReviewTask,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    NotificationType,
    Permission,
    PurchaseOrderLine,
    WorkflowState,
    WorkflowStatus,
)

router = APIRouter()


@router.post("/demo/reset")
def reset_demo_data(
    seed_mode: str = Query(default="clean", pattern="^(clean|approval_ready|review_required|inbox_demo|all)$"),
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> dict:
    if settings.app_env != "staging" or not settings.allow_demo_reset:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    tenant_id = context.tenant.id
    cleared = repository.clear_demo_operational_data(tenant_id)
    repository.ensure_phase3_fixtures(tenant_id)
    seeded = _seed_demo_mode(repository, tenant_id, seed_mode)

    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="admin.demo_reset",
            entity_type="tenant",
            entity_id=tenant_id,
            metadata={
                "seed_mode": seed_mode,
                "workflow_status": seeded["workflow_status"],
            },
        )
    )
    return {
        "status": "reset",
        "message": "Demo data reset successfully.",
        "cleared": cleared,
        "tenant_id": tenant_id,
        "tenant_name": context.tenant.name,
        "user_email": context.user.email,
        "invoice_id": seeded["invoice_id"],
        "invoice_number": seeded["invoice_number"],
        "workflow_status": seeded["workflow_status"],
        "seed_mode": seed_mode,
        "erp_export_ready": seeded["erp_export_ready"],
        "vendor_count": len(repository.list_vendors(tenant_id)),
        "purchase_order_count": len(repository.list_purchase_orders(tenant_id)),
        "approval_task_count": len(repository.list_approval_tasks(tenant_id)),
        "notification_count": len(repository.list_notification_events(tenant_id)),
        "reset_at": datetime.now(UTC).isoformat(),
    }


def _seed_demo_mode(repository: InMemoryAPRepository, tenant_id, seed_mode: str) -> dict:
    if seed_mode == "clean":
        return {
            "invoice_id": None,
            "invoice_number": None,
            "workflow_status": "clean",
            "erp_export_ready": False,
        }

    approval_ready = None
    if seed_mode in {"approval_ready", "all"}:
        approval_ready = _seed_approval_ready_demo(repository, tenant_id)
    if seed_mode in {"review_required", "all"}:
        _seed_review_required_demo(repository, tenant_id)
    if seed_mode == "inbox_demo":
        return _seed_inbox_demo(repository, tenant_id)

    if seed_mode == "review_required":
        return {
            "invoice_id": None,
            "invoice_number": None,
            "workflow_status": "review_required",
            "erp_export_ready": False,
        }
    return approval_ready


def _seed_demo_vendor_and_po(repository: InMemoryAPRepository, tenant_id):
    vendor = next(
        (record for record in repository.list_vendors(tenant_id) if record.name == "APFlow Demo Supplier Ltd."),
        None,
    )
    if vendor is None:
        vendor = repository.add_vendor(
            tenant_id=tenant_id,
            name="APFlow Demo Supplier Ltd.",
            tax_id="DEMO-TAX-0001",
        )
    if repository.get_purchase_order_by_number(tenant_id, "PO-DEMO-1001") is None:
        repository.add_purchase_order(
            tenant_id=tenant_id,
            po_number="PO-DEMO-1001",
            vendor_id=vendor.vendor_id,
            total_amount=1170,
            lines=[PurchaseOrderLine(description="Demo services", quantity=1, unit_price=1000, total=1170)],
        )
    return vendor


def _seed_approval_ready_demo(repository: InMemoryAPRepository, tenant_id) -> dict:
    vendor = _seed_demo_vendor_and_po(repository, tenant_id)
    invoice = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number="DEMO-INVOICE-1001",
            supplier_name="APFlow Demo Supplier Ltd.",
            supplier_tax_id="DEMO-TAX-0001",
            invoice_date="2026-05-16",
            due_date="2026-06-15",
            currency="USD",
            subtotal=1000,
            tax_total=170,
            grand_total=1170,
            po_number="PO-DEMO-1001",
            line_items=[
                InvoiceLineItem(
                    description="Demo services",
                    quantity=1,
                    unit_price=1000,
                    tax_amount=170,
                    total=1170,
                    po_number="PO-DEMO-1001",
                )
            ],
        ),
        file_checksum="demo-approval-ready",
    )
    repository.store_invoice(invoice)
    repository.update_invoice_vendor(tenant_id, invoice.invoice_id, vendor.vendor_id)
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=ApprovalRoute.MANAGER_APPROVAL,
        assigned_role="finance_manager",
        status=ApprovalTaskStatus.PENDING,
        reason="Deterministic demo approval-ready invoice.",
    )
    repository.store_notification_event(
        tenant_id=tenant_id,
        notification_id=uuid4(),
        invoice_id=invoice.invoice_id,
        notification_type=NotificationType.APPROVAL_REQUIRED,
        recipient_role="finance_manager",
        status="sent",
        channel="mock",
        payload={"scenario": "approval_ready"},
    )
    repository.store_workflow_state(
        WorkflowState(
            tenant_id=tenant_id,
            workflow_id=uuid4(),
            state="approval_ready",
            status=WorkflowStatus.COMPLETED,
            current_agent="ApprovalRoutingAgent",
        )
    )
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_number": invoice.canonical_invoice.invoice_number,
        "workflow_status": "approval_ready",
        "erp_export_ready": True,
    }


def _seed_review_required_demo(repository: InMemoryAPRepository, tenant_id) -> None:
    repository.store_review_task(
        HumanReviewTask(
            tenant_id=tenant_id,
            status=HumanReviewStatus.REVIEW_REQUIRED,
            issues=[
                HumanReviewFieldIssue(
                    field_name="invoice_number",
                    issue_type="missing_required_field",
                    message="Demo OCR output omitted invoice number.",
                ),
                HumanReviewFieldIssue(
                    field_name="invoice_date",
                    issue_type="low_confidence",
                    message="Demo OCR date is weak and needs review.",
                    confidence=0.55,
                ),
            ],
            history=[{"action": "seeded", "scenario": "review_required"}],
        )
    )
    repository.store_workflow_state(
        WorkflowState(
            tenant_id=tenant_id,
            workflow_id=uuid4(),
            state="review_required",
            status=WorkflowStatus.WAITING_FOR_HUMAN,
            current_agent="HumanReviewAgent",
        )
    )


def _seed_inbox_demo(repository: InMemoryAPRepository, tenant_id) -> dict:
    approval_ready = _seed_demo_invoice(
        repository,
        tenant_id,
        invoice_number="DEMO-INBOX-READY",
        file_checksum="demo-inbox-ready",
        route=ApprovalRoute.MANAGER_APPROVAL,
        status=ApprovalTaskStatus.APPROVED,
        reason="Approved demo invoice is ready for ERP export.",
        po_number="PO-DEMO-1001",
        notification_type=NotificationType.APPROVAL_DECISION_RECORDED,
        notification_payload={"scenario": "approval_ready"},
        workflow_state="approval_ready",
    )
    _seed_demo_invoice(
        repository,
        tenant_id,
        invoice_number="DEMO-INBOX-BLOCKED",
        file_checksum="demo-inbox-blocked",
        route=ApprovalRoute.BLOCKED,
        status=ApprovalTaskStatus.BLOCKED,
        reason="Invoice blocked by risk policy.",
        po_number=None,
        notification_type=NotificationType.INVOICE_BLOCKED,
        notification_payload={"scenario": "blocked_high_risk", "risk_level": "high"},
        workflow_state="blocked",
    )
    _seed_demo_invoice(
        repository,
        tenant_id,
        invoice_number="DEMO-INBOX-HOLD",
        file_checksum="demo-inbox-hold",
        route=ApprovalRoute.BLOCKED,
        status=ApprovalTaskStatus.ON_HOLD,
        reason="Invoice kept on hold by authorized reviewer.",
        po_number=None,
        notification_type=NotificationType.APPROVAL_DECISION_RECORDED,
        notification_payload={"scenario": "on_hold"},
        workflow_state="blocked",
    )
    _seed_demo_invoice(
        repository,
        tenant_id,
        invoice_number="DEMO-INBOX-REJECTED",
        file_checksum="demo-inbox-rejected",
        route=ApprovalRoute.BLOCKED,
        status=ApprovalTaskStatus.REJECTED,
        reason="Invoice rejected by authorized reviewer.",
        po_number=None,
        notification_type=NotificationType.APPROVAL_DECISION_RECORDED,
        notification_payload={"scenario": "rejected"},
        workflow_state="rejected",
    )
    _seed_demo_invoice(
        repository,
        tenant_id,
        invoice_number="DEMO-INBOX-DUPLICATE",
        file_checksum="demo-inbox-duplicate-a",
        route=ApprovalRoute.AP_REVIEW,
        status=ApprovalTaskStatus.PENDING,
        reason="PO exception requires AP review.",
        po_number=None,
        notification_type=NotificationType.DUPLICATE_DETECTED,
        notification_payload={"scenario": "duplicate_like", "duplicate_status": "likely_duplicate"},
        workflow_state="approval_required",
    )
    _seed_demo_invoice(
        repository,
        tenant_id,
        invoice_number="DEMO-INBOX-DUPLICATE",
        file_checksum="demo-inbox-duplicate-b",
        route=ApprovalRoute.AP_REVIEW,
        status=ApprovalTaskStatus.PENDING,
        reason="PO exception requires AP review.",
        po_number=None,
        notification_type=NotificationType.DUPLICATE_DETECTED,
        notification_payload={"scenario": "duplicate_like", "duplicate_status": "likely_duplicate"},
        workflow_state="approval_required",
    )
    _seed_review_required_demo(repository, tenant_id)
    return approval_ready


def _seed_demo_invoice(
    repository: InMemoryAPRepository,
    tenant_id,
    *,
    invoice_number: str,
    file_checksum: str,
    route: ApprovalRoute,
    status: ApprovalTaskStatus,
    reason: str,
    po_number: str | None,
    notification_type: NotificationType,
    notification_payload: dict,
    workflow_state: str,
) -> dict:
    vendor = _seed_demo_vendor_and_po(repository, tenant_id)
    invoice = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        canonical_invoice=CanonicalInvoice(
            invoice_number=invoice_number,
            supplier_name="APFlow Demo Supplier Ltd.",
            supplier_tax_id="DEMO-TAX-0001",
            invoice_date="2026-05-16",
            due_date="2026-06-15",
            currency="USD",
            subtotal=1000,
            tax_total=170,
            grand_total=1170,
            po_number=po_number,
            line_items=[
                InvoiceLineItem(
                    description="Demo services",
                    quantity=1,
                    unit_price=1000,
                    tax_amount=170,
                    total=1170,
                    po_number=po_number,
                )
            ],
        ),
        file_checksum=file_checksum,
    )
    repository.store_invoice(invoice)
    repository.update_invoice_vendor(tenant_id, invoice.invoice_id, vendor.vendor_id)
    repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice.invoice_id,
        route=route,
        assigned_role="ap_admin" if route == ApprovalRoute.BLOCKED else "finance_manager",
        status=status,
        reason=reason,
    )
    repository.store_notification_event(
        tenant_id=tenant_id,
        notification_id=uuid4(),
        invoice_id=invoice.invoice_id,
        notification_type=notification_type,
        recipient_role="ap_admin",
        status="sent",
        channel="mock",
        payload=notification_payload,
    )
    repository.store_workflow_state(
        WorkflowState(
            tenant_id=tenant_id,
            workflow_id=uuid4(),
            state=workflow_state,
            status=WorkflowStatus.COMPLETED,
            current_agent="ApprovalRoutingAgent",
        )
    )
    return {
        "invoice_id": invoice.invoice_id,
        "invoice_number": invoice.canonical_invoice.invoice_number,
        "workflow_status": workflow_state,
        "erp_export_ready": status in {ApprovalTaskStatus.APPROVED, ApprovalTaskStatus.AUTO_APPROVED},
    }
