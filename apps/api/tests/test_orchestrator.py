from uuid import uuid4

from app.core.events import WorkflowEventType
from app.core.schemas import WorkflowEventInput, WorkflowStatus


def test_orchestrator_dispatches_invoice_received(orchestrator, audit_agent, monitoring_agent, tenant_id):
    event = WorkflowEventInput(
        tenant_id=tenant_id,
        workflow_id=uuid4(),
        event_type=WorkflowEventType.INVOICE_RECEIVED,
        entity_id=uuid4(),
        payload={"raw_invoice_id": str(uuid4())},
    )

    output = orchestrator.handle_event(event)

    assert output.next_agent == "InvoiceExtractionAgent"
    assert output.status == WorkflowStatus.QUEUED
    assert len(audit_agent.events) == 1
    assert len(monitoring_agent.metrics) == 1


def test_orchestrator_is_idempotent_for_replayed_events(orchestrator, tenant_id):
    event = WorkflowEventInput(
        tenant_id=tenant_id,
        workflow_id=uuid4(),
        event_type=WorkflowEventType.INVOICE_EXTRACTED,
        entity_id=uuid4(),
    )

    first = orchestrator.handle_event(event)
    second = orchestrator.handle_event(event)

    assert first.next_agent == "InvoiceNormalizationAgent"
    assert second.next_agent == first.next_agent
    assert second.context["idempotent_replay"] is True
