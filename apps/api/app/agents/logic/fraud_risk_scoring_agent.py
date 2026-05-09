from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    DuplicateStatus,
    ErrorCategory,
    FraudRecommendedAction,
    FraudRiskScoringInput,
    FraudRiskScoringOutput,
    InvoiceValidationStatus,
    MetricEventInput,
    POMatchStatus,
    RiskLevel,
    SupplierMatchStatus,
    WorkflowErrorInput,
)


class FraudRiskScoringAgent(BaseAgent[FraudRiskScoringInput, FraudRiskScoringOutput]):
    name = "FraudRiskScoringAgent"
    responsibility = "Score invoices and supplier events for deterministic fraud/anomaly risk."

    def __init__(
        self,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
    ) -> None:
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent

    def score(self, request: FraudRiskScoringInput) -> FraudRiskScoringOutput:
        try:
            risk_score, reasons = self._calculate(request)
            risk_level = self._level_for(risk_score)
            if risk_level == RiskLevel.CRITICAL:
                action = FraudRecommendedAction.BLOCK_PAYMENT
            elif risk_level in {RiskLevel.HIGH, RiskLevel.MEDIUM}:
                action = FraudRecommendedAction.MANAGER_REVIEW
            else:
                action = FraudRecommendedAction.CONTINUE

            output = FraudRiskScoringOutput(
                invoice_id=request.invoice_id,
                risk_score=risk_score,
                risk_level=risk_level,
                reasons=reasons,
                recommended_action=action,
            )
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="fraud.risk_scored",
                    entity_type="invoice",
                    entity_id=request.invoice_id,
                    metadata={
                        "risk_score": risk_score,
                        "risk_level": risk_level,
                        "reasons": reasons,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="fraud.risk_scored",
                    value=risk_score,
                    metadata={"risk_level": risk_level},
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

    def _calculate(self, request: FraudRiskScoringInput) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        if request.validation_result.validation_status == InvoiceValidationStatus.FAILED:
            score += 35
            reasons.append("Validation failed.")
        elif request.validation_result.validation_status == InvoiceValidationStatus.NEEDS_REVIEW:
            score += 15
            reasons.append("Validation requires review.")

        if request.duplicate_result.status == DuplicateStatus.LIKELY_DUPLICATE:
            score += 55
            reasons.append("Likely duplicate invoice detected.")
        elif request.duplicate_result.status == DuplicateStatus.POSSIBLE_DUPLICATE:
            score += 25
            reasons.append("Possible duplicate invoice detected.")

        if request.supplier_result.status == SupplierMatchStatus.UNKNOWN_VENDOR:
            score += 25
            reasons.append("Supplier is unknown.")
        elif request.supplier_result.status == SupplierMatchStatus.POSSIBLE_MATCH:
            score += 10
            reasons.append("Supplier match is uncertain.")

        po_status = request.po_match_result.match_status
        if po_status == POMatchStatus.VENDOR_MISMATCH:
            score += 35
            reasons.append("PO vendor does not match invoice vendor.")
        elif po_status == POMatchStatus.MISSING_PO:
            score += 20
            reasons.append("No matching purchase order was found.")
        elif po_status in {POMatchStatus.AMOUNT_VARIANCE, POMatchStatus.QUANTITY_VARIANCE}:
            score += 20
            reasons.append("PO variance requires exception review.")
        elif po_status == POMatchStatus.PARTIAL_MATCH:
            score += 10
            reasons.append("PO only partially matches invoice.")

        if request.invoice_total > 50000:
            score += 20
            reasons.append("Invoice amount exceeds controller review threshold.")
        elif request.invoice_total > 10000:
            score += 10
            reasons.append("Invoice amount exceeds manager review threshold.")

        if not reasons:
            reasons.append("No material risk signals detected.")

        return min(score, 100), reasons

    def _level_for(self, score: int) -> RiskLevel:
        if score >= 75:
            return RiskLevel.CRITICAL
        if score >= 50:
            return RiskLevel.HIGH
        if score >= 25:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
