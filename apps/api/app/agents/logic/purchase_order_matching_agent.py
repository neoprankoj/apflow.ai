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
    POMatchRecommendedAction,
    POMatchStatus,
    PurchaseOrderMatchingInput,
    PurchaseOrderMatchingOutput,
    VarianceDetail,
    WorkflowErrorInput,
)


class PurchaseOrderMatchingAgent(BaseAgent[PurchaseOrderMatchingInput, PurchaseOrderMatchingOutput]):
    name = "PurchaseOrderMatchingAgent"
    responsibility = "Perform 2-way and mock-ready 3-way PO matching."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        amount_tolerance: float = 2.0,
        quantity_tolerance: float = 0.01,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.amount_tolerance = amount_tolerance
        self.quantity_tolerance = quantity_tolerance

    def match(self, request: PurchaseOrderMatchingInput) -> PurchaseOrderMatchingOutput:
        try:
            output = self._match(request)
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=request.tenant_id,
                    actor_type=ActorType.AGENT,
                    actor_id=self.name,
                    action="po.matched",
                    entity_type="invoice",
                    entity_id=request.invoice_id,
                    metadata={
                        "match_status": output.match_status,
                        "recommended_action": output.recommended_action,
                        "variance_count": len(output.variance_details),
                        "matched_po_id": str(output.matched_po_id) if output.matched_po_id else None,
                        "correlation_id": str(request.correlation_id),
                    },
                    correlation_id=request.correlation_id,
                )
            )
            self.monitoring_agent.record_metric(
                MetricEventInput(
                    tenant_id=request.tenant_id,
                    metric_event="po.match",
                    value=1,
                    metadata={"match_status": output.match_status},
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
                    context={"invoice_id": str(request.invoice_id), "po_number": request.po_number},
                )
            )
            raise

    def _match(self, request: PurchaseOrderMatchingInput) -> PurchaseOrderMatchingOutput:
        if not request.po_number:
            return PurchaseOrderMatchingOutput(
                invoice_id=request.invoice_id,
                match_status=POMatchStatus.MISSING_PO,
                variance_details=[
                    VarianceDetail(
                        field="po_number",
                        expected="known purchase order",
                        actual=None,
                        message="Invoice does not include a PO number.",
                    )
                ],
                recommended_action=POMatchRecommendedAction.REQUEST_REVIEW,
            )

        po = self.repository.get_purchase_order_by_number(request.tenant_id, request.po_number)
        if po is None:
            return PurchaseOrderMatchingOutput(
                invoice_id=request.invoice_id,
                match_status=POMatchStatus.MISSING_PO,
                variance_details=[
                    VarianceDetail(
                        field="po_number",
                        expected=request.po_number,
                        actual=None,
                        message="No purchase order exists for this tenant and PO number.",
                    )
                ],
                recommended_action=POMatchRecommendedAction.REQUEST_REVIEW,
            )

        variances: list[VarianceDetail] = []
        if request.vendor_id and po.vendor_id != request.vendor_id:
            variances.append(
                VarianceDetail(
                    field="vendor_id",
                    expected=str(po.vendor_id),
                    actual=str(request.vendor_id),
                    message="Invoice vendor does not match the purchase order vendor.",
                )
            )
            return PurchaseOrderMatchingOutput(
                invoice_id=request.invoice_id,
                match_status=POMatchStatus.VENDOR_MISMATCH,
                variance_details=variances,
                recommended_action=POMatchRecommendedAction.BLOCK,
                matched_po_id=po.purchase_order_id,
                is_three_way_ready=True,
            )

        if po.currency != request.currency:
            variances.append(
                VarianceDetail(
                    field="currency",
                    expected=po.currency,
                    actual=request.currency,
                    message="Invoice currency differs from PO currency.",
                )
            )

        amount_delta = round(request.invoice_total - po.total_amount, 2)
        if abs(amount_delta) > self.amount_tolerance:
            variances.append(
                VarianceDetail(
                    field="total_amount",
                    expected=po.total_amount,
                    actual=request.invoice_total,
                    message=f"Invoice total differs from PO by {amount_delta:.2f}.",
                )
            )
            return PurchaseOrderMatchingOutput(
                invoice_id=request.invoice_id,
                match_status=POMatchStatus.AMOUNT_VARIANCE,
                variance_details=variances,
                recommended_action=POMatchRecommendedAction.ROUTE_EXCEPTION,
                matched_po_id=po.purchase_order_id,
                is_three_way_ready=True,
            )

        po_quantity = sum(line.quantity for line in po.lines)
        invoice_quantity = sum(line.quantity for line in request.invoice_lines)
        if po_quantity and abs(invoice_quantity - po_quantity) > self.quantity_tolerance:
            variances.append(
                VarianceDetail(
                    field="quantity",
                    expected=po_quantity,
                    actual=invoice_quantity,
                    message="Invoice quantity differs from PO quantity.",
                )
            )
            return PurchaseOrderMatchingOutput(
                invoice_id=request.invoice_id,
                match_status=POMatchStatus.QUANTITY_VARIANCE,
                variance_details=variances,
                recommended_action=POMatchRecommendedAction.ROUTE_EXCEPTION,
                matched_po_id=po.purchase_order_id,
                is_three_way_ready=True,
            )

        if len(request.invoice_lines) != len(po.lines):
            variances.append(
                VarianceDetail(
                    field="line_count",
                    expected=len(po.lines),
                    actual=len(request.invoice_lines),
                    message="Invoice line count differs from PO line count.",
                )
            )
            return PurchaseOrderMatchingOutput(
                invoice_id=request.invoice_id,
                match_status=POMatchStatus.PARTIAL_MATCH,
                variance_details=variances,
                recommended_action=POMatchRecommendedAction.REQUEST_REVIEW,
                matched_po_id=po.purchase_order_id,
                is_three_way_ready=True,
            )

        return PurchaseOrderMatchingOutput(
            invoice_id=request.invoice_id,
            match_status=POMatchStatus.MATCHED,
            variance_details=variances,
            recommended_action=POMatchRecommendedAction.AUTO_APPROVE,
            matched_po_id=po.purchase_order_id,
            is_three_way_ready=True,
        )
