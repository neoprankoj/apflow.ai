from uuid import UUID

from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    MetricEventInput,
    NotificationType,
    VendorMessageCreate,
    VendorMessageResult,
    WorkflowErrorInput,
)


class VendorCommunicationAgent(BaseAgent[VendorMessageCreate, VendorMessageResult]):
    name = "VendorCommunicationAgent"
    responsibility = "Store vendor messages and notify AP teams without sending real email."

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

    def submit_message(self, request: VendorMessageCreate, vendor_id: UUID) -> VendorMessageResult:
        try:
            if request.invoice_id is not None:
                invoice = self.repository.get_invoice(request.tenant_id, request.invoice_id)
                if invoice.vendor_id != vendor_id:
                    raise PermissionError("invoice is outside vendor scope")
            result = VendorMessageResult(
                tenant_id=request.tenant_id,
                vendor_id=vendor_id,
                invoice_id=request.invoice_id,
                sender_email=request.sender_email,
                message=request.message,
                status="submitted",
            )
            self.repository.store_vendor_message(result)
            if request.invoice_id is not None:
                self.repository.store_notification_event(
                    tenant_id=request.tenant_id,
                    notification_id=result.message_id,
                    invoice_id=request.invoice_id,
                    notification_type=NotificationType.VENDOR_MESSAGE_RECEIVED,
                    recipient_role="ap_team",
                    status="sent",
                    channel="mock",
                    payload={"sender_email": request.sender_email, "message_id": str(result.message_id)},
                )
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.VENDOR,
                    actor_id=request.sender_email,
                    action="vendor.message_submitted",
                    entity_type="vendor_message",
                    entity_id=result.message_id,
                    metadata={
                        "vendor_id": str(vendor_id),
                        "invoice_id": str(request.invoice_id) if request.invoice_id else None,
                    },
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="vendor.message_submitted",
                    value=1,
                    metadata={"vendor_id": str(vendor_id)},
                )
            )
            return result
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
