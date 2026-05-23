from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ErrorCategory,
    HumanReviewCorrectionRequest,
    HumanReviewCorrectionResult,
    HumanReviewFieldIssue,
    HumanReviewStatus,
    HumanReviewTask,
    MetricEventInput,
    OCRExtractionResult,
    WorkflowErrorInput,
)
from app.core.totals import reconcile_total


REQUIRED_REVIEW_FIELDS = ["invoice_number", "supplier_name", "invoice_date", "currency", "grand_total"]


class HumanReviewAgent(BaseAgent[OCRExtractionResult, HumanReviewTask]):
    name = "HumanReviewAgent"
    responsibility = "Create and manage human review tasks for low-confidence invoice extraction."

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

    def inspect_extraction(
        self,
        ocr_result: OCRExtractionResult,
        raw_invoice_id=None,
        invoice_id=None,
    ) -> HumanReviewTask:
        try:
            issues = self._issues_for(ocr_result)
            status = HumanReviewStatus.REVIEW_REQUIRED if issues else HumanReviewStatus.NOT_REQUIRED
            task = HumanReviewTask(
                tenant_id=ocr_result.tenant_id,
                invoice_id=invoice_id,
                raw_invoice_id=raw_invoice_id,
                extraction_id=ocr_result.extraction_id,
                status=status,
                issues=issues,
                history=[{"action": str(status), "actor_id": self.name}],
            )
            if issues:
                self.repository.store_review_task(task)
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=ocr_result.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="review.inspected",
                    entity_type="ocr_extraction",
                    entity_id=ocr_result.extraction_id,
                    metadata={"status": status, "issue_count": len(issues)},
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=ocr_result.tenant_id,
                    metric_event="review.inspected",
                    value=len(issues),
                    metadata={"status": status},
                )
            )
            return task
        except Exception as exc:
            self.error_handler_agent.handle_error(
                WorkflowErrorInput(
                    tenant_id=ocr_result.tenant_id,
                    workflow_id=ocr_result.extraction_id,
                    agent_name=self.name,
                    error_type=ErrorCategory.UNKNOWN,
                    error_message=str(exc),
                    retry_count=0,
                )
            )
            raise

    def submit_corrections(
        self,
        task_id,
        request: HumanReviewCorrectionRequest,
    ) -> HumanReviewCorrectionResult:
        task = self.repository.apply_review_corrections(request.tenant_id, task_id, request)
        self.audit_agent.record(
            AuditEventInput(
                tenant_id=request.tenant_id,
                actor_type=ActorType.USER,
                actor_id=request.reviewer_id,
                action="review.corrected",
                entity_type="human_review_task",
                entity_id=task_id,
                metadata={"fields": list(request.corrections)},
            )
        )
        self.monitoring_agent.record_metric(
            MetricEventInput(
                tenant_id=request.tenant_id,
                metric_event="review.corrected",
                value=1,
                metadata={"field_count": len(request.corrections)},
            )
        )
        return HumanReviewCorrectionResult(
            task_id=task.task_id,
            status=task.status,
            corrected_fields=task.corrected_fields,
        )

    def approve(self, tenant_id, task_id) -> HumanReviewTask:
        return self.repository.update_review_task_status(
            tenant_id,
            task_id,
            HumanReviewStatus.CORRECTED,
            actor_id=self.name,
        )

    def reject(self, tenant_id, task_id) -> HumanReviewTask:
        return self.repository.update_review_task_status(
            tenant_id,
            task_id,
            HumanReviewStatus.REJECTED,
            actor_id=self.name,
        )

    def _issues_for(self, ocr_result: OCRExtractionResult) -> list[HumanReviewFieldIssue]:
        issues: list[HumanReviewFieldIssue] = []
        fields = {field.field_name: field for field in ocr_result.fields}
        for field_name in REQUIRED_REVIEW_FIELDS:
            field = fields.get(field_name)
            if field is None or field.value in (None, ""):
                issues.append(
                    HumanReviewFieldIssue(
                        field_name=field_name,
                        issue_type="missing_required_field",
                        message=f"{field_name} is required but was not extracted.",
                    )
                )
            elif field.confidence < 0.75:
                issues.append(
                    HumanReviewFieldIssue(
                        field_name=field_name,
                        issue_type="low_confidence",
                        message=f"{field_name} confidence is below review threshold.",
                        current_value=field.value,
                        confidence=field.confidence,
                    )
                )
        if ocr_result.error:
            issues.append(
                HumanReviewFieldIssue(
                    field_name="document",
                    issue_type="provider_failure",
                    message=ocr_result.error,
                    confidence=0,
                )
            )

        subtotal = fields.get("subtotal")
        grand_total = fields.get("grand_total")
        if subtotal and grand_total and subtotal.value not in (None, "") and grand_total.value not in (None, ""):
            tax_total = fields.get("tax_total")
            shipping_amount = fields.get("shipping_amount")
            fee_total = fields.get("fee_total")
            discount_total = fields.get("discount_total")
            optional_values = [tax_total, shipping_amount, fee_total, discount_total]
            components_complete = any(
                field is not None and field.value not in (None, "")
                for field in optional_values
            ) or round(float(subtotal.value or 0), 2) == round(float(grand_total.value or 0), 2)
            reconciliation = reconcile_total(
                subtotal=float(subtotal.value or 0),
                tax_total=float(tax_total.value or 0) if tax_total else 0,
                shipping_amount=float(shipping_amount.value or 0) if shipping_amount else 0,
                fee_total=float(fee_total.value or 0) if fee_total else 0,
                discount_total=float(discount_total.value or 0) if discount_total else 0,
                grand_total=float(grand_total.value or 0),
                components_complete=components_complete,
            )
            if not reconciliation.matches and reconciliation.components_complete:
                discount_note = (
                    " Discount was treated as a deduction."
                    if reconciliation.discount_deduction
                    else ""
                )
                issues.append(
                    HumanReviewFieldIssue(
                        field_name="grand_total",
                        issue_type="suspicious_totals",
                        message=(
                            f"Grand total mismatch: {reconciliation.formula_label} = "
                            f"{reconciliation.expected_total}, but grand total is "
                            f"{reconciliation.actual_total}.{discount_note}"
                        ),
                        current_value=reconciliation.actual_total,
                        confidence=grand_total.confidence,
                    )
                )
            elif not reconciliation.matches:
                issues.append(
                    HumanReviewFieldIssue(
                        field_name="grand_total",
                        issue_type="suspicious_totals",
                        message="Total could not be fully reconciled from visible components.",
                        current_value=reconciliation.actual_total,
                        confidence=grand_total.confidence,
                    )
                )
        return issues
