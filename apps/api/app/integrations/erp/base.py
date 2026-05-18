from typing import Any, Protocol
from uuid import UUID

from app.core.schemas import (
    ERPInvoiceExportResult,
    ERPPaymentStatusResult,
    ERPPurchaseOrderRecord,
    ERPSyncLog,
    ERPVendorRecord,
)


class ERPAdapterProtocol(Protocol):
    def get_adapter_name(self) -> str: ...

    def test_connection(self, tenant_id: UUID) -> bool | dict[str, Any]: ...

    def sync_vendors(self, tenant_id: UUID) -> list[ERPVendorRecord]: ...

    def sync_purchase_orders(self, tenant_id: UUID) -> list[ERPPurchaseOrderRecord]: ...

    def export_invoice(self, tenant_id: UUID, invoice_id: UUID) -> ERPInvoiceExportResult: ...

    def update_invoice_status(self, tenant_id: UUID, invoice_id: UUID, status: str) -> bool: ...

    def sync_payment_status(self, tenant_id: UUID, invoice_id: UUID) -> ERPPaymentStatusResult: ...

    def get_sync_log(self, tenant_id: UUID) -> list[ERPSyncLog]: ...


class ERPAdapterError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
