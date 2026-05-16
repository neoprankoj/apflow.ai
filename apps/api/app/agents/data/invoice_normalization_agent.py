from datetime import date

from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CanonicalInvoice,
    ErrorCategory,
    InvoiceNormalizationInput,
    InvoiceNormalizationOutput,
    MetricEventInput,
    WorkflowErrorInput,
)


class InvoiceNormalizationAgent(BaseAgent[InvoiceNormalizationInput, InvoiceNormalizationOutput]):
    name = "InvoiceNormalizationAgent"
    responsibility = "Convert extracted data into the canonical APFlow invoice schema."

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

    def normalize(self, request: InvoiceNormalizationInput) -> InvoiceNormalizationOutput:
        try:
            fields = request.fields
            warnings: list[str] = []
            currency = (fields.currency or "USD").upper()
            if fields.currency is None:
                warnings.append("currency defaulted to USD")

            subtotal = round(float(fields.subtotal or 0), 2)
            tax_total = round(float(fields.tax_total or 0), 2)
            shipping_amount = round(float(fields.shipping_amount or 0), 2)
            fee_total = round(float(fields.fee_total or 0), 2)
            discount_total = round(float(fields.discount_total or 0), 2)
            grand_total = round(
                float(fields.grand_total or subtotal + tax_total + shipping_amount + fee_total - discount_total),
                2,
            )
            invoice_date = fields.invoice_date or date.today().isoformat()
            total_components_complete = self._total_components_complete(
                subtotal=fields.subtotal,
                tax_total=fields.tax_total,
                shipping_amount=fields.shipping_amount,
                fee_total=fields.fee_total,
                discount_total=fields.discount_total,
                grand_total=fields.grand_total,
            )

            canonical = CanonicalInvoice(
                invoice_number=self._required(fields.invoice_number, "invoice_number"),
                supplier_name=self._required(fields.supplier_name, "supplier_name").strip(),
                supplier_tax_id=fields.supplier_tax_id.strip() if fields.supplier_tax_id else None,
                invoice_date=invoice_date,
                due_date=fields.due_date,
                currency=currency,
                subtotal=subtotal,
                tax_total=tax_total,
                shipping_amount=shipping_amount,
                fee_total=fee_total,
                discount_total=discount_total,
                grand_total=grand_total,
                total_components_complete=total_components_complete,
                po_number=fields.po_number,
                line_items=request.line_items,
            )
            output = InvoiceNormalizationOutput(
                tenant_id=request.tenant_id,
                canonical_invoice=canonical,
                normalization_warnings=warnings,
                file_checksum=request.file_checksum,
            )
            self.repository.store_invoice(output)
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="invoice.normalized",
                    entity_type="invoice",
                    entity_id=output.invoice_id,
                    metadata={
                        "warnings": warnings,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="invoice.normalized",
                    value=1,
                    metadata={"warning_count": len(warnings)},
                )
            )
            return output
        except Exception as exc:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=request.tenant_id,
                    workflow_id=request.correlation_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.VALIDATION,
                    error_message=str(exc),
                    retry_count=0,
                    context={"extraction_id": str(request.extraction_id)},
                )
            )
            raise

    def _required(self, value: str | None, field_name: str) -> str:
        if value is None or not value.strip():
            raise ValueError(f"{field_name} is required for normalization")
        return value

    def _total_components_complete(
        self,
        *,
        subtotal: float | None,
        tax_total: float | None,
        shipping_amount: float | None,
        fee_total: float | None,
        discount_total: float | None,
        grand_total: float | None,
    ) -> bool:
        if subtotal is None or grand_total is None:
            return False
        optional_components = [tax_total, shipping_amount, fee_total, discount_total]
        if any(value is not None for value in optional_components):
            return True
        return round(float(subtotal), 2) == round(float(grand_total), 2)
