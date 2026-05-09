from uuid import UUID

from app.core.schemas import (
    ERPAdapterType,
    ERPInvoiceExportResult,
    ERPPaymentStatusResult,
    ERPPurchaseOrderRecord,
    ERPSyncLog,
    ERPVendorRecord,
    PurchaseOrderLine,
)


class BaseMockERPAdapter:
    adapter_type: ERPAdapterType
    vendors: list[dict]
    purchase_orders: list[dict]

    def __init__(self) -> None:
        self._logs: dict[UUID, list[ERPSyncLog]] = {}

    def get_adapter_name(self) -> str:
        return self.adapter_type

    def test_connection(self, tenant_id: UUID) -> bool:
        return True

    def sync_vendors(self, tenant_id: UUID) -> list[ERPVendorRecord]:
        return [
            ERPVendorRecord(
                tenant_id=tenant_id,
                external_vendor_id=vendor["external_vendor_id"],
                name=vendor["name"],
                tax_id=vendor.get("tax_id"),
                bank_account_hash=vendor.get("bank_account_hash"),
            )
            for vendor in self.vendors
        ]

    def sync_purchase_orders(self, tenant_id: UUID) -> list[ERPPurchaseOrderRecord]:
        return [
            ERPPurchaseOrderRecord(
                tenant_id=tenant_id,
                external_po_id=po["external_po_id"],
                po_number=po["po_number"],
                external_vendor_id=po["external_vendor_id"],
                vendor_name=po["vendor_name"],
                vendor_tax_id=po.get("vendor_tax_id"),
                currency=po.get("currency", "USD"),
                total_amount=po["total_amount"],
                lines=[
                    PurchaseOrderLine(
                        description=line["description"],
                        quantity=line["quantity"],
                        unit_price=line["unit_price"],
                        total=line["total"],
                    )
                    for line in po.get("lines", [])
                ],
            )
            for po in self.purchase_orders
        ]

    def export_invoice(self, tenant_id: UUID, invoice_id: UUID) -> ERPInvoiceExportResult:
        return ERPInvoiceExportResult(
            invoice_id=invoice_id,
            external_invoice_id=f"{self.adapter_type.upper()}-INV-{str(invoice_id)[:8]}",
            exported=True,
        )

    def update_invoice_status(self, tenant_id: UUID, invoice_id: UUID, status: str) -> bool:
        return True

    def sync_payment_status(self, tenant_id: UUID, invoice_id: UUID) -> ERPPaymentStatusResult:
        return ERPPaymentStatusResult(
            invoice_id=invoice_id,
            external_invoice_id=f"{self.adapter_type.upper()}-INV-{str(invoice_id)[:8]}",
            payment_status="scheduled",
            paid_at=None,
        )

    def get_sync_log(self, tenant_id: UUID) -> list[ERPSyncLog]:
        return self._logs.get(tenant_id, [])


class MockPriorityERPAdapter(BaseMockERPAdapter):
    adapter_type = ERPAdapterType.PRIORITY
    vendors = [
        {
            "external_vendor_id": "PRI-V-100",
            "name": "Northstar Components",
            "tax_id": "TAX-12345",
            "bank_account_hash": "bank-hash-northstar",
        },
        {
            "external_vendor_id": "PRI-V-200",
            "name": "Tel Aviv Logistics Ltd",
            "tax_id": "IL-514220991",
        },
    ]
    purchase_orders = [
        {
            "external_po_id": "PRI-PO-100",
            "po_number": "PO-100",
            "external_vendor_id": "PRI-V-100",
            "vendor_name": "Northstar Components",
            "vendor_tax_id": "TAX-12345",
            "currency": "USD",
            "total_amount": 1170,
            "lines": [
                {
                    "description": "Mock extracted invoice line",
                    "quantity": 1,
                    "unit_price": 1000,
                    "total": 1170,
                }
            ],
        },
        {
            "external_po_id": "PRI-PO-IL-220",
            "po_number": "PO-IL-220",
            "external_vendor_id": "PRI-V-200",
            "vendor_name": "Tel Aviv Logistics Ltd",
            "vendor_tax_id": "IL-514220991",
            "currency": "ILS",
            "total_amount": 8200,
            "lines": [
                {
                    "description": "Domestic freight service",
                    "quantity": 1,
                    "unit_price": 7000,
                    "total": 8200,
                }
            ],
        },
    ]


class MockOdooERPAdapter(BaseMockERPAdapter):
    adapter_type = ERPAdapterType.ODOO
    vendors = [
        {
            "external_vendor_id": "ODOO-V-10",
            "name": "Pacific Distributor Group",
            "tax_id": "US-88-1553001",
        },
        {
            "external_vendor_id": "ODOO-V-20",
            "name": "Summit Manufacturing Co",
            "tax_id": "US-91-0031420",
        },
    ]
    purchase_orders = [
        {
            "external_po_id": "ODOO-PO-410",
            "po_number": "ODOO-PO-410",
            "external_vendor_id": "ODOO-V-10",
            "vendor_name": "Pacific Distributor Group",
            "vendor_tax_id": "US-88-1553001",
            "currency": "USD",
            "total_amount": 4300,
            "lines": [
                {
                    "description": "Distributor replenishment batch",
                    "quantity": 10,
                    "unit_price": 430,
                    "total": 4300,
                }
            ],
        }
    ]


class MockZohoBooksAdapter(BaseMockERPAdapter):
    adapter_type = ERPAdapterType.ZOHO_BOOKS
    vendors = [
        {
            "external_vendor_id": "ZOHO-V-11",
            "name": "Bright Office Supply",
            "tax_id": "SMB-77881",
        },
        {
            "external_vendor_id": "ZOHO-V-12",
            "name": "Greenfield Web Services",
            "tax_id": "SMB-77882",
        },
    ]
    purchase_orders = [
        {
            "external_po_id": "ZOHO-PO-55",
            "po_number": "ZOHO-PO-55",
            "external_vendor_id": "ZOHO-V-11",
            "vendor_name": "Bright Office Supply",
            "vendor_tax_id": "SMB-77881",
            "currency": "USD",
            "total_amount": 612.44,
            "lines": [
                {
                    "description": "Office supplies bundle",
                    "quantity": 1,
                    "unit_price": 612.44,
                    "total": 612.44,
                }
            ],
        }
    ]
