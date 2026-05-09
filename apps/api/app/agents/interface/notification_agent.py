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
    NotificationInput,
    NotificationOutput,
    WorkflowErrorInput,
)


class MockNotificationAdapter:
    channel = "mock"

    def send(self, request: NotificationInput) -> str:
        return "sent"


class NotificationAgent(BaseAgent[NotificationInput, NotificationOutput]):
    name = "NotificationAgent"
    responsibility = "Send mock notifications and store tenant-scoped delivery events."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        adapter: MockNotificationAdapter | None = None,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.adapter = adapter or MockNotificationAdapter()

    def send(self, request: NotificationInput) -> NotificationOutput:
        try:
            status = self.adapter.send(request)
            output = NotificationOutput(
                invoice_id=request.invoice_id,
                status=status,
                channel=self.adapter.channel,
                notification_type=request.notification_type,
                recipient_role=request.recipient_role,
            )
            self.repository.store_notification_event(
                tenant_id=request.tenant_id,
                notification_id=output.notification_id,
                invoice_id=request.invoice_id,
                notification_type=request.notification_type,
                recipient_role=request.recipient_role,
                status=output.status,
                channel=output.channel,
                payload=request.payload,
            )
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="notification.sent",
                    entity_type="invoice",
                    entity_id=request.invoice_id,
                    metadata={
                        "notification_type": request.notification_type,
                        "recipient_role": request.recipient_role,
                        "status": status,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="notification.sent",
                    value=1,
                    metadata={
                        "notification_type": request.notification_type,
                        "recipient_role": request.recipient_role,
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
                    error_type=ErrorCategory.INTEGRATION,
                    error_message=str(exc),
                    retry_count=0,
                    context={"invoice_id": str(request.invoice_id)},
                )
            )
            raise
