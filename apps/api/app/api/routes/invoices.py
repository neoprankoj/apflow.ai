from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agents.data.invoice_extraction_agent import InvoiceExtractionAgent
from app.agents.data.invoice_ingestion_agent import InvoiceIngestionAgent
from app.agents.data.invoice_normalization_agent import InvoiceNormalizationAgent
from app.agents.interface.human_review_agent import HumanReviewAgent
from app.agents.interface.notification_agent import NotificationAgent
from app.agents.logic.approval_routing_agent import ApprovalRoutingAgent
from app.agents.logic.duplicate_detection_agent import DuplicateDetectionAgent
from app.agents.logic.fraud_risk_scoring_agent import FraudRiskScoringAgent
from app.agents.logic.invoice_validation_agent import InvoiceValidationAgent
from app.agents.logic.purchase_order_matching_agent import PurchaseOrderMatchingAgent
from app.agents.logic.supplier_identity_agent import SupplierIdentityAgent
from app.api.dependencies import (
    get_audit_agent,
    get_approval_routing_agent,
    get_duplicate_detection_agent,
    get_fraud_risk_scoring_agent,
    get_human_review_agent,
    get_invoice_extraction_agent,
    get_invoice_ingestion_agent,
    get_invoice_normalization_agent,
    get_invoice_validation_agent,
    get_notification_agent,
    get_monitoring_agent,
    get_purchase_order_matching_agent,
    get_repository,
    get_supplier_identity_agent,
    require_permission,
    resolve_tenant_id,
)
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    ApprovalDecisionAction,
    ApprovalDecisionRequest,
    ApprovalDecisionResult,
    ApprovalRoute,
    ApprovalRoutingInput,
    ApprovalTaskStatus,
    AuditEventInput,
    CurrentUserContext,
    DuplicateDetectionInput,
    DuplicateStatus,
    FraudRiskScoringInput,
    InvoiceExtractionInput,
    InvoiceIngestionInput,
    InvoiceNormalizationInput,
    InvoiceValidationInput,
    InvoiceValidationStatus,
    MetricEventInput,
    NotificationInput,
    NotificationType,
    POMatchStatus,
    Permission,
    PurchaseOrderMatchingInput,
    RiskLevel,
    SupplierIdentityInput,
    UsageEventSource,
    UsageEventType,
    WorkflowState,
)
from app.services.usage_metering_service import UsageMeteringService

router = APIRouter()


@router.post("/mock-pipeline")
def run_mock_invoice_pipeline(
    payload: InvoiceIngestionInput,
    repository: InMemoryAPRepository = Depends(get_repository),
    ingestion_agent: InvoiceIngestionAgent = Depends(get_invoice_ingestion_agent),
    extraction_agent: InvoiceExtractionAgent = Depends(get_invoice_extraction_agent),
    normalization_agent: InvoiceNormalizationAgent = Depends(get_invoice_normalization_agent),
    supplier_identity_agent: SupplierIdentityAgent = Depends(get_supplier_identity_agent),
    validation_agent: InvoiceValidationAgent = Depends(get_invoice_validation_agent),
    duplicate_detection_agent: DuplicateDetectionAgent = Depends(get_duplicate_detection_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> dict:
    _enforce_body_tenant(payload.tenant_id, context)
    if not repository.list_vendors(payload.tenant_id):
        repository.add_vendor(
            tenant_id=payload.tenant_id,
            name="Northstar Components",
            tax_id="TAX-12345",
        )

    raw_invoice = ingestion_agent.ingest(payload)
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw_invoice.raw_invoice_id,
            tenant_id=raw_invoice.tenant_id,
            storage_url=raw_invoice.storage_url,
            mime_type=raw_invoice.mime_type,
            correlation_id=payload.correlation_id,
        )
    )
    normalized = normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw_invoice.raw_invoice_id,
            tenant_id=raw_invoice.tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            confidence=extraction.confidence,
            file_checksum=raw_invoice.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )
    supplier = supplier_identity_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=normalized.canonical_invoice.supplier_name,
            supplier_tax_id=normalized.canonical_invoice.supplier_tax_id,
            correlation_id=payload.correlation_id,
        )
    )
    validation = validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            canonical_invoice=normalized.canonical_invoice,
            vendor_id=supplier.vendor_id,
            correlation_id=payload.correlation_id,
        )
    )
    duplicate = duplicate_detection_agent.detect(
        DuplicateDetectionInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_number=normalized.canonical_invoice.invoice_number,
            invoice_date=normalized.canonical_invoice.invoice_date,
            grand_total=normalized.canonical_invoice.grand_total,
            file_checksum=normalized.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )

    return {
        "raw_invoice": raw_invoice,
        "extraction": extraction,
        "normalized": normalized,
        "supplier": supplier,
        "validation": validation,
        "duplicate": duplicate,
    }


