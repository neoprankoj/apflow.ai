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
    ConfidenceBand,
    ExtractedInvoiceFields,
    InvoiceExtractionInput,
    InvoiceExtractionOutput,
    InvoiceIngestionOutput,
    InvoiceProcessFromUploadRequest,
    InvoiceProcessFromUploadResult,
    InvoiceSource,
    InvoiceUploadResult,
    HumanReviewStatus,
    OCRConfidenceSummary,
    OCRExtractedField,
    OCRExtractionResult,
    Permission,
    UsageEventSource,
    UsageEventType,
    UploadedInvoiceDocument,
)
from app.services.usage_metering_service import UsageMeteringService

router = APIRouter()

ALLOWED_UPLOAD_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}


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
    UsageMeteringService(repository).record_usage_event(
        tenant_id,
        UsageEventType.INVOICE_UPLOADED,
        source=UsageEventSource.USER,
        related_document_id=document.document_id,
        metadata={"content_type": content_type, "size_bytes": len(content)},
    )
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
    usage = UsageMeteringService(repository)
    usage.record_usage_event(
        tenant_id,
        UsageEventType.OCR_EXTRACTION_ATTEMPTED,
        source=UsageEventSource.USER,
        related_document_id=document_id,
        metadata={"mime_type": raw.mime_type},
    )
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
        )
    )
    usage.record_usage_event(
        tenant_id,
        UsageEventType.OCR_EXTRACTION_FAILED
        if extraction.ocr_result is not None and extraction.ocr_result.error
        else UsageEventType.OCR_EXTRACTION_SUCCEEDED,
        source=UsageEventSource.SYSTEM,
        related_document_id=document_id,
        metadata={"provider": _ocr_provider_name(extraction.ocr_result)},
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
    usage = UsageMeteringService(repository)
    usage.record_usage_event(
        payload.tenant_id,
        UsageEventType.OCR_EXTRACTION_ATTEMPTED,
        source=UsageEventSource.USER,
        related_document_id=document_id,
        metadata={"stage": "process", "mime_type": raw.mime_type},
    )
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=payload.tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
            correlation_id=payload.correlation_id,
        )
    )
    usage.record_usage_event(
        payload.tenant_id,
        UsageEventType.OCR_EXTRACTION_FAILED
        if extraction.ocr_result is not None and extraction.ocr_result.error
        else UsageEventType.OCR_EXTRACTION_SUCCEEDED,
        source=UsageEventSource.SYSTEM,
        related_document_id=document_id,
        metadata={"stage": "process", "provider": _ocr_provider_name(extraction.ocr_result)},
    )
    extraction = _apply_latest_corrected_review_task(payload.tenant_id, raw.raw_invoice_id, extraction, repository)
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
    if pipeline.get("invoice_created") and pipeline.get("invoice"):
        usage.record_usage_event(
            payload.tenant_id,
            UsageEventType.INVOICE_PROCESSED,
            source=UsageEventSource.USER,
            related_invoice_id=pipeline["invoice"].invoice_id,
            related_document_id=document_id,
            metadata={"workflow_status": pipeline["workflow_status"]},
        )
    return InvoiceProcessFromUploadResult(
        document=document,
        extraction_result=extraction,
        pipeline_result=pipeline,
        review_status=pipeline.get("review_status"),
        workflow_status=pipeline["workflow_status"],
        corrected_fields_applied=pipeline["corrected_fields_applied"],
        corrected_field_count=pipeline["corrected_field_count"],
        unresolved_review_fields=pipeline["unresolved_review_fields"],
        invoice_created=pipeline["invoice_created"],
        blocker_reason=pipeline["blocker_reason"],
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
        original_file_name=document.original_file_name,
    )
    repository.store_raw_invoice(raw, content=content)
    return document, raw


def _ocr_provider_name(ocr_result: OCRExtractionResult | None) -> str | None:
    if ocr_result is None:
        return None
    provider = ocr_result.raw_response.get("provider") if ocr_result.raw_response else None
    return str(provider) if provider else None


def _enforce_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")


