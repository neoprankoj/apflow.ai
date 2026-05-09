from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.agents.data.invoice_extraction_agent import InvoiceExtractionAgent
from app.agents.data.invoice_ingestion_agent import InvoiceIngestionAgent
from app.agents.data.invoice_normalization_agent import InvoiceNormalizationAgent
from app.agents.interface.notification_agent import NotificationAgent
from app.agents.logic.approval_routing_agent import ApprovalRoutingAgent
from app.agents.logic.duplicate_detection_agent import DuplicateDetectionAgent
from app.agents.logic.fraud_risk_scoring_agent import FraudRiskScoringAgent
from app.agents.logic.invoice_validation_agent import InvoiceValidationAgent
from app.agents.logic.purchase_order_matching_agent import PurchaseOrderMatchingAgent
from app.agents.logic.supplier_identity_agent import SupplierIdentityAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.core.schemas import (
    ActorType,
    ApprovalRoute,
    ApprovalRoutingInput,
    ApprovalTaskStatus,
    AuditEventInput,
    CanonicalInvoice,
    DuplicateDetectionInput,
    FraudRiskScoringInput,
    InvoiceExtractionInput,
    InvoiceIngestionInput,
    InvoiceIngestionMetadata,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    InvoiceNormalizationInput,
    InvoiceSource,
    InvoiceValidationInput,
    NotificationInput,
    NotificationType,
    PurchaseOrderLine,
    PurchaseOrderMatchingInput,
    SupplierIdentityInput,
    HumanReviewFieldIssue,
    HumanReviewStatus,
    HumanReviewTask,
    UploadedInvoiceDocument,
)
from app.db.models import Base
from app.db.repositories import SQLAlchemyAPRepository


@pytest.fixture
def sql_repository():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)()
    return SQLAlchemyAPRepository(session)


def test_sqlalchemy_models_create_phase4_tables():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())

    assert "tenants" in tables
    assert "tenant_memberships" in tables
    assert "invoices" in tables
    assert "invoice_line_items" in tables
    assert "purchase_orders" in tables
    assert "purchase_order_line_items" in tables
    assert "approval_policies" in tables
    assert "approval_tasks" in tables
    assert "notification_events" in tables
    assert "audit_events" in tables
    assert "workflow_states" in tables
    assert "erp_connection_configs" in tables
    assert "erp_sync_logs" in tables
    assert "erp_external_references" in tables
    assert "human_review_tasks" in tables
    assert "uploaded_invoice_documents" in tables
    assert "vendor_portal_access" in tables
    assert "vendor_messages" in tables


def test_sql_repository_preserves_invoice_tenant_isolation(sql_repository):
    tenant_a = uuid4()
    tenant_b = uuid4()
    output = InvoiceNormalizationOutput(
        tenant_id=tenant_a,
        canonical_invoice=CanonicalInvoice(
            invoice_number="INV-SQL-1",
            supplier_name="Northstar Components",
            invoice_date="2026-05-05",
            currency="USD",
            subtotal=100,
            tax_total=17,
            grand_total=117,
            line_items=[
                InvoiceLineItem(
                    description="Line",
                    quantity=1,
                    unit_price=100,
                    tax_amount=17,
                    total=117,
                )
            ],
        ),
        file_checksum="checksum-1",
    )

    sql_repository.store_invoice(output)

    assert len(sql_repository.list_invoices(tenant_a)) == 1
    assert sql_repository.list_invoices(tenant_b) == []


def test_sql_repository_persists_purchase_orders(sql_repository):
    tenant_id = uuid4()
    vendor = sql_repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-1")

    po = sql_repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-SQL-1",
        vendor_id=vendor.vendor_id,
        total_amount=117,
        lines=[PurchaseOrderLine(description="Line", quantity=1, unit_price=100, total=117)],
    )

    fetched = sql_repository.get_purchase_order_by_number(tenant_id, "PO-SQL-1")
    assert fetched == po
    assert len(sql_repository.list_purchase_orders(tenant_id)) == 1