@router.post("/full-mock-pipeline")
def run_full_mock_invoice_pipeline(
    payload: InvoiceIngestionInput,
    repository: InMemoryAPRepository = Depends(get_repository),
    ingestion_agent: InvoiceIngestionAgent = Depends(get_invoice_ingestion_agent),
    extraction_agent: InvoiceExtractionAgent = Depends(get_invoice_extraction_agent),
    normalization_agent: InvoiceNormalizationAgent = Depends(get_invoice_normalization_agent),
    supplier_identity_agent: SupplierIdentityAgent = Depends(get_supplier_identity_agent),
    validation_agent: InvoiceValidationAgent = Depends(get_invoice_validation_agent),
    duplicate_detection_agent: DuplicateDetectionAgent = Depends(get_duplicate_detection_agent),
    po_matching_agent: PurchaseOrderMatchingAgent = Depends(get_purchase_order_matching_agent),
    fraud_risk_agent: FraudRiskScoringAgent = Depends(get_fraud_risk_scoring_agent),
    approval_routing_agent: ApprovalRoutingAgent = Depends(get_approval_routing_agent),
    notification_agent: NotificationAgent = Depends(get_notification_agent),
    review_agent: HumanReviewAgent = Depends(get_human_review_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> dict:
    _enforce_body_tenant(payload.tenant_id, context)
    repository.ensure_phase3_fixtures(payload.tenant_id)

    raw_invoice = ingestion_agent.ingest(payload)
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw_invoice.raw_invoice_id,
            tenant_id=raw_invoice.tenant_id,
            storage_url=raw_invoice.storage_url,
            mime_type=raw_invoice.mime_type,
            correlation_id=payload.correlation_id,
        )
    )
    review_task = (
        review_agent.inspect_extraction(
            extraction.ocr_result,
            raw_invoice_id=raw_invoice.raw_invoice_id,
        )
        if extraction.ocr_result is not None
        else None
    )
    review_tasks = [review_task] if review_task is not None and review_task.status != "not_required" else []
    if review_tasks:
        return {
            "invoice": None,
            "validation_result": None,
            "duplicate_result": None,
            "po_match_result": None,
            "fraud_risk_result": None,
            "approval_result": None,
            "notifications": [],
            "workflow_status": "review_required",
            "erp_export_ready": False,
            "ocr_result": extraction.ocr_result,
            "confidence_summary": extraction.confidence_summary,
            "review_status": review_task.status,
            "review_tasks": review_tasks,
        }

    normalized = normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw_invoice.raw_invoice_id,
            tenant_id=raw_invoice.tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            confidence=extraction.confidence,
            file_checksum=raw_invoice.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )
    supplier = supplier_identity_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=normalized.canonical_invoice.supplier_name,
            supplier_tax_id=normalized.canonical_invoice.supplier_tax_id,
            correlation_id=payload.correlation_id,
        )
    )
    validation = validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            canonical_invoice=normalized.canonical_invoice,
            vendor_id=supplier.vendor_id,
            correlation_id=payload.correlation_id,
        )
    )
    duplicate = duplicate_detection_agent.detect(
        DuplicateDetectionInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_number=normalized.canonical_invoice.invoice_number,
            invoice_date=normalized.canonical_invoice.invoice_date,
            grand_total=normalized.canonical_invoice.grand_total,
            file_checksum=normalized.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )
    invoice = normalized.canonical_invoice

    po_match = po_matching_agent.match(
        PurchaseOrderMatchingInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            po_number=invoice.po_number,
            invoice_lines=invoice.line_items,
            invoice_total=invoice.grand_total,
            currency=invoice.currency,
            correlation_id=payload.correlation_id,
        )
    )
    fraud_risk = fraud_risk_agent.score(
        FraudRiskScoringInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_total=invoice.grand_total,
            duplicate_result=duplicate,
            supplier_result=supplier,
            po_match_result=po_match,
            validation_result=validation,
            correlation_id=payload.correlation_id,
        )
    )
    approval = approval_routing_agent.route(
        ApprovalRoutingInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            amount=invoice.grand_total,
            match_status=po_match.match_status,
            risk_level=fraud_risk.risk_level,
            validation_status=validation.validation_status,
            duplicate_status=duplicate.status,
            correlation_id=payload.correlation_id,
        )
    )
    notifications = _send_pipeline_notifications(
        tenant_id=normalized.tenant_id,
        invoice_id=normalized.invoice_id,
        validation_status=validation.validation_status,
        duplicate_status=duplicate.status,
        risk_level=fraud_risk.risk_level,
        approval_route=approval.route,
        assigned_role=approval.assigned_role,
        notification_agent=notification_agent,
        correlation_id=payload.correlation_id,
    )

    workflow_status = "blocked" if approval.route == ApprovalRoute.BLOCKED else "approval_ready"
    if approval.route == ApprovalRoute.AUTO_APPROVE:
        workflow_status = "auto_approved"

    return {
        "invoice": normalized,
        "validation_result": validation,
        "duplicate_result": duplicate,
        "po_match_result": po_match,
        "fraud_risk_result": fraud_risk,
        "approval_result": approval,
        "notifications": notifications,
        "workflow_status": workflow_status,
        "erp_export_ready": workflow_status in {"approval_ready", "auto_approved"},
        "ocr_result": extraction.ocr_result,
        "confidence_summary": extraction.confidence_summary,
        "review_status": review_task.status if review_task else "not_required",
        "review_tasks": [],
    }


