from uuid import UUID

from app.agents.base import BaseAgent
from app.agents.interface.vendor_communication_agent import VendorCommunicationAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository, InvoiceRecord
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    MetricEventInput,
    VendorChatIntent,
    VendorChatRequest,
    VendorChatResponse,
    WorkflowErrorInput,
)
from app.core.vendor_portal import invoice_is_visible_to_vendor, vendor_invoice_status


class PaymentStatusChatbotAgent(BaseAgent[VendorChatRequest, VendorChatResponse]):
    name = "PaymentStatusChatbotAgent"
    responsibility = "Answer vendor-safe invoice and payment status questions."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        vendor_communication_agent: VendorCommunicationAgent,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.vendor_communication_agent = vendor_communication_agent

    def answer(self, request: VendorChatRequest, vendor_id: UUID) -> VendorChatResponse:
        try:
            intent = self._classify_intent(request.question)
            invoice = self._resolve_invoice(request, vendor_id)
            response = self._response_for(request, invoice, intent)
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.VENDOR,
                    actor_id=request.sender_email or str(vendor_id),
                    action="vendor.chat",
                    entity_type="invoice" if invoice else "vendor",
                    entity_id=invoice.invoice_id if invoice else vendor_id,
                    metadata={
                        "intent": str(intent),
                        "invoice_id": str(invoice.invoice_id) if invoice else None,
                        "escalated": response.escalated,
                    },
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="vendor.chat",
                    value=1,
                    metadata={"intent": str(intent), "escalated": response.escalated},
                )
            )
            return response
        except Exception as exc:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=request.tenant_id,
                    workflow_id=request.invoice_id or vendor_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.SECURITY if isinstance(exc, PermissionError) else ErrorCategory.UNKNOWN,
                    error_message=str(exc),
                    retry_count=0,
                    context={"vendor_id": str(vendor_id)},
                )
            )
            raise

    def _resolve_invoice(self, request: VendorChatRequest, vendor_id: UUID) -> InvoiceRecord | None:
        invoices = [
            invoice
            for invoice in self.repository.list_invoices(request.tenant_id)
            if invoice_is_visible_to_vendor(invoice, vendor_id)
        ]
        if request.invoice_id is not None:
            invoice = next((item for item in invoices if item.invoice_id == request.invoice_id), None)
            if invoice is None:
                raise PermissionError("invoice is outside vendor scope")
            return invoice
        if request.invoice_number:
            return next(
                (
                    item
                    for item in invoices
                    if item.canonical_invoice.invoice_number.lower() == request.invoice_number.lower()
                ),
                None,
            )
        if len(invoices) == 1:
            return invoices[0]
        return None

    def _response_for(
        self,
        request: VendorChatRequest,
        invoice: InvoiceRecord | None,
        intent: VendorChatIntent,
    ) -> VendorChatResponse:
        if intent == VendorChatIntent.UNKNOWN:
            return VendorChatResponse(
                intent=intent,
                answer="I can only help with invoice receipt, review, missing information, and payment status. Please contact AP for this request.",
                escalated=True,
            )
        if invoice is None:
            return VendorChatResponse(
                intent=intent,
                answer="I cannot confirm that invoice from the available vendor records. Please contact AP with the invoice number.",
                escalated=True,
            )
        status = vendor_invoice_status(self.repository, request.tenant_id, invoice)
        invoice_number = status.invoice_number
        if intent == VendorChatIntent.PAYMENT_STATUS:
            if status.status in {"paid", "scheduled_for_payment"}:
                answer = f"Invoice {invoice_number} is {status.status.replace('_', ' ')}."
            else:
                answer = f"Invoice {invoice_number} is {status.status.replace('_', ' ')}; I cannot confirm a payment date yet."
        elif intent == VendorChatIntent.MISSING_INFORMATION:
            if status.missing_information:
                fields = ", ".join(status.missing_information)
                answer = f"Invoice {invoice_number} needs more information for: {fields}."
            else:
                answer = f"Invoice {invoice_number} does not show a current missing-information request."
        elif intent == VendorChatIntent.REJECTION_REASON_PUBLIC:
            answer = status.public_message
        elif intent == VendorChatIntent.APPROVAL_STATUS:
            answer = f"Invoice {invoice_number} is {status.status.replace('_', ' ')}."
        else:
            answer = f"Invoice {invoice_number} was received and is currently {status.status.replace('_', ' ')}."
        return VendorChatResponse(
            intent=intent,
            answer=answer,
            invoice_id=invoice.invoice_id,
            status=status.status,
            escalated=False,
        )

    def _classify_intent(self, question: str) -> VendorChatIntent:
        normalized = question.lower()
        if any(term in normalized for term in ("fraud", "risk", "audit", "approval policy", "erp log")):
            return VendorChatIntent.UNKNOWN
        if any(term in normalized for term in ("paid", "payment", "pay date", "scheduled")):
            return VendorChatIntent.PAYMENT_STATUS
        if any(term in normalized for term in ("approved", "approval", "review")):
            return VendorChatIntent.APPROVAL_STATUS
        if any(term in normalized for term in ("missing", "information", "documents", "correction")):
            return VendorChatIntent.MISSING_INFORMATION
        if any(term in normalized for term in ("reject", "rejected", "declined")):
            return VendorChatIntent.REJECTION_REASON_PUBLIC
        if any(term in normalized for term in ("received", "submitted", "got my invoice", "invoice")):
            return VendorChatIntent.INVOICE_RECEIVED
        return VendorChatIntent.UNKNOWN
