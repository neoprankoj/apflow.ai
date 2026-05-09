from app.core.schemas import (
    ApprovalRoute,
    ApprovalRoutingInput,
    DuplicateDetectionInput,
    DuplicateStatus,
    FraudRiskScoringInput,
    InvoiceExtractionInput,
    InvoiceIngestionInput,
    InvoiceIngestionMetadata,
    InvoiceNormalizationInput,
    InvoiceSource,
    InvoiceValidationInput,
    NotificationInput,
    NotificationType,
    POMatchStatus,
    PurchaseOrderLine,
    PurchaseOrderMatchingInput,
    RiskLevel,
    SupplierIdentityInput,
)


def _payload(tenant_id, content: str) -> InvoiceIngestionInput:
    return InvoiceIngestionInput(
        tenant_id=tenant_id,
        source=InvoiceSource.UPLOAD,
        file_url="mock://incoming/invoice.pdf",
        metadata=InvoiceIngestionMetadata(original_filename="invoice.pdf", mime_type="application/pdf"),
        content=content,
    )


def _full_pipeline(
    tenant_id,
    content,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
    purchase_order_matching_agent,
    fraud_risk_scoring_agent,
    approval_routing_agent,
    notification_agent,
):
    payload = _payload(tenant_id, content)
    raw = invoice_ingestion_agent.ingest(payload)
    extraction = invoice_extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
            correlation_id=payload.correlation_id,
        )
    )
    normalized = invoice_normalization_agent.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            confidence=extraction.confidence,
            file_checksum=raw.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )
    invoice = normalized.canonical_invoice
    supplier = supplier_identity_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=invoice.supplier_name,
            supplier_tax_id=invoice.supplier_tax_id,
            correlation_id=payload.correlation_id,
        )
    )
    validation = invoice_validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            canonical_invoice=invoice,
            vendor_id=supplier.vendor_id,
            correlation_id=payload.correlation_id,
        )
    )
    duplicate = duplicate_detection_agent.detect(
        DuplicateDetectionInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_number=invoice.invoice_number,
            invoice_date=invoice.invoice_date,
            grand_total=invoice.grand_total,
            file_checksum=normalized.file_checksum,
            correlation_id=payload.correlation_id,
        )
    )
    po_match = purchase_order_matching_agent.match(
        PurchaseOrderMatchingInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            po_number=invoice.po_number,
            invoice_lines=invoice.line_items,
            invoice_total=invoice.grand_total,
            currency=invoice.currency,
            correlation_id=payload.correlation_id,
        )
    )
    fraud = fraud_risk_scoring_agent.score(
        FraudRiskScoringInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_total=invoice.grand_total,
            duplicate_result=duplicate,
            supplier_result=supplier,
            po_match_result=po_match,
            validation_result=validation,
            correlation_id=payload.correlation_id,
        )
    )
    approval = approval_routing_agent.route(
        ApprovalRoutingInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            amount=invoice.grand_total,
            match_status=po_match.match_status,
            risk_level=fraud.risk_level,
            validation_status=validation.validation_status,
            duplicate_status=duplicate.status,
            correlation_id=payload.correlation_id,
        )
    )

    notifications = []
    if validation.validation_status == "failed":
        notifications.append(
            notification_agent.send(
                NotificationInput(
                    tenant_id=tenant_id,
                    invoice_id=normalized.invoice_id,
                    notification_type=NotificationType.VALIDATION_FAILED,
                    recipient_role="ap_specialist",
                )
            )
        )
    if duplicate.status != DuplicateStatus.CLEAR:
        notifications.append(
            notification_agent.send(
                NotificationInput(
                    tenant_id=tenant_id,
                    invoice_id=normalized.invoice_id,
                    notification_type=NotificationType.DUPLICATE_DETECTED,
                    recipient_role="ap_admin",
                )
            )
        )
    if approval.route == ApprovalRoute.BLOCKED:
        notifications.append(
            notification_agent.send(
                NotificationInput(
                    tenant_id=tenant_id,
                    invoice_id=normalized.invoice_id,
                    notification_type=NotificationType.INVOICE_BLOCKED,
                    recipient_role="ap_admin",
                )
            )
        )
    elif approval.route != ApprovalRoute.AUTO_APPROVE:
        notifications.append(
            notification_agent.send(
                NotificationInput(
                    tenant_id=tenant_id,
                    invoice_id=normalized.invoice_id,
                    notification_type=NotificationType.APPROVAL_REQUIRED,
                    recipient_role=approval.assigned_role,
                )
            )
        )

    return {
        "invoice": normalized,
        "validation_result": validation,
        "duplicate_result": duplicate,
        "po_match_result": po_match,
        "fraud_risk_result": fraud,
        "approval_result": approval,
        "notifications": notifications,
    }


def _content(invoice_number, amount=1170, po_number="PO-100", supplier="Northstar Components", tax="TAX-12345"):
    subtotal = round(amount / 1.17, 2)
    tax_total = round(amount - subtotal, 2)
    return (
        f"invoice_number={invoice_number} supplier_name={supplier} supplier_tax_id={tax} "
        f"subtotal={subtotal} tax_total={tax_total} grand_total={amount} currency=USD "
        f"invoice_date=2026-05-05 po_number={po_number}"
    )


