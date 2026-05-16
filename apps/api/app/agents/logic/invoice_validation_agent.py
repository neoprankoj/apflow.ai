from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    InvoiceValidationInput,
    InvoiceValidationOutput,
    InvoiceValidationStatus,
    MetricEventInput,
    WorkflowErrorInput,
)
from app.core.totals import reconcile_total


class InvoiceValidationAgent(BaseAgent[InvoiceValidationInput, InvoiceValidationOutput]):
    name = "InvoiceValidationAgent"
    responsibility = "Validate invoice completeness, math, tax fields, and tenant rules."

    def __init__(
        self,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        total_tolerance: float = 0.02,
    ) -> None:
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.total_tolerance = total_tolerance

    def validate(self, request: InvoiceValidationInput) -> InvoiceValidationOutput:
        try:
            invoice = request.canonical_invoice
            errors: list[str] = []
            warnings: list[str] = []

            if not invoice.invoice_number.strip():
                errors.append("invoice_number is required")
            if not invoice.supplier_name.strip():
                errors.append("supplier_name is required")
            if invoice.grand_total <= 0:
                errors.append("grand_total must be greater than zero")
            if not invoice.currency or len(invoice.currency) != 3:
                errors.append("currency must be a 3-letter ISO code")
            if request.vendor_id is None:
                warnings.append("vendor is not confidently matched")

            reconciliation = reconcile_total(
                subtotal=invoice.subtotal,
                tax_total=invoice.tax_total,
                shipping_amount=invoice.shipping_amount,
                fee_total=invoice.fee_total,
                discount_total=invoice.discount_total,
                grand_total=invoice.grand_total,
                components_complete=invoice.total_components_complete,
                tolerance=self.total_tolerance,
            )
            if not reconciliation.matches and reconciliation.components_complete:
                errors.append(
                    f"grand_total {invoice.grand_total:.2f} does not equal visible invoice components "
                    f"{reconciliation.expected_total:.2f}"
                )
            elif not reconciliation.matches:
                warnings.append("Total could not be fully reconciled from visible components.")

            if errors:
                status = InvoiceValidationStatus.FAILED
            elif warnings:
                status = InvoiceValidationStatus.NEEDS_REVIEW
            else:
                status = InvoiceValidationStatus.PASSED

            output = InvoiceValidationOutput(
                invoice_id=request.invoice_id,
                validation_status=status,
                errors=errors,
                warnings=warnings,
            )
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="invoice.validated",
                    entity_type="invoice",
                    entity_id=request.invoice_id,
                    metadata={
                        "status": status,
                        "error_count": len(errors),
                        "warning_count": len(warnings),
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="invoice.validated",
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
                    error_type=ErrorCategory.VALIDATION,
                    error_message=str(exc),
                    retry_count=0,
                    context={"invoice_id": str(request.invoice_id)},
                )
            )
            raise
