from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    ApprovalRoute,
    ApprovalRoutingInput,
    ApprovalRoutingOutput,
    ApprovalTaskStatus,
    AuditEventInput,
    DuplicateStatus,
    ErrorCategory,
    InvoiceValidationStatus,
    MetricEventInput,
    POMatchStatus,
    RiskLevel,
    WorkflowErrorInput,
)


class ApprovalRoutingAgent(BaseAgent[ApprovalRoutingInput, ApprovalRoutingOutput]):
    name = "ApprovalRoutingAgent"
    responsibility = "Route invoices to approvers based on tenant policy and exception state."

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

    def route(self, request: ApprovalRoutingInput) -> ApprovalRoutingOutput:
        try:
            route, role, status, reason = self._route(request)
            task = self.repository.create_approval_task(
                tenant_id=request.tenant_id,
                invoice_id=request.invoice_id,
                route=route,
                assigned_role=role,
                status=status,
                reason=reason,
            )
            output = ApprovalRoutingOutput(
                invoice_id=request.invoice_id,
                approval_task_id=task.approval_task_id,
                route=route,
                assigned_role=role,
                approval_status=status,
                reason=reason,
            )
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="approval.routed",
                    entity_type="invoice",
                    entity_id=request.invoice_id,
                    metadata={
                        "route": route,
                        "assigned_role": role,
                        "approval_status": status,
                        "reason": reason,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="approval.routed",
                    value=1,
                    metadata={"route": route, "approval_status": status},
                )
            )
            return output
        except Exception as exc:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=request.tenant_id,
                    workflow_id=request.correlation_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.UNKNOWN,
                    error_message=str(exc),
                    retry_count=0,
                    context={"invoice_id": str(request.invoice_id)},
                )
            )
            raise

    def _route(
        self,
        request: ApprovalRoutingInput,
    ) -> tuple[ApprovalRoute, str, ApprovalTaskStatus, str]:
        policy = self.repository.get_approval_policy(request.tenant_id)

        if request.risk_level == RiskLevel.CRITICAL or (
            policy.high_risk_blocks and request.risk_level == RiskLevel.HIGH
        ):
            return (
                ApprovalRoute.BLOCKED,
                "ap_admin",
                ApprovalTaskStatus.BLOCKED,
                "Invoice blocked by risk policy.",
            )

        if request.duplicate_status == DuplicateStatus.LIKELY_DUPLICATE:
            return (
                ApprovalRoute.BLOCKED,
                "ap_admin",
                ApprovalTaskStatus.BLOCKED,
                "Likely duplicate invoice requires payment block.",
            )

        if request.validation_status == InvoiceValidationStatus.FAILED:
            return (
                ApprovalRoute.AP_REVIEW,
                "ap_specialist",
                ApprovalTaskStatus.PENDING,
                "Validation failed and requires AP review.",
            )

        if request.match_status in {
            POMatchStatus.MISSING_PO,
            POMatchStatus.PARTIAL_MATCH,
            POMatchStatus.AMOUNT_VARIANCE,
            POMatchStatus.QUANTITY_VARIANCE,
            POMatchStatus.VENDOR_MISMATCH,
            POMatchStatus.NEEDS_REVIEW,
        }:
            return (
                ApprovalRoute.AP_REVIEW,
                "ap_specialist",
                ApprovalTaskStatus.PENDING,
                "PO exception requires AP review.",
            )

        if request.amount > policy.manager_approval_limit:
            return (
                ApprovalRoute.CONTROLLER_APPROVAL,
                "controller",
                ApprovalTaskStatus.PENDING,
                "Amount exceeds manager approval limit.",
            )

        if request.amount > policy.auto_approve_limit or request.risk_level == RiskLevel.MEDIUM:
            return (
                ApprovalRoute.MANAGER_APPROVAL,
                "finance_manager",
                ApprovalTaskStatus.PENDING,
                "Amount or medium risk requires manager approval.",
            )

        return (
            ApprovalRoute.AUTO_APPROVE,
            "system",
            ApprovalTaskStatus.AUTO_APPROVED,
            "Invoice meets auto-approval policy.",
        )