@router.get("")
def list_invoices(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list:
    return repository.list_invoices(tenant_id)


@router.get("/approval-tasks")
def list_approval_tasks(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list:
    return repository.list_approval_tasks(tenant_id)


@router.get("/notification-events")
def list_notification_events(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.NOTIFICATION_READ)),
) -> list:
    return repository.list_notification_events(tenant_id)


@router.get("/purchase-orders")
def list_purchase_orders(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list:
    repository.ensure_phase3_fixtures(tenant_id)
    return repository.list_purchase_orders(tenant_id)


@router.get("/workflows")
def list_workflows(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list:
    return repository.list_workflow_states(tenant_id)


@router.get("/audit-events")
def list_audit_events(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.AUDIT_READ)),
) -> list:
    return repository.list_audit_events(tenant_id)


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
):
    if hasattr(repository, "get_invoice"):
        return repository.get_invoice(tenant_id, invoice_id)

    for invoice in repository.list_invoices(tenant_id):
        if invoice.invoice_id == invoice_id:
            return invoice
    raise HTTPException(status_code=404, detail="invoice not found for tenant")


@router.post("/{invoice_id}/approval-decision", response_model=ApprovalDecisionResult)
def decide_invoice_approval(
    invoice_id: UUID,
    payload: ApprovalDecisionRequest,
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    monitoring_agent: MonitoringAgent = Depends(get_monitoring_agent),
    notification_agent: NotificationAgent = Depends(get_notification_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_APPROVE)),
) -> ApprovalDecisionResult:
    _enforce_body_tenant(payload.tenant_id, context)
    try:
        repository.get_invoice(payload.tenant_id, invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="invoice not found for tenant") from exc

    task = repository.get_latest_approval_task(payload.tenant_id, invoice_id)
    if task is None:
        raise HTTPException(status_code=409, detail="invoice has no approval task to resolve")

    status, workflow_status, export_ready, default_reason = _approval_decision_state(payload.action)
    reason = payload.reason or default_reason
    updated_task = repository.update_approval_task(
        payload.tenant_id,
        task.approval_task_id,
        status=status,
        reason=reason,
    )
    audit_agent.record(
        AuditEventInput(
            tenant_id=payload.tenant_id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action=f"invoice.approval_{payload.action}",
            entity_type="invoice",
            entity_id=invoice_id,
            metadata={
                "approval_task_id": str(updated_task.approval_task_id),
                "route": updated_task.route,
                "approval_status": updated_task.status,
                "reason": reason,
            },
            correlation_id=payload.correlation_id,
        )
    )
    monitoring_agent.record_metric(
        MetricEventInput(
            tenant_id=payload.tenant_id,
            metric_event="invoice.approval_decision",
            value=1,
            metadata={
                "action": payload.action,
                "route": updated_task.route,
                "approval_status": updated_task.status,
            },
        )
    )
    notification_agent.send(
        NotificationInput(
            tenant_id=payload.tenant_id,
            invoice_id=invoice_id,
            notification_type=NotificationType.APPROVAL_DECISION_RECORDED,
            recipient_role="ap_admin",
            payload={
                "action": payload.action,
                "approval_status": updated_task.status,
                "reason": reason,
            },
            correlation_id=payload.correlation_id,
        )
    )
    if hasattr(repository, "store_workflow_state"):
        repository.store_workflow_state(
            WorkflowState(
                workflow_id=invoice_id,
                tenant_id=payload.tenant_id,
                state=workflow_status,
                status=updated_task.status,
                current_agent="ApprovalRoutingAgent",
            )
        )
    usage_event = {
        ApprovalDecisionAction.APPROVE: UsageEventType.INVOICE_APPROVED,
        ApprovalDecisionAction.REJECT: UsageEventType.INVOICE_REJECTED,
        ApprovalDecisionAction.HOLD: UsageEventType.INVOICE_HELD,
    }[payload.action]
    UsageMeteringService(repository).record_usage_event(
        payload.tenant_id,
        usage_event,
        source=UsageEventSource.USER,
        related_invoice_id=invoice_id,
        metadata={"approval_status": str(updated_task.status)},
    )
    return ApprovalDecisionResult(
        invoice_id=invoice_id,
        approval_task_id=updated_task.approval_task_id,
        action=payload.action,
        route=updated_task.route,
        approval_status=updated_task.status,
        reason=reason,
        workflow_status=workflow_status,
        erp_export_ready=export_ready,
        blocker_reason=None if export_ready else reason,
    )