def test_sql_repository_persists_approval_tasks(sql_repository):
    tenant_id = uuid4()
    invoice_id = uuid4()

    task = sql_repository.create_approval_task(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        route=ApprovalRoute.MANAGER_APPROVAL,
        assigned_role="finance_manager",
        status=ApprovalTaskStatus.PENDING,
        reason="Amount requires manager approval.",
    )

    assert sql_repository.list_approval_tasks(tenant_id)[0] == task
    assert sql_repository.list_approval_tasks(uuid4()) == []


def test_sql_repository_persists_notification_events(sql_repository):
    tenant_id = uuid4()
    invoice_id = uuid4()
    notification_id = uuid4()

    event = sql_repository.store_notification_event(
        tenant_id=tenant_id,
        notification_id=notification_id,
        invoice_id=invoice_id,
        notification_type=NotificationType.APPROVAL_REQUIRED,
        recipient_role="controller",
        status="sent",
        channel="mock",
        payload={"invoice_number": "INV-1"},
    )

    assert sql_repository.list_notification_events(tenant_id)[0] == event
    assert sql_repository.list_notification_events(uuid4()) == []


def test_sql_repository_persists_audit_events(sql_repository):
    tenant_id = uuid4()
    audit_agent = AuditLoggingAgent(repository=sql_repository)
    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.AGENT,
            actor_id="AuditLoggingAgent",
            action="test.persisted",
            entity_type="invoice",
            entity_id=uuid4(),
        )
    )

    events = sql_repository.list_audit_events(tenant_id)
    assert len(events) == 1
    assert events[0].action == "test.persisted"


def test_sql_repository_persists_human_review_tasks(sql_repository):
    tenant_id = uuid4()
    task = HumanReviewTask(
        tenant_id=tenant_id,
        status=HumanReviewStatus.REVIEW_REQUIRED,
        issues=[
            HumanReviewFieldIssue(
                field_name="invoice_number",
                issue_type="low_confidence",
                message="Needs review.",
                confidence=0.5,
            )
        ],
    )

    sql_repository.store_review_task(task)
    fetched = sql_repository.get_review_task(tenant_id, task.task_id)

    assert fetched.task_id == task.task_id
    assert fetched.status == HumanReviewStatus.REVIEW_REQUIRED
    assert sql_repository.list_review_tasks(uuid4()) == []


def test_sql_repository_persists_uploaded_documents(sql_repository):
    tenant_id = uuid4()
    document = UploadedInvoiceDocument(
        tenant_id=tenant_id,
        original_file_name="invoice.pdf",
        content_type="application/pdf",
        size_bytes=128,
        storage_provider="filesystem",
        storage_key=f"{tenant_id}/invoice.pdf",
        uploaded_by="ap@example.com",
    )

    stored = sql_repository.store_uploaded_document(document)
    fetched = sql_repository.get_uploaded_document(tenant_id, stored.document_id)

    assert fetched.document_id == stored.document_id
    assert fetched.original_file_name == "invoice.pdf"
    assert fetched.storage_key == f"{tenant_id}/invoice.pdf"
    assert len(sql_repository.list_uploaded_documents(tenant_id)) == 1
    assert sql_repository.list_uploaded_documents(uuid4()) == []


