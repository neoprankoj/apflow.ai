import hashlib
import secrets
from uuid import UUID

from app.core.repositories import InMemoryAPRepository, InvoiceRecord
from app.core.schemas import (
    ApprovalRoute,
    ApprovalTaskStatus,
    ERPOperation,
    VendorInvoiceListItem,
    VendorInvoiceStatus,
    VendorSafeStatus,
)


def generate_vendor_access_token() -> str:
    return secrets.token_urlsafe(32)


def hash_vendor_access_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invoice_is_visible_to_vendor(invoice: InvoiceRecord, vendor_id: UUID) -> bool:
    return invoice.vendor_id == vendor_id


def map_vendor_invoice_status(
    repository: InMemoryAPRepository,
    tenant_id: UUID,
    invoice: InvoiceRecord,
) -> VendorSafeStatus:
    payment_status = get_vendor_payment_status(repository, tenant_id, invoice.invoice_id)
    if payment_status in {"paid", "settled"}:
        return VendorSafeStatus.PAID
    if payment_status in {"scheduled", "scheduled_for_payment", "processing"}:
        return VendorSafeStatus.SCHEDULED_FOR_PAYMENT

    review_tasks = [
        task
        for task in repository.list_review_tasks(tenant_id)
        if task.invoice_id == invoice.invoice_id
        and str(task.status) in {"review_required", "in_review"}
    ]
    if review_tasks:
        return VendorSafeStatus.NEEDS_INFORMATION

    approval_tasks = [
        task for task in repository.list_approval_tasks(tenant_id) if task.invoice_id == invoice.invoice_id
    ]
    if not approval_tasks:
        return VendorSafeStatus.RECEIVED
    latest = approval_tasks[-1]
    if latest.status == ApprovalTaskStatus.REJECTED:
        return VendorSafeStatus.REJECTED
    if latest.status in {ApprovalTaskStatus.AUTO_APPROVED, ApprovalTaskStatus.APPROVED}:
        return VendorSafeStatus.APPROVED
    if latest.status in {
        ApprovalTaskStatus.PENDING,
        ApprovalTaskStatus.BLOCKED,
        ApprovalTaskStatus.ON_HOLD,
    }:
        return VendorSafeStatus.UNDER_REVIEW
    return VendorSafeStatus.UNDER_REVIEW


def get_vendor_payment_status(
    repository: InMemoryAPRepository,
    tenant_id: UUID,
    invoice_id: UUID,
) -> str | None:
    logs = [
        log
        for log in repository.list_erp_sync_logs(tenant_id)
        if log.invoice_id == invoice_id and log.operation == ERPOperation.SYNC_PAYMENT_STATUS
    ]
    if not logs:
        return None
    return logs[-1].metadata.get("payment_status")


def vendor_invoice_list_item(
    repository: InMemoryAPRepository,
    tenant_id: UUID,
    invoice: InvoiceRecord,
) -> VendorInvoiceListItem:
    canonical = invoice.canonical_invoice
    return VendorInvoiceListItem(
        invoice_id=invoice.invoice_id,
        invoice_number=canonical.invoice_number,
        supplier_name=canonical.supplier_name,
        invoice_date=canonical.invoice_date,
        currency=canonical.currency,
        grand_total=canonical.grand_total,
        status=map_vendor_invoice_status(repository, tenant_id, invoice),
        payment_status=get_vendor_payment_status(repository, tenant_id, invoice.invoice_id),
    )


def vendor_invoice_status(
    repository: InMemoryAPRepository,
    tenant_id: UUID,
    invoice: InvoiceRecord,
) -> VendorInvoiceStatus:
    item = vendor_invoice_list_item(repository, tenant_id, invoice)
    missing_information = [
        issue.field_name
        for task in repository.list_review_tasks(tenant_id)
        if task.invoice_id == invoice.invoice_id
        for issue in task.issues
    ]
    return VendorInvoiceStatus(
        **item.model_dump(),
        due_date=invoice.canonical_invoice.due_date,
        public_message=_public_message(item.status),
        missing_information=missing_information,
        line_item_count=len(invoice.canonical_invoice.line_items),
    )


def _public_message(status: VendorSafeStatus) -> str:
    messages = {
        VendorSafeStatus.RECEIVED: "We received this invoice and it is waiting for review.",
        VendorSafeStatus.UNDER_REVIEW: "This invoice is under AP review.",
        VendorSafeStatus.NEEDS_INFORMATION: "We need more information before this invoice can continue.",
        VendorSafeStatus.APPROVED: "This invoice has been approved.",
        VendorSafeStatus.SCHEDULED_FOR_PAYMENT: "This invoice is scheduled for payment.",
        VendorSafeStatus.PAID: "This invoice is marked as paid.",
        VendorSafeStatus.REJECTED: "This invoice cannot be processed. Contact AP for the public reason.",
    }
    return messages[status]
