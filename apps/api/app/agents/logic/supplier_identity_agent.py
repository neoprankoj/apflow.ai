from difflib import SequenceMatcher

from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository, VendorRecord
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    MetricEventInput,
    SupplierIdentityInput,
    SupplierIdentityOutput,
    SupplierMatchStatus,
    WorkflowErrorInput,
)


class SupplierIdentityAgent(BaseAgent[SupplierIdentityInput, SupplierIdentityOutput]):
    name = "SupplierIdentityAgent"
    responsibility = "Match invoices to known vendors and flag unknown suppliers."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        possible_match_threshold: float = 0.72,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.possible_match_threshold = possible_match_threshold

    def match_supplier(self, request: SupplierIdentityInput) -> SupplierIdentityOutput:
        try:
            candidates = self.repository.list_vendors(request.tenant_id)
            best_vendor, confidence, evidence = self._best_match(request, candidates)

            if best_vendor is None:
                status = SupplierMatchStatus.UNKNOWN_VENDOR
                vendor_id = None
            elif confidence >= 0.95:
                status = SupplierMatchStatus.MATCHED
                vendor_id = best_vendor.vendor_id
            elif confidence >= self.possible_match_threshold:
                status = SupplierMatchStatus.POSSIBLE_MATCH
                vendor_id = best_vendor.vendor_id
            else:
                status = SupplierMatchStatus.UNKNOWN_VENDOR
                vendor_id = None

            self.repository.update_invoice_vendor(request.tenant_id, request.invoice_id, vendor_id)
            output = SupplierIdentityOutput(
                invoice_id=request.invoice_id,
                vendor_id=vendor_id,
                match_confidence=round(confidence, 4),
                status=status,
                evidence=evidence,
            )
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="supplier.matched",
                    entity_type="invoice",
                    entity_id=request.invoice_id,
                    metadata={
                        "status": status,
                        "confidence": output.match_confidence,
                        "vendor_id": str(vendor_id) if vendor_id else None,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="supplier.match",
                    value=1,
                    metadata={"status": status},
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

    def _best_match(
        self,
        request: SupplierIdentityInput,
        candidates: list[VendorRecord],
    ) -> tuple[VendorRecord | None, float, list[str]]:
        best_vendor: VendorRecord | None = None
        best_score = 0.0
        evidence: list[str] = []
        supplier_name = request.supplier_name.casefold().strip()

        for vendor in candidates:
            score = SequenceMatcher(None, supplier_name, vendor.name.casefold()).ratio()
            reasons = [f"name similarity {score:.2f}"]
            if request.supplier_tax_id and vendor.tax_id == request.supplier_tax_id:
                score = max(score, 1.0)
                reasons.append("tax ID exact match")
            if request.bank_account_hash and vendor.bank_account_hash == request.bank_account_hash:
                score = max(score, 0.98)
                reasons.append("bank hash exact match")

            if score > best_score:
                best_vendor = vendor
                best_score = score
                evidence = reasons

        return best_vendor, best_score, evidence
