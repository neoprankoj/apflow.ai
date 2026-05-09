from app.agents.base import BaseAgent
from app.core.schemas import AuditEventInput, AuditEventOutput, StoredAuditEvent


class AuditLoggingAgent(BaseAgent[AuditEventInput, AuditEventOutput]):
    name = "AuditLoggingAgent"
    responsibility = "Record immutable workflow events and user/agent decisions."

    def __init__(self, repository=None) -> None:
        self.repository = repository
        self._events: list[StoredAuditEvent] = []

    def record(self, event: AuditEventInput) -> AuditEventOutput:
        stored = StoredAuditEvent(**event.model_dump())
        self._events.append(stored)
        if self.repository is not None and hasattr(self.repository, "store_audit_event"):
            self.repository.store_audit_event(event, stored.audit_event_id)
        return AuditEventOutput(audit_event_id=stored.audit_event_id)

    @property
    def events(self) -> tuple[StoredAuditEvent, ...]:
        return tuple(self._events)
