from uuid import uuid4

from app.core.schemas import (
    ApprovalRoute,
    ApprovalRoutingInput,
    ApprovalTaskStatus,
    CanonicalInvoice,
    DuplicateDetectionOutput,
    DuplicateStatus,
    FraudRiskScoringInput,
    InvoiceLineItem,
    InvoiceValidationOutput,
    InvoiceValidationStatus,
    NotificationInput,
    NotificationType,
    POMatchRecommendedAction,
    POMatchStatus,
    PurchaseOrderLine,
    PurchaseOrderMatchingInput,
    PurchaseOrderMatchingOutput,
    RiskLevel,
    SupplierIdentityOutput,
    SupplierMatchStatus,
)


def _validation(invoice_id, status=InvoiceValidationStatus.PASSED):
    return InvoiceValidationOutput(invoice_id=invoice_id, validation_status=status)


def _duplicate(invoice_id, status=DuplicateStatus.CLEAR, score=0):
    return DuplicateDetectionOutput(invoice_id=invoice_id, duplicate_score=score, status=status)


def _supplier(invoice_id, vendor_id, status=SupplierMatchStatus.MATCHED):
    return SupplierIdentityOutput(
        invoice_id=invoice_id,
        vendor_id=vendor_id,
        match_confidence=1 if status == SupplierMatchStatus.MATCHED else 0,
        status=status,
    )


def _po_match(invoice_id, status=POMatchStatus.MATCHED):
    return PurchaseOrderMatchingOutput(
        invoice_id=invoice_id,
        match_status=status,
        recommended_action=POMatchRecommendedAction.AUTO_APPROVE
        if status == POMatchStatus.MATCHED
        else POMatchRecommendedAction.REQUEST_REVIEW,
    )


def test_purchase_order_matching_returns_matched_for_clean_two_way_match(
    tenant_id,
    repository,
    purchase_order_matching_agent,
):
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")
    po = repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-100",
        vendor_id=vendor.vendor_id,
        total_amount=1170,
        lines=[PurchaseOrderLine(description="Line", quantity=1, unit_price=1000, total=1170)],
    )

    output = purchase_order_matching_agent.match(
        PurchaseOrderMatchingInput(
            tenant_id=tenant_id,
            invoice_id=uuid4(),
            vendor_id=vendor.vendor_id,
            po_number=po.po_number,
            invoice_lines=[InvoiceLineItem(description="Line", quantity=1, total=1170)],
            invoice_total=1170,
        )
    )

    assert output.match_status == POMatchStatus.MATCHED
    assert output.recommended_action == POMatchRecommendedAction.AUTO_APPROVE
    assert output.is_three_way_ready is True


def test_purchase_order_matching_flags_vendor_mismatch(
    tenant_id,
    repository,
    purchase_order_matching_agent,
):
    po_vendor = repository.add_vendor(tenant_id=tenant_id, name="PO Vendor", tax_id="PO-TAX")
    invoice_vendor = repository.add_vendor(tenant_id=tenant_id, name="Invoice Vendor", tax_id="INV-TAX")
    repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-MISMATCH",
        vendor_id=po_vendor.vendor_id,
        total_amount=1170,
    )

    output = purchase_order_matching_agent.match(
        PurchaseOrderMatchingInput(
            tenant_id=tenant_id,
            invoice_id=uuid4(),
            vendor_id=invoice_vendor.vendor_id,
            po_number="PO-MISMATCH",
            invoice_total=1170,
        )
    )

    assert output.match_status == POMatchStatus.VENDOR_MISMATCH
    assert output.recommended_action == POMatchRecommendedAction.BLOCK


def test_fraud_risk_scoring_raises_high_risk_for_likely_duplicate(
    tenant_id,
    fraud_risk_scoring_agent,
):
    invoice_id = uuid4()
    vendor_id = uuid4()

    output = fraud_risk_scoring_agent.score(
        FraudRiskScoringInput(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            vendor_id=vendor_id,
            invoice_total=1170,
            duplicate_result=_duplicate(invoice_id, DuplicateStatus.LIKELY_DUPLICATE, 1.0),
            supplier_result=_supplier(invoice_id, vendor_id),
            po_match_result=_po_match(invoice_id),
            validation_result=_validation(invoice_id),
        )
    )

    assert output.risk_level == RiskLevel.HIGH
    assert "Likely duplicate" in output.reasons[0]


def test_approval_routing_sends_high_amount_to_controller(
    tenant_id,
    approval_routing_agent,
):
    output = approval_routing_agent.route(
        ApprovalRoutingInput(
            tenant_id=tenant_id,
            invoice_id=uuid4(),
            amount=46000,
            match_status=POMatchStatus.MATCHED,
            risk_level=RiskLevel.LOW,
            validation_status=InvoiceValidationStatus.PASSED,
            duplicate_status=DuplicateStatus.CLEAR,
        )
    )

    assert output.route == ApprovalRoute.CONTROLLER_APPROVAL
    assert output.assigned_role == "controller"
    assert output.approval_status == ApprovalTaskStatus.PENDING


def test_notification_agent_stores_mock_event(
    tenant_id,
    repository,
    notification_agent,
):
    invoice_id = uuid4()
    output = notification_agent.send(
        NotificationInput(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            notification_type=NotificationType.APPROVAL_REQUIRED,
            recipient_role="controller",
            payload={"invoice_number": "INV-1"},
        )
    )

    events = repository.list_notification_events(tenant_id)
    assert output.status == "sent"
    assert len(events) == 1
    assert events[0].notification_type == NotificationType.APPROVAL_REQUIRED