def _apply_latest_corrected_review_task(
    tenant_id: UUID,
    raw_invoice_id: UUID,
    extraction: InvoiceExtractionOutput,
    repository: InMemoryAPRepository,
) -> InvoiceExtractionOutput:
    corrected_tasks = [
        task
        for task in repository.list_review_tasks(tenant_id)
        if task.raw_invoice_id == raw_invoice_id
        and task.status == HumanReviewStatus.CORRECTED
        and task.corrected_fields
    ]
    if not corrected_tasks:
        return extraction
    latest = sorted(corrected_tasks, key=lambda task: task.updated_at)[-1]
    normalized = _normalize_corrections(latest.corrected_fields)
    if not normalized:
        return extraction

    fields = extraction.fields.model_copy(update=normalized)
    confidence = {**extraction.confidence}
    for field_name in normalized:
        confidence[field_name] = 1.0

    ocr_result = extraction.ocr_result
    confidence_summary = extraction.confidence_summary
    if ocr_result is not None:
        ocr_result = _apply_corrections_to_ocr_result(ocr_result, normalized)
        confidence_summary = ocr_result.confidence_summary

    missing_required = [
        field_name
        for field_name in ["invoice_number", "supplier_name", "invoice_date", "currency", "grand_total"]
        if getattr(fields, field_name) in (None, "")
    ]
    return extraction.model_copy(
        update={
            "fields": fields,
            "confidence": confidence,
            "needs_review": bool(missing_required),
            "review_reasons": [] if not missing_required else extraction.review_reasons,
            "ocr_result": ocr_result,
            "confidence_summary": confidence_summary,
        }
    )


def _apply_corrections_to_ocr_result(
    ocr_result: OCRExtractionResult,
    corrections: dict[str, str | float],
) -> OCRExtractionResult:
    field_map = {field.field_name: field for field in ocr_result.fields}
    for field_name, value in corrections.items():
        field_map[field_name] = OCRExtractedField(
            field_name=field_name,
            value=value,
            confidence=1.0,
            raw_text="manual correction",
            requires_review=False,
        )
    fields = list(field_map.values())
    summary = _confidence_summary(fields)
    return ocr_result.model_copy(
        update={
            "fields": fields,
            "confidence_summary": summary,
            "raw_response": {
                **ocr_result.raw_response,
                "corrected_fields_applied": True,
                "corrected_field_count": len(corrections),
            },
            "error": None,
        }
    )


def _normalize_corrections(corrections: dict) -> dict[str, str | float]:
    aliases = {
        "vendor_name": "supplier_name",
        "total_amount": "grand_total",
        "tax_amount": "tax_total",
        "purchase_order_number": "po_number",
    }
    numeric_fields = {"subtotal", "tax_total", "shipping_amount", "fee_total", "discount_total", "grand_total"}
    allowed = set(ExtractedInvoiceFields.model_fields)
    normalized: dict[str, str | float] = {}
    for raw_name, raw_value in corrections.items():
        field_name = aliases.get(str(raw_name), str(raw_name))
        if field_name not in allowed or raw_value in (None, ""):
            continue
        if field_name in numeric_fields:
            try:
                normalized[field_name] = float(str(raw_value).replace(",", ""))
            except ValueError:
                continue
        else:
            normalized[field_name] = str(raw_value).strip()
    return normalized


def _confidence_summary(fields: list[OCRExtractedField]) -> OCRConfidenceSummary:
    required = ["invoice_number", "supplier_name", "invoice_date", "currency", "grand_total"]
    missing = [
        field_name
        for field_name in required
        if not any(field.field_name == field_name and field.value not in (None, "") for field in fields)
    ]
    low_required = [
        field.field_name
        for field in fields
        if field.field_name in required and field.value not in (None, "") and field.confidence < 0.75
    ]
    average = round(sum(field.confidence for field in fields) / len(fields), 4) if fields else 0
    return OCRConfidenceSummary(
        average_confidence=average,
        high_confidence_fields=sum(1 for field in fields if _band(field.confidence) == ConfidenceBand.HIGH),
        medium_confidence_fields=sum(1 for field in fields if _band(field.confidence) == ConfidenceBand.MEDIUM),
        low_confidence_fields=sum(1 for field in fields if _band(field.confidence) == ConfidenceBand.LOW),
        required_fields_missing=missing,
        required_fields_low_confidence=low_required,
    )


def _band(confidence: float) -> ConfidenceBand:
    if confidence >= 0.9:
        return ConfidenceBand.HIGH
    if confidence >= 0.75:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW
