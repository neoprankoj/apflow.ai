from datetime import UTC, datetime, timedelta

from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    ErrorResolutionAction,
    ErrorResolutionOutput,
    MetricEventInput,
    WorkflowErrorInput,
)


class ErrorHandlerAgent(BaseAgent[WorkflowErrorInput, ErrorResolutionOutput]):
    name = "ErrorHandlerAgent"
    responsibility = "Classify workflow failures, apply retries, and route dead-letter escalation."

    def __init__(
        self,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        max_retries: int = 3,
    ) -> None:
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.max_retries = max_retries

    def handle_error(self, error: WorkflowErrorInput) -> ErrorResolutionOutput:
        if error.error_type == ErrorCategory.SECURITY:
            output = ErrorResolutionOutput(
                resolution=ErrorResolutionAction.ESCALATE,
                notification_required=True,
            )
        elif error.error_type == ErrorCategory.VALIDATION:
            output = ErrorResolutionOutput(
                resolution=ErrorResolutionAction.MANUAL_REVIEW,
                notification_required=True,
            )
        elif error.error_type in {ErrorCategory.TRANSIENT, ErrorCategory.INTEGRATION}:
            output = self._retry_or_dead_letter(error)
        else:
            output = ErrorResolutionOutput(
                resolution=ErrorResolutionAction.ESCALATE,
                notification_required=True,
            )

        self.monitoring_agent.record_metric(
            MetricEventInput(
                tenant_id=error.tenant_id,
                metric_event="agent.failure",
                value=1,
                metadata={"agent_name": error.agent_name, "error_type": error.error_type},
            )
        )
        self.audit_agent.record(
            AuditEventInput(
                tenant_id=error.tenant_id,
                actor_type=ActorType.AGENT,
                actor_id=self.name,
                action="error.classified",
                entity_type="workflow",
                entity_id=error.workflow_id,
                metadata={
                    "agent_name": error.agent_name,
                    "error_type": error.error_type,
                    "resolution": output.resolution,
                    "retry_count": error.retry_count,
                },
            )
        )
        return output

    def _retry_or_dead_letter(self, error: WorkflowErrorInput) -> ErrorResolutionOutput:
        if error.retry_count >= self.max_retries:
            return ErrorResolutionOutput(
                resolution=ErrorResolutionAction.DEAD_LETTER,
                notification_required=True,
            )

        delay_seconds = 2 ** error.retry_count * 60
        return ErrorResolutionOutput(
            resolution=ErrorResolutionAction.RETRY,
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=delay_seconds),
            notification_required=False,
        )
