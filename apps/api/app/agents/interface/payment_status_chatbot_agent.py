from uuid import UUID

from app.agents.base import BaseAgent
from app.agents.interface.vendor_communication_agent import VendorCommunicationAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    MetricEventInput,
    VendorChatRequest,
    VendorChatResponse,
    WorkflowErrorInput,
)
from app.services.vendor_payment_chatbot_service import VendorPaymentChatbotService


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
        self.chatbot_service = VendorPaymentChatbotService(repository)

    def answer(self, request: VendorChatRequest, vendor_id: UUID, vendor_name: str | None = None) -> VendorChatResponse:
        try:
            response = self.chatbot_service.answer(request, vendor_id, vendor_name)
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.VENDOR,
                    actor_id=request.sender_email or str(vendor_id),
                    action="vendor.chat_question_refused" if response.refused else "vendor.chat_question_answered",
                    entity_type="invoice" if response.invoice_id else "vendor",
                    entity_id=response.invoice_id or vendor_id,
                    metadata={
                        "intent": str(response.intent),
                        "matched_invoice_count": len(response.matched_invoice_ids),
                        "refused": response.refused,
                        "refusal_reason": response.refusal_reason,
                    },
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="vendor.chat",
                    value=1,
                    metadata={"intent": str(response.intent), "escalated": response.escalated},
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
