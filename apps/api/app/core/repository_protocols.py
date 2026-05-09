from typing import Protocol
from uuid import UUID

from app.core.repositories import (
    ApprovalTaskRecord,
    InvoiceRecord,
    NotificationEventRecord,
    PurchaseOrderOutput,
    VendorRecord,
)
from app.core.schemas import (
    ApprovalPolicy,
    ApprovalRoute,
    ApprovalTaskStatus,
    AuditEventInput,
    InvoiceIngestionOutput,
    InvoiceNormalizationOutput,
    NotificationType,
    PurchaseOrderLine,
)


class InvoiceRepository(Protocol):
    def store_raw_invoice(
        self,
        output: InvoiceIngestionOutput,
        content: str | bytes | None = None,
    ) -> None: ...

    def store_invoice(self, output: InvoiceNormalizationOutput) -> None: ...

    def update_invoice_vendor(self, tenant_id: UUID, invoice_id: UUID, vendor_id: UUID | None) -> None: ...

    def list_invoices(self, tenant_id: UUID) -> list[InvoiceRecord]: ...


class PurchaseOrderRepository(Protocol):
    def add_purchase_order(
        self,
        tenant_id: UUID,
        po_number: str,
        vendor_id: UUID,
        total_amount: float,
        lines: list[PurchaseOrderLine] | None = None,
        currency: str = "USD",
    ) -> PurchaseOrderOutput: ...

    def get_purchase_order_by_number(self, tenant_id: UUID, po_number: str) -> PurchaseOrderOutput | None: ...

    def list_purchase_orders(self, tenant_id: UUID) -> list[PurchaseOrderOutput]: ...


class ApprovalRepository(Protocol):
    def set_approval_policy(self, policy: ApprovalPolicy) -> None: ...

    def get_approval_policy(self, tenant_id: UUID) -> ApprovalPolicy: ...

    def create_approval_task(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        route: ApprovalRoute,
        assigned_role: str,
        status: ApprovalTaskStatus,
        reason: str,
        approval_task_id: UUID | None = None,
    ) -> ApprovalTaskRecord: ...

    def list_approval_tasks(self, tenant_id: UUID) -> list[ApprovalTaskRecord]: ...


class NotificationRepository(Protocol):
    def store_notification_event(
        self,
        tenant_id: UUID,
        notification_id: UUID,
        invoice_id: UUID,
        notification_type: NotificationType,
        recipient_role: str,
        status: str,
        channel: str,
        payload: dict,
    ) -> NotificationEventRecord: ...

    def list_notification_events(self, tenant_id: UUID) -> list[NotificationEventRecord]: ...


class AuditRepository(Protocol):
    def store_audit_event(self, event: AuditEventInput, audit_event_id: UUID) -> None: ...

    def list_audit_events(self, tenant_id: UUID): ...


class WorkflowRepository(Protocol):
    def list_workflow_states(self, tenant_id: UUID): ...


class APRepository(
    InvoiceRepository,
    PurchaseOrderRepository,
    ApprovalRepository,
    NotificationRepository,
    AuditRepository,
    WorkflowRepository,
    Protocol,
):
    def add_vendor(
        self,
        tenant_id: UUID,
        name: str,
        tax_id: str | None = None,
        bank_account_hash: str | None = None,
        vendor_id: UUID | None = None,
    ) -> VendorRecord: ...

    def list_vendors(self, tenant_id: UUID) -> list[VendorRecord]: ...

    def ensure_phase3_fixtures(self, tenant_id: UUID) -> None: ...
