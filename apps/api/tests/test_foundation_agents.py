from uuid import uuid4

from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    ErrorResolutionAction,
    MetricEventInput,
    ResourceAction,
    SecurityDecisionInput,
    WorkflowErrorInput,
)


def test_tenant_security_denies_by_default(security_agent, tenant_id):
    decision = security_agent.authorize(
        SecurityDecisionInput(
            tenant_id=tenant_id,
            actor_id="user-1",
            actor_type=ActorType.USER,
            resource="invoice",
            action=ResourceAction.READ,
        )
    )

    assert decision.allowed is False
    assert decision.policy_id == "deny-by-default"


def test_tenant_security_allows_role_grant(security_agent, tenant_id):
    decision = security_agent.authorize(
        SecurityDecisionInput(
            tenant_id=tenant_id,
            actor_id="user-1",
            actor_type=ActorType.USER,
            resource="invoice",
            action=ResourceAction.APPROVE,
            context={"roles": ["approver"]},
        )
    )

    assert decision.allowed is True


def test_audit_logging_is_append_only(audit_agent, tenant_id):
    result = audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.AGENT,
            actor_id="AuditLoggingAgent",
            action="test.recorded",
            entity_type="invoice",
            entity_id=uuid4(),
        )
    )

    assert result.status == "recorded"
    assert len(audit_agent.events) == 1
    assert not hasattr(audit_agent, "delete")


def test_monitoring_agent_triggers_threshold_alert(monitoring_agent, tenant_id):
    output = monitoring_agent.record_metric(
        MetricEventInput(tenant_id=tenant_id, metric_event="agent.failure", value=1)
    )

    assert output.status == "alert_triggered"
    assert output.alerts


def test_error_handler_retries_transient_errors(error_handler_agent, tenant_id):
    workflow_id = uuid4()
    output = error_handler_agent.handle_error(
        WorkflowErrorInput(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            agent_name="InvoiceExtractionAgent",
            error_type=ErrorCategory.TRANSIENT,
            error_message="temporary OCR outage",
            retry_count=1,
        )
    )

    assert output.resolution == ErrorResolutionAction.RETRY
    assert output.next_attempt_at is not None
    assert output.notification_required is False


def test_error_handler_dead_letters_after_max_retries(error_handler_agent, tenant_id):
    output = error_handler_agent.handle_error(
        WorkflowErrorInput(
            tenant_id=tenant_id,
            workflow_id=uuid4(),
            agent_name="ERPConnectorAgent",
            error_type=ErrorCategory.INTEGRATION,
            error_message="persistent ERP failure",
            retry_count=3,
        )
    )

    assert output.resolution == ErrorResolutionAction.DEAD_LETTER
    assert output.notification_required is True
