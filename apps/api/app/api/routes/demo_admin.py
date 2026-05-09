from datetime import UTC, datetime

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
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import (
    get_approval_routing_agent,
    get_audit_agent,
    get_duplicate_detection_agent,
    get_fraud_risk_scoring_agent,
    get_human_review_agent,
    get_invoice_extraction_agent,
    get_invoice_ingestion_agent,
    get_invoice_normalization_agent,
    get_invoice_validation_agent,
    get_notification_agent,
    get_purchase_order_matching_agent,
    get_repository,
    get_supplier_identity_agent,
    require_permission,
)
from app.api.routes.invoices import run_full_mock_invoice_pipeline
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    InvoiceIngestionInput,
    InvoiceIngestionMetadata,
    InvoiceSource,
    Permission,
)

router = APIRouter()


@router.post("/demo/reset")
def reset_demo_data(
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
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
) -> dict:
    if settings.app_env != "staging" or not settings.allow_demo_reset:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    tenant_id = context.tenant.id
    repository.ensure_phase3_fixtures(tenant_id)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    payload = InvoiceIngestionInput(
        tenant_id=tenant_id,
        source=InvoiceSource.UPLOAD,
        file_url=f"mock://demo/reset-invoice-{stamp}.pdf",
        metadata=InvoiceIngestionMetadata(
            sender_email="demo-ap@apflow.local",
            original_filename=f"demo-reset-invoice-{stamp}.pdf",
            mime_type="application/pdf",
        ),
        content=(
            f"invoice_number=INV-DEMO-{stamp} "
            "supplier_name=Northstar Components supplier_tax_id=TAX-12345 "
            "subtotal=1000 tax_total=170 grand_total=1170 currency=USD "
            "invoice_date=2026-05-09 po_number=PO-100"
        ),
    )
    pipeline = run_full_mock_invoice_pipeline(
        payload=payload,
        repository=repository,
        ingestion_agent=ingestion_agent,
        extraction_agent=extraction_agent,
        normalization_agent=normalization_agent,
        supplier_identity_agent=supplier_identity_agent,
        validation_agent=validation_agent,
        duplicate_detection_agent=duplicate_detection_agent,
        po_matching_agent=po_matching_agent,
        fraud_risk_agent=fraud_risk_agent,
        approval_routing_agent=approval_routing_agent,
        notification_agent=notification_agent,
        review_agent=review_agent,
        context=context,
    )
    invoice = pipeline.get("invoice")
    invoice_id = invoice.invoice_id if invoice is not None else None
    invoice_number = invoice.canonical_invoice.invoice_number if invoice is not None else None

    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="admin.demo_reset",
            entity_type="tenant",
            entity_id=tenant_id,
            metadata={
                "invoice_id": str(invoice_id) if invoice_id else None,
                "workflow_status": pipeline["workflow_status"],
            },
        )
    )
    return {
        "tenant_id": tenant_id,
        "tenant_name": context.tenant.name,
        "user_email": context.user.email,
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "workflow_status": pipeline["workflow_status"],
        "erp_export_ready": bool(pipeline.get("erp_export_ready")),
        "vendor_count": len(repository.list_vendors(tenant_id)),
        "purchase_order_count": len(repository.list_purchase_orders(tenant_id)),
        "approval_task_count": len(repository.list_approval_tasks(tenant_id)),
        "notification_count": len(repository.list_notification_events(tenant_id)),
        "reset_at": datetime.now(UTC).isoformat(),
    }
