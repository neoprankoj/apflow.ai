from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    ExtractionReviewReason,
    InvoiceExtractionInput,
    InvoiceExtractionOutput,
    MetricEventInput,
    WorkflowErrorInput,
)
from app.integrations.ocr.base import OCRAdapterProtocol
from app.integrations.ocr.factory import OCRProviderFactory
from app.integrations.ocr.mock import MockOCRProvider


class InvoiceExtractionAgent(BaseAgent[InvoiceExtractionInput, InvoiceExtractionOutput]):
    name = "InvoiceExtractionAgent"
    responsibility = "Extract invoice fields and line items from raw invoice files."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        ocr_provider: OCRAdapterProtocol | None = None,
        review_threshold: float = 0.8,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.ocr_provider = ocr_provider or OCRProviderFactory().get_provider()
        self.review_threshold = review_threshold

    def extract(self, request: InvoiceExtractionInput) -> InvoiceExtractionOutput:
        try:
            raw = self.repository.get_raw_invoice(request.tenant_id, request.raw_invoice_id)
            ocr_result = self.ocr_provider.extract_invoice(
                {
                    "content": raw.content,
                    "mime_type": request.mime_type,
                    "storage_url": request.storage_url,
                    "raw_invoice_id": str(request.raw_invoice_id),
                },
                request.tenant_id,
            )
            result = MockOCRProvider().to_legacy_result(ocr_result)
            confidence = result["confidence"]
            review_reasons: list[ExtractionReviewReason] = []

            if confidence.get("document", 0) < self.review_threshold:
                review_reasons.append(ExtractionReviewReason.LOW_CONFIDENCE)
            if request.mime_type != raw.output.mime_type:
                review_reasons.append(ExtractionReviewReason.UNSUPPORTED_MIME_TYPE)
            if ocr_result.error:
                review_reasons.append(ExtractionReviewReason.MISSING_REQUIRED_FIELD)

            output = InvoiceExtractionOutput(
                raw_invoice_id=request.raw_invoice_id,
                tenant_id=request.tenant_id,
                fields=result["fields"],
                line_items=result["line_items"],
                confidence=confidence,
                needs_review=bool(review_reasons),
                review_reasons=review_reasons,
                ocr_result=ocr_result,
                confidence_summary=ocr_result.confidence_summary,
            )
            self.repository.store_extraction(output)
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="invoice.extracted",
                    entity_type="raw_invoice",
                    entity_id=request.raw_invoice_id,
                    metadata={
                        "extraction_id": str(output.extraction_id),
                        "needs_review": output.needs_review,
                        "ocr_provider": ocr_result.provider_metadata.provider_name,
                        "average_confidence": ocr_result.confidence_summary.average_confidence,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="invoice.extracted",
                    value=1,
                    metadata={
                        "needs_review": output.needs_review,
                        "ocr_provider": ocr_result.provider_metadata.provider_name,
                        "average_confidence": ocr_result.confidence_summary.average_confidence,
                    },
                )
            )
            return output
        except Exception as exc:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=request.tenant_id,
                    workflow_id=request.correlation_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.TRANSIENT,
                    error_message=str(exc),
                    retry_count=0,
                    context={"raw_invoice_id": str(request.raw_invoice_id)},
                )
            )
            raise