def _enforce_body_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")


def _run_phase2_pipeline(
    payload: InvoiceIngestionInput,
    repository: InMemoryAPRepository,
    ingestion_agent: InvoiceIngestionAgent,
    extraction_agent: InvoiceExtractionAgent,
    normalization_agent: InvoiceNormalizationAgent,
    supplier_identity_agent: SupplierIdentityAgent,
    validation_agent: InvoiceValidationAgent,
    duplicate_detection_agent: DuplicateDetectionAgent,
) -> dict:
    if not repository.list_vendors(payload.tenant_id):
        repository.add_vendor(
            tenant_id=payload.tenant_id,
            name="Northstar Components",
            tax_id="TAX-12345",
        )

    raw_invoice = ingestion_agent.ingest(payload)
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw_invoice.raw_invoice_id,
            tenant_id=raw_invoice.tenant_id,
            storage_url=raw_invoice.storage_url,
            mime_type=raw_invoice.mime_type,
            correlation_id=payload.correlation_id,
        )
    )
    normalized = normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw_invoice.raw_invoice_id,
            tenant_id=raw_invoice.tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            confidence=extraction.confidence,
            file_checksum=raw_invoice.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )
    supplier = supplier_identity_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=normalized.canonical_invoice.supplier_name,
            supplier_tax_id=normalized.canonical_invoice.supplier_tax_id,
            correlation_id=payload.correlation_id,
        )
    )
    validation = validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            canonical_invoice=normalized.canonical_invoice,
            vendor_id=supplier.vendor_id,
            correlation_id=payload.correlation_id,
        )
    )
    duplicate = duplicate_detection_agent.detect(
        DuplicateDetectionInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_number=normalized.canonical_invoice.invoice_number,
            invoice_date=normalized.canonical_invoice.invoice_date,
            grand_total=normalized.canonical_invoice.grand_total,
            file_checksum=normalized.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )
    return {
        "raw_invoice": raw_invoice,
        "extraction": extraction,
        "normalized": normalized,
        "supplier": supplier,
        "validation": validation,
        "duplicate": duplicate,
    }


def _send_pipeline_notifications(
    tenant_id: UUID,
    invoice_id: UUID,
    validation_status: InvoiceValidationStatus,
    duplicate_status: DuplicateStatus,
    risk_level: RiskLevel,
    approval_route: ApprovalRoute,
    assigned_role: str,
    notification_agent: NotificationAgent,
    correlation_id: UUID,
) -> list:
    requests: list[NotificationInput] = []
    if validation_status == InvoiceValidationStatus.FAILED:
        requests.append(
            NotificationInput(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                notification_type=NotificationType.VALIDATION_FAILED,
                recipient_role="ap_specialist",
                payload={"validation_status": validation_status},
                correlation_id=correlation_id,
            )
        )
    if duplicate_status != DuplicateStatus.CLEAR:
        requests.append(
            NotificationInput(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                notification_type=NotificationType.DUPLICATE_DETECTED,
                recipient_role="ap_admin",
                payload={"duplicate_status": duplicate_status},
                correlation_id=correlation_id,
            )
        )
    if approval_route == ApprovalRoute.BLOCKED or risk_level == RiskLevel.CRITICAL:
        requests.append(
            NotificationInput(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                notification_type=NotificationType.INVOICE_BLOCKED,
                recipient_role="ap_admin",
                payload={"risk_level": risk_level, "approval_route": approval_route},
                correlation_id=correlation_id,
            )
        )
    elif approval_route != ApprovalRoute.AUTO_APPROVE:
        requests.append(
            NotificationInput(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                notification_type=NotificationType.APPROVAL_REQUIRED,
                recipient_role=assigned_role,
                payload={"approval_route": approval_route},
                correlation_id=correlation_id,
            )
        )

    return [notification_agent.send(request) for request in requests]