def test_sql_repository_full_pipeline_persists_runtime_outputs(sql_repository):
    tenant_id = uuid4()
    audit = AuditLoggingAgent(repository=sql_repository)
    monitoring = MonitoringAgent()
    error_handler = ErrorHandlerAgent(audit_agent=audit, monitoring_agent=monitoring)
    ingestion = InvoiceIngestionAgent(sql_repository, audit, monitoring, error_handler)
    extraction_agent = InvoiceExtractionAgent(sql_repository, audit, monitoring, error_handler)
    normalization = InvoiceNormalizationAgent(sql_repository, audit, monitoring, error_handler)
    supplier_agent = SupplierIdentityAgent(sql_repository, audit, monitoring, error_handler)
    validation_agent = InvoiceValidationAgent(audit, monitoring, error_handler)
    duplicate_agent = DuplicateDetectionAgent(sql_repository, audit, monitoring, error_handler)
    po_agent = PurchaseOrderMatchingAgent(sql_repository, audit, monitoring, error_handler)
    risk_agent = FraudRiskScoringAgent(audit, monitoring, error_handler)
    approval_agent = ApprovalRoutingAgent(sql_repository, audit, monitoring, error_handler)
    notification_agent = NotificationAgent(sql_repository, audit, monitoring, error_handler)

    vendor = sql_repository.add_vendor(tenant_id=tenant_id, name="Northstar Components", tax_id="TAX-12345")
    sql_repository.add_purchase_order(
        tenant_id=tenant_id,
        po_number="PO-SQL-PIPE",
        vendor_id=vendor.vendor_id,
        total_amount=1170,
        lines=[
            PurchaseOrderLine(
                description="Mock extracted invoice line",
                quantity=1,
                unit_price=1000,
                total=1170,
            )
        ],
    )

    payload = InvoiceIngestionInput(
        tenant_id=tenant_id,
        source=InvoiceSource.UPLOAD,
        file_url="mock://incoming/invoice.pdf",
        metadata=InvoiceIngestionMetadata(original_filename="invoice.pdf", mime_type="application/pdf"),
        content=(
            "invoice_number=INV-SQL-PIPE supplier_name=Northstar Components "
            "supplier_tax_id=TAX-12345 subtotal=1000 tax_total=170 grand_total=1170 "
            "currency=USD invoice_date=2026-05-05 po_number=PO-SQL-PIPE"
        ),
    )
    raw = ingestion.ingest(payload)
    extraction = extraction_agent.extract(
        InvoiceExtractionInput(
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            storage_url=raw.storage_url,
            mime_type=raw.mime_type,
        )
    )
    normalized = normalization.normalize(
        InvoiceNormalizationInput(
            extraction_id=extraction.extraction_id,
            raw_invoice_id=raw.raw_invoice_id,
            tenant_id=tenant_id,
            fields=extraction.fields,
            line_items=extraction.line_items,
            confidence=extraction.confidence,
            file_checksum=raw.file_checksum,
        )
    )
    supplier = supplier_agent.match_supplier(
        SupplierIdentityInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            supplier_name=normalized.canonical_invoice.supplier_name,
            supplier_tax_id=normalized.canonical_invoice.supplier_tax_id,
        )
    )
    validation = validation_agent.validate(
        InvoiceValidationInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            canonical_invoice=normalized.canonical_invoice,
            vendor_id=supplier.vendor_id,
        )
    )
    duplicate = duplicate_agent.detect(
        DuplicateDetectionInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_number=normalized.canonical_invoice.invoice_number,
            invoice_date=normalized.canonical_invoice.invoice_date,
            grand_total=normalized.canonical_invoice.grand_total,
            file_checksum=normalized.file_checksum,
        )
    )
    po_match = po_agent.match(
        PurchaseOrderMatchingInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            po_number=normalized.canonical_invoice.po_number,
            invoice_lines=normalized.canonical_invoice.line_items,
            invoice_total=normalized.canonical_invoice.grand_total,
            currency=normalized.canonical_invoice.currency,
        )
    )
    risk = risk_agent.score(
        FraudRiskScoringInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            vendor_id=supplier.vendor_id,
            invoice_total=normalized.canonical_invoice.grand_total,
            duplicate_result=duplicate,
            supplier_result=supplier,
            po_match_result=po_match,
            validation_result=validation,
        )
    )
    approval = approval_agent.route(
        ApprovalRoutingInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            amount=normalized.canonical_invoice.grand_total,
            match_status=po_match.match_status,
            risk_level=risk.risk_level,
            validation_status=validation.validation_status,
            duplicate_status=duplicate.status,
        )
    )
    notification_agent.send(
        NotificationInput(
            tenant_id=tenant_id,
            invoice_id=normalized.invoice_id,
            notification_type=NotificationType.APPROVAL_REQUIRED,
            recipient_role=approval.assigned_role,
        )
    )

    assert len(sql_repository.list_invoices(tenant_id)) == 1
    assert len(sql_repository.list_approval_tasks(tenant_id)) == 1
    assert len(sql_repository.list_notification_events(tenant_id)) == 1
    assert len(sql_repository.list_audit_events(tenant_id)) >= 8
