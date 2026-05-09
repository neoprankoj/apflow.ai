from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository, InvoiceRecord
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    DuplicateDetectionInput,
    DuplicateDetectionOutput,
    DuplicateEvidence,
    DuplicateStatus,
    ErrorCategory,
    MetricEventInput,
    WorkflowErrorInput,
)


class DuplicateDetectionAgent(BaseAgent[DuplicateDetectionInput, DuplicateDetectionOutput]):
    name = "DuplicateDetectionAgent"
    responsibility = "Detect possible duplicate invoices and duplicate payment risks."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent

    def detect(self, request: DuplicateDetectionInput) -> DuplicateDetectionOutput:
        try:
            evidence: list[DuplicateEvidence] = []
            for existing in self.repository.list_invoices(request.tenant_id):
                if existing.invoice_id == request.invoice_id:
                    continue
                evidence.extend(self._compare(request, existing))

            duplicate_score = round(max((item.score for item in evidence), default=0.0), 4)
            if duplicate_score >= 0.9:
                status = DuplicateStatus.LIKELY_DUPLICATE
            elif duplicate_score >= 0.6:
                status = DuplicateStatus.POSSIBLE_DUPLICATE
            else:
                status = DuplicateStatus.CLEAR

            output = DuplicateDetectionOutput(
                invoice_id=request.invoice_id,
                duplicate_score=duplicate_score,
                possible_duplicates=evidence,
                status=status,
            )
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="invoice.duplicate_scored",
                    entity_type="invoice",
                    entity_id=request.invoice_id,
                    metadata={
                        "status": status,
                        "duplicate_score": duplicate_score,
                        "evidence_count": len(evidence),
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="invoice.duplicate_scored",
                    value=1,
                    metadata={"status": status, "duplicate_score": duplicate_score},
                )
            )
            return output
        except Exception as exc:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=request.tenant_id,
                    workflow_id=request.correlation_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.UNKNOWN,
                    error_message=str(exc),
                    retry_count=0,
                    context={"invoice_id": str(request.invoice_id)},
                )
            )
            raise

    def _compare(
        self,
        request: DuplicateDetectionInput,
        existing: InvoiceRecord,
    ) -> list[DuplicateEvidence]:
        invoice = existing.canonical_invoice
        evidence: list[DuplicateEvidence] = []

        if request.file_checksum and request.file_checksum == existing.file_checksum:
            evidence.append(
                DuplicateEvidence(
                    invoice_id=existing.invoice_id,
                    reason="file checksum exact match",
                    score=1.0,
                )
            )

        if request.vendor_id and request.vendor_id == existing.vendor_id:
            same_number = request.invoice_number.casefold() == invoice.invoice_number.casefold()
            same_amount = abs(request.grand_total - invoice.grand_total) < 0.01
            same_date = request.invoice_date == invoice.invoice_date
            if same_number and same_amount:
                evidence.append(
                    DuplicateEvidence(
                        invoice_id=existing.invoice_id,
                        reason="same vendor, invoice number, and amount",
                        score=0.95,
                    )
                )
            elif same_number or (same_amount and same_date):
                evidence.append(
                    DuplicateEvidence(
                        invoice_id=existing.invoice_id,
                        reason="partial vendor invoice duplicate signal",
                        score=0.65,
                    )
                )

        return evidence
