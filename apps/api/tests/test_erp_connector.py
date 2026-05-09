from uuid import UUID, uuid4

from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    CanonicalInvoice,
    ERPAdapterType,
    ERPConnectionConfig,
    ERPOperation,
    ERPSyncRequest,
    ERPSyncStatus,
    InvoiceNormalizationOutput,
)
from app.integrations.erp.mock_adapters import (
    MockOdooERPAdapter,
    MockPriorityERPAdapter,
    MockZohoBooksAdapter,
)


def _store_invoice(repository: InMemoryAPRepository, tenant_id, invoice_id=None):
    output = InvoiceNormalizationOutput(
        tenant_id=tenant_id,
        invoice_id=invoice_id or uuid4(),
        canonical_invoice=CanonicalInvoice(
            invoice_number="INV-ERP-1",
            supplier_name="Northstar Components",
            supplier_tax_id="TAX-12345",
            invoice_date="2026-05-05",
            currency="USD",
            subtotal=1000,
            tax_total=170,
            grand_total=1170,
            po_number="PO-100",
        ),
        file_checksum="erp-checksum",
    )
    repository.store_invoice(output)
    return output.invoice_id


def test_erp_connector_selects_configured_adapter(
    tenant_id,
    repository,
    erp_connector_agent,
):
    erp_connector_agent.configure_connection(
        ERPConnectionConfig(tenant_id=tenant_id, adapter_type=ERPAdapterType.ODOO)
    )

    result = erp_connector_agent.test_connection(tenant_id)

    assert result.adapter_type == ERPAdapterType.ODOO
    assert result.status == ERPSyncStatus.SUCCESS


def test_mock_priority_adapter_returns_local_market_records(tenant_id):
    adapter = MockPriorityERPAdapter()

    vendors = adapter.sync_vendors(tenant_id)
    pos = adapter.sync_purchase_orders(tenant_id)

    assert adapter.test_connection(tenant_id) is True
    assert any(vendor.tax_id and vendor.tax_id.startswith("IL-") for vendor in vendors)
    assert any(po.currency == "ILS" for po in pos)


def test_mock_odoo_adapter_returns_distributor_records(tenant_id):
    adapter = MockOdooERPAdapter()

    vendors = adapter.sync_vendors(tenant_id)
    pos = adapter.sync_purchase_orders(tenant_id)

    assert vendors[0].name == "Pacific Distributor Group"
    assert pos[0].po_number == "ODOO-PO-410"


def test_mock_zoho_adapter_returns_smb_records(tenant_id):
    adapter = MockZohoBooksAdapter()

    vendors = adapter.sync_vendors(tenant_id)
    pos = adapter.sync_purchase_orders(tenant_id)

    assert vendors[0].name == "Bright Office Supply"
    assert pos[0].total_amount == 612.44


def test_erp_vendor_and_po_sync_populates_repository(tenant_id, repository, erp_connector_agent):
    vendor_result = erp_connector_agent.sync_vendors(tenant_id, ERPAdapterType.PRIORITY)
    po_result = erp_connector_agent.sync_purchase_orders(tenant_id, ERPAdapterType.PRIORITY)

    assert vendor_result.status == ERPSyncStatus.SUCCESS
    assert vendor_result.records_processed == 2
    assert po_result.status == ERPSyncStatus.SUCCESS
    assert repository.list_vendors(tenant_id)
    assert repository.list_purchase_orders(tenant_id)


def test_erp_invoice_export_links_external_invoice_id(tenant_id, repository, erp_connector_agent):
    invoice_id = _store_invoice(repository, tenant_id)

    result = erp_connector_agent.export_invoice(tenant_id, invoice_id, ERPAdapterType.PRIORITY)

    assert result.status == ERPSyncStatus.SUCCESS
    assert result.external_id
    assert repository.get_external_invoice_id(tenant_id, invoice_id) == result.external_id


def test_erp_payment_status_sync(tenant_id, repository, erp_connector_agent):
    invoice_id = _store_invoice(repository, tenant_id)

    result = erp_connector_agent.sync_payment_status(tenant_id, invoice_id, ERPAdapterType.ZOHO_BOOKS)

    assert result.status == ERPSyncStatus.SUCCESS
    assert result.details["payment_status"] == "scheduled"


class FailingERPAdapter(MockPriorityERPAdapter):
    def sync_purchase_orders(self, tenant_id: UUID):
        raise RuntimeError("mock ERP outage")


def test_erp_sync_failure_routes_to_error_handler_and_logs(
    tenant_id,
    repository,
    audit_agent,
    monitoring_agent,
    error_handler_agent,
):
    agent = ERPConnectorAgent(
        repository=repository,
        audit_agent=audit_agent,
        monitoring_agent=monitoring_agent,
        error_handler_agent=error_handler_agent,
        adapters={ERPAdapterType.PRIORITY: FailingERPAdapter()},
    )

    result = agent.run(
        ERPSyncRequest(
            tenant_id=tenant_id,
            adapter_type=ERPAdapterType.PRIORITY,
            operation=ERPOperation.SYNC_PURCHASE_ORDERS,
        )
    )

    logs = repository.list_erp_sync_logs(tenant_id)
    assert result.status == ERPSyncStatus.FAILED
    assert logs[0].status == ERPSyncStatus.FAILED
    assert any(metric.metric_event == "erp.sync_failure" for metric in monitoring_agent.metrics)


def test_erp_sync_logs_are_tenant_scoped(repository, erp_connector_agent):
    tenant_a = uuid4()
    tenant_b = uuid4()

    erp_connector_agent.test_connection(tenant_a, ERPAdapterType.PRIORITY)

    assert len(repository.list_erp_sync_logs(tenant_a)) == 1
    assert repository.list_erp_sync_logs(tenant_b) == []