def continue_full_pipeline_from_extraction(
    tenant_id: UUID,
    raw_invoice_id: UUID,
    extraction,
    file_checksum: str | None,
    correlation_id: UUID,
    repository: InMemoryAPRepository,
    normalization_agent: InvoiceNormalizationAgent,
    supplier_identity_agent: SupplierIdentityAgent,
    validation_agent: InvoiceValidationAgent,
    duplicate_detection_agent: DuplicateDetectionAgent,
    po_matching_agent: PurchaseOrderMatchingAgent,
    fraud_risk_agent: FraudRiskScoringAgent,
    approval_routing_agent: ApprovalRoutingAgent,
    notification_agent: NotificationAgent,
    review_agent: HumanReviewAgent,
) -> dict:
    corrected_fields_applied = bool(
        extraction.ocr_result
        and extraction.ocr_result.raw_response.get("corrected_fields_applied")
    )
    corrected_field_count = int(
        extraction.ocr_result.raw_response.get("corrected_field_count", 0)
        if extraction.ocr_result
        else 0
    )
    review_task = (
        review_agent.inspect_extraction(extraction.ocr_result, raw_invoice_id=raw_invoice_id)
        if extraction.ocr_result is not None
        else None
    )
    review_tasks = [review_task] if review_task is not None and review_task.status != "not_required" else []
    if review_tasks:
        unresolved_review_fields = sorted(
            {
                issue.field_name
                for task in review_tasks
                for issue in task.issues
            }
        )
        return {
            "invoice": None,
            "validation_result": None,
            "duplicate_result": None,
            "po_match_result": None,
            "fraud_risk_result": None,
            "approval_result": None,
            "notifications": [],
            "workflow_status": "review_required",
            "erp_export_ready": False,
            "ocr_result": extraction.ocr_result,
            "confidence_summary": extraction.confidence_summary,
            "review_status": review_task.status,
            "review_tasks": review_tasks,
            "corrected_fields_applied": corrected_fields_applied,
            "corrected_field_count": corrected_field_count,
            "unresolved_review_fields": unresolved_review_fields,
            "invoice_created": False,
            "blocker_reason": _review_blocker_reason(unresolved_review_fields),
        }

    normalized = normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw_invoice_id,
            tenant_id=tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            confidence=extraction.confidence,
            file_checksum=file_checksum,
            correlation_id=correlation_id,
        )
    )
    supplier = supplier_identity_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=normalized.canonical_invoice.supplier_name,
            supplier_tax_id=normalized.canonical_invoice.supplier_tax_id,
            correlation_id=correlation_id,
        )
    )
    validation = validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            canonical_invoice=normalized.canonical_invoice,
            vendor_id=supplier.vendor_id,
            correlation_id=correlation_id,
        )
    )
    duplicate = duplicate_detection_agent.detect(
        DuplicateDetectionInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_number=normalized.canonical_invoice.invoice_number,
            invoice_date=normalized.canonical_invoice.invoice_date,
            grand_total=normalized.canonical_invoice.grand_total,
            file_checksum=normalized.file_checksum,
            correlation_id=correlation_id,
        )
    )
    invoice = normalized.canonical_invoice
    po_match = po_matching_agent.match(
        PurchaseOrderMatchingInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            po_number=invoice.po_number,
            invoice_lines=invoice.line_items,
            invoice_total=invoice.grand_total,
            currency=invoice.currency,
            correlation_id=correlation_id,
        )
    )
    fraud_risk = fraud_risk_agent.score(
        FraudRiskScoringInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_total=invoice.grand_total,
            duplicate_result=duplicate,
            supplier_result=supplier,
            po_match_result=po_match,
            validation_result=validation,
            correlation_id=correlation_id,
        )
    )
    approval = approval_routing_agent.route(
        ApprovalRoutingInput(
            tenant_id=normalized.tenant_id,
            invoice_id=normalized.invoice_id,
            amount=invoice.grand_total,
            match_status=po_match.match_status,
            risk_level=fraud_risk.risk_level,
            validation_status=validation.validation_status,
            duplicate_status=duplicate.status,
            correlation_id=correlation_id,
        )
    )
    notifications = _send_pipeline_notifications(
        tenant_id=normalized.tenant_id,
        invoice_id=normalized.invoice_id,
        validation_status=validation.validation_status,
        duplicate_status=duplicate.status,
        risk_level=fraud_risk.risk_level,
        approval_route=approval.route,
        assigned_role=approval.assigned_role,
        notification_agent=notification_agent,
        correlation_id=correlation_id,
    )
    workflow_status = "blocked" if approval.route == ApprovalRoute.BLOCKED else "approval_ready"
    if approval.route == ApprovalRoute.AUTO_APPROVE:
        workflow_status = "auto_approved"

    return {
        "invoice": normalized,
        "validation_result": validation,
        "duplicate_result": duplicate,
        "po_match_result": po_match,
        "fraud_risk_result": fraud_risk,
        "approval_result": approval,
        "notifications": notifications,
        "workflow_status": workflow_status,
        "erp_export_ready": workflow_status in {"approval_ready", "auto_approved"},
        "ocr_result": extraction.ocr_result,
        "confidence_summary": extraction.confidence_summary,
        "review_status": review_task.status if review_task else "not_required",
        "review_tasks": [],
        "corrected_fields_applied": corrected_fields_applied,
        "corrected_field_count": corrected_field_count,
        "unresolved_review_fields": [],
        "invoice_created": True,
        "blocker_reason": None,
    }


def _review_blocker_reason(unresolved_review_fields: list[str]) -> str:
    if not unresolved_review_fields:
        return "Human review remains required before invoice creation."
    fields = ", ".join(unresolved_review_fields)
    return f"Human review remains required for fields: {fields}."


def _approval_decision_state(
    action: ApprovalDecisionAction,
) -> tuple[ApprovalTaskStatus, str, bool, str]:
    if action == ApprovalDecisionAction.APPROVE:
        return (
            ApprovalTaskStatus.APPROVED,
            "approval_ready",
            True,
            "Invoice approved by authorized reviewer.",
        )
    if action == ApprovalDecisionAction.REJECT:
        return (
            ApprovalTaskStatus.REJECTED,
            "rejected",
            False,
            "Invoice rejected by authorized reviewer.",
        )
    return (
        ApprovalTaskStatus.ON_HOLD,
        "blocked",
        False,
        "Invoice kept on hold by authorized reviewer.",
    )