def test_full_pipeline_matched_po_invoice_routes_to_manager(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
    purchase_order_matching_agent,
    fraud_risk_scoring_agent,
    approval_routing_agent,
    notification_agent,
):
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")
    repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-100",
        vendor_id=vendor.vendor_id,
        total_amount=1170,
        lines=[PurchaseOrderLine(description="Mock extracted invoice line", quantity=1, unit_price=1000, total=1170)],
    )

    result = _full_pipeline(
        tenant_id,
        _content("INV-MATCHED-1"),
        invoice_ingestion_agent,
        invoice_extraction_agent,
        invoice_normalization_agent,
        supplier_identity_agent,
        invoice_validation_agent,
        duplicate_detection_agent,
        purchase_order_matching_agent,
        fraud_risk_scoring_agent,
        approval_routing_agent,
        notification_agent,
    )

    assert result["po_match_result"].match_status == POMatchStatus.MATCHED
    assert result["fraud_risk_result"].risk_level == RiskLevel.LOW
    assert result["approval_result"].route == ApprovalRoute.MANAGER_APPROVAL


def test_full_pipeline_duplicate_invoice_blocks_or_reviews(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
    purchase_order_matching_agent,
    fraud_risk_scoring_agent,
    approval_routing_agent,
    notification_agent,
):
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")
    repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-100",
        vendor_id=vendor.vendor_id,
        total_amount=1170,
    )
    kwargs = (
        invoice_ingestion_agent,
        invoice_extraction_agent,
        invoice_normalization_agent,
        supplier_identity_agent,
        invoice_validation_agent,
        duplicate_detection_agent,
        purchase_order_matching_agent,
        fraud_risk_scoring_agent,
        approval_routing_agent,
        notification_agent,
    )

    _full_pipeline(tenant_id, _content("INV-DUP-1"), *kwargs)
    second = _full_pipeline(tenant_id, _content("INV-DUP-1"), *kwargs)

    assert second["duplicate_result"].status == DuplicateStatus.LIKELY_DUPLICATE
    assert second["fraud_risk_result"].risk_level == RiskLevel.HIGH
    assert second["approval_result"].route == ApprovalRoute.BLOCKED


def test_full_pipeline_missing_po_routes_to_ap_review(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
    purchase_order_matching_agent,
    fraud_risk_scoring_agent,
    approval_routing_agent,
    notification_agent,
):
    repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")

    result = _full_pipeline(
        tenant_id,
        _content("INV-MISSING-PO", po_number="PO-DOES-NOT-EXIST"),
        invoice_ingestion_agent,
        invoice_extraction_agent,
        invoice_normalization_agent,
        supplier_identity_agent,
        invoice_validation_agent,
        duplicate_detection_agent,
        purchase_order_matching_agent,
        fraud_risk_scoring_agent,
        approval_routing_agent,
        notification_agent,
    )

    assert result["po_match_result"].match_status == POMatchStatus.MISSING_PO
    assert result["approval_result"].route == ApprovalRoute.AP_REVIEW


def test_full_pipeline_high_amount_invoice_routes_to_controller(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
    purchase_order_matching_agent,
    fraud_risk_scoring_agent,
    approval_routing_agent,
    notification_agent,
):
    vendor = repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")
    repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-HIGH",
        vendor_id=vendor.vendor_id,
        total_amount=46000,
        lines=[
            PurchaseOrderLine(
                description="Mock extracted invoice line",
                quantity=1,
                unit_price=39316.24,
                total=46000,
            )
        ],
    )

    result = _full_pipeline(
        tenant_id,
        _content("INV-HIGH-1", amount=46000, po_number="PO-HIGH"),
        invoice_ingestion_agent,
        invoice_extraction_agent,
        invoice_normalization_agent,
        supplier_identity_agent,
        invoice_validation_agent,
        duplicate_detection_agent,
        purchase_order_matching_agent,
        fraud_risk_scoring_agent,
        approval_routing_agent,
        notification_agent,
    )

    assert result["po_match_result"].match_status == POMatchStatus.MATCHED
    assert result["approval_result"].route == ApprovalRoute.CONTROLLER_APPROVAL


def test_full_pipeline_vendor_mismatch_is_flagged(
    tenant_id,
    repository,
    invoice_ingestion_agent,
    invoice_extraction_agent,
    invoice_normalization_agent,
    supplier_identity_agent,
    invoice_validation_agent,
    duplicate_detection_agent,
    purchase_order_matching_agent,
    fraud_risk_scoring_agent,
    approval_routing_agent,
    notification_agent,
):
    po_vendor = repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")
    repository.add_vendor(tenant_id=tenant_id, name="Other Components", tax_id="TAX-OTHER")
    repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-100",
        vendor_id=po_vendor.vendor_id,
        total_amount=1170,
    )

    result = _full_pipeline(
        tenant_id,
        _content("INV-MISMATCH-1", supplier="Other Components", tax="TAX-OTHER"),
        invoice_ingestion_agent,
        invoice_extraction_agent,
        invoice_normalization_agent,
        supplier_identity_agent,
        invoice_validation_agent,
        duplicate_detection_agent,
        purchase_order_matching_agent,
        fraud_risk_scoring_agent,
        approval_routing_agent,
        notification_agent,
    )

    assert result["po_match_result"].match_status == POMatchStatus.VENDOR_MISMATCH
    assert result["fraud_risk_result"].risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH}
    assert result["approval_result"].route in {ApprovalRoute.AP_REVIEW, ApprovalRoute.BLOCKED}
