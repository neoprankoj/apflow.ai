from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agents.data.invoice_extraction_agent import InvoiceExtractionAgent
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
    get_approval_routing_agent,
    get_duplicate_detection_agent,
    get_fraud_risk_scoring_agent,
    get_human_review_agent,
    get_invoice_extraction_agent,
    get_invoice_normalization_agent,
    get_invoice_validation_agent,
    get_notification_agent,
    get_purchase_order_matching_agent,
    get_repository,
    get_storage_adapter,
    get_supplier_identity_agent,
    require_permission,
    resolve_tenant_id,
)
from app.api.routes.invoices import continue_full_pipeline_from_extraction
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    CurrentUserContext,
    DocumentReference,
    InvoiceExtractionInput,
    InvoiceIngestionOutput,
    InvoiceProcessFromUploadRequest,
    InvoiceProcessFromUploadResult,
    InvoiceSource,
    InvoiceUploadResult,
    Permission,
    UploadedInvoiceDocument,
)

router = APIRouter()

ALLOWED_UPLOAD_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}


@router.post("/invoices/upload", response_model=InvoiceUploadResult)
async def upload_invoice_document(
    tenant_id: UUID = Form(...),
    uploaded_by: str | None = Form(default=None),
    file: UploadFile = File(...),
    repository: InMemoryAPRepository = Depends(get_repository),
    storage=Depends(get_storage_adapter),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> InvoiceUploadResult:
    _enforce_tenant(tenant_id, context)
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported invoice file type")
    content = await file.read()
    if len(content) > settings.max_invoice_upload_bytes:
        raise HTTPException(status_code=413, detail="Invoice upload exceeds size limit")
    reference = storage.save_document(
        tenant_id=tenant_id,
        file_name=file.filename or "invoice",
        content_type=content_type,
        content=content,
    )
    document = UploadedInvoiceDocument(
        document_id=reference.document_id,
        tenant_id=tenant_id,
        original_file_name=file.filename or "invoice",
        content_type=content_type,
        size_bytes=len(content),
        storage_provider=reference.storage_provider,
        storage_key=reference.storage_key,
        uploaded_by=uploaded_by or context.user.email,
    )
    repository.store_uploaded_document(document)
    return InvoiceUploadResult(document=document, document_reference=reference)


@router.get("/invoices")
def list_invoice_documents(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list[UploadedInvoiceDocument]:
    return repository.list_uploaded_documents(tenant_id)


@router.get("/invoices/{document_id}", response_model=UploadedInvoiceDocument)
def get_invoice_document(
    document_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> UploadedInvoiceDocument:
    try:
        return repository.get_uploaded_document(tenant_id, document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document not found for tenant") from exc


@router.post("/invoices/{document_id}/extract")
def extract_invoice_document(
    document_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    storage=Depends(get_storage_adapter),
    extraction_agent: InvoiceExtractionAgent = Depends(get_invoice_extraction_agent),
    review_agent: HumanReviewAgent = Depends(get_human_review_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> dict:
    document, raw = _prepare_raw_invoice_from_document(tenant_id, document_id, repository, storage)
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
        )
    )
    review_task = review_agent.inspect_extraction(extraction.ocr_result, raw_invoice_id=raw.raw_invoice_id)
    review_tasks = [review_task] if review_task.status != "not_required" else []
    return {
        "document": document,
        "extraction": extraction,
        "ocr_result": extraction.ocr_result,
        "confidence_summary": extraction.confidence_summary,
        "review_status": review_task.status,
        "review_tasks": review_tasks,
    }


@router.post("/invoices/{document_id}/process", response_model=InvoiceProcessFromUploadResult)
def process_invoice_document(
    document_id: UUID,
    payload: InvoiceProcessFromUploadRequest,
    repository: InMemoryAPRepository = Depends(get_repository),
    storage=Depends(get_storage_adapter),
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
) -> InvoiceProcessFromUploadResult:
    _enforce_tenant(payload.tenant_id, context)
    repository.ensure_phase3_fixtures(payload.tenant_id)
    document, raw = _prepare_raw_invoice_from_document(payload.tenant_id, document_id, repository, storage)
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=payload.tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
            correlation_id=payload.correlation_id,
        )
    )
    pipeline = continue_full_pipeline_from_extraction(
        tenant_id=payload.tenant_id,
        raw_invoice_id=raw.raw_invoice_id,
        extraction=extraction,
        file_checksum=raw.file_checksum,
        correlation_id=payload.correlation_id,
        repository=repository,
        normalization_agent=normalization_agent,
        supplier_identity_agent=supplier_identity_agent,
        validation_agent=validation_agent,
        duplicate_detection_agent=duplicate_detection_agent,
        po_matching_agent=po_matching_agent,
        fraud_risk_agent=fraud_risk_agent,
        approval_routing_agent=approval_routing_agent,
        notification_agent=notification_agent,
        review_agent=review_agent,
    )
    return InvoiceProcessFromUploadResult(
        document=document,
        extraction_result=extraction,
        pipeline_result=pipeline,
        review_status=pipeline.get("review_status"),
        workflow_status=pipeline["workflow_status"],
    )


def _prepare_raw_invoice_from_document(
    tenant_id: UUID,
    document_id: UUID,
    repository: InMemoryAPRepository,
    storage,
) -> tuple[UploadedInvoiceDocument, InvoiceIngestionOutput]:
    try:
        document = repository.get_uploaded_document(tenant_id, document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Document not found for tenant") from exc
    reference = DocumentReference(
        document_id=document.document_id,
        tenant_id=document.tenant_id,
        storage_provider=document.storage_provider,
        storage_key=document.storage_key,
        content_type=document.content_type,
    )
    content = storage.get_document(reference)
    raw = InvoiceIngestionOutput(
        raw_invoice_id=document.document_id,
        tenant_id=tenant_id,
        storage_url=f"{document.storage_provider}://{document.storage_key}",
        mime_type=document.content_type,
        source=InvoiceSource.UPLOAD,
        file_checksum=sha256(content).hexdigest(),
    )
    repository.store_raw_invoice(raw, content=content)
    return document, raw


def _enforce_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
