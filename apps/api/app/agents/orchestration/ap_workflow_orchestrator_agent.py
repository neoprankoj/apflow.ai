from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.events import NEXT_AGENT_BY_EVENT
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    MetricEventInput,
    OrchestratorOutput,
    WorkflowErrorInput,
    WorkflowEventInput,
    WorkflowState,
    WorkflowStatus,
)


class APWorkflowOrchestratorAgent(BaseAgent[WorkflowEventInput, OrchestratorOutput]):
    name = "APWorkflowOrchestratorAgent"
    responsibility = "Coordinate AP workflow state and dispatch the next agent task."

    def __init__(
        self,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        repository=None,
    ) -> None:
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.repository = repository
        self._states: dict[str, WorkflowState] = {}
        self._processed_events: set[str] = set()

    def handle_event(self, event: WorkflowEventInput) -> OrchestratorOutput:
        event_key = str(event.event_id)
        if event_key in self._processed_events:
            state = self._states[str(event.workflow_id)]
            return OrchestratorOutput(
                workflow_id=state.workflow_id,
                next_agent=state.current_agent or "",
                state=state.state,
                status=state.status,
                context={"idempotent_replay": True},
            )

        next_agent = NEXT_AGENT_BY_EVENT.get(event.event_type)
        if next_agent is None:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=event.tenant_id,
                    workflow_id=event.workflow_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.VALIDATION,
                    error_message=f"No next agent for event type {event.event_type}",
                    retry_count=0,
                    context={"event_id": str(event.event_id)},
                )
            )
            return OrchestratorOutput(
                workflow_id=event.workflow_id,
                next_agent="ErrorHandlerAgent",
                state="exception",
                status=WorkflowStatus.WAITING_FOR_HUMAN,
                context={"reason": "missing_next_agent"},
            )

        state = WorkflowState(
            workflow_id=event.workflow_id,
            tenant_id=event.tenant_id,
            state=str(event.event_type),
            status=WorkflowStatus.QUEUED,
            current_agent=next_agent,
        )
        self._states[str(event.workflow_id)] = state
        if self.repository is not None and hasattr(self.repository, "store_workflow_state"):
            self.repository.store_workflow_state(state)
        self._processed_events.add(event_key)

        self.audit_agent.record(
            AuditEventInput(
                tenant_id=event.tenant_id,
                actor_type=ActorType.AGENT,
                actor_id=self.name,
                action="workflow.dispatched",
                entity_type="workflow",
                entity_id=event.workflow_id,
                metadata={
                    "event_type": event.event_type,
                    "next_agent": next_agent,
                    "correlation_id": str(event.correlation_id),
                },
                correlation_id=event.correlation_id,
            )
        )
        self.monitoring_agent.record_metric(
            MetricEventInput(
                tenant_id=event.tenant_id,
                metric_event="workflow.event.dispatched",
                value=1,
                metadata={"event_type": event.event_type, "next_agent": next_agent},
            )
        )
        return OrchestratorOutput(
            workflow_id=event.workflow_id,
            next_agent=next_agent,
            state=state.state,
            status=state.status,
            context={"correlation_id": str(event.correlation_id)},
        )

    @property
    def states(self) -> tuple[WorkflowState, ...]:
        return tuple(self._states.values())
