from uuid import UUID

from app.agents.base import BaseAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.agents.observability.error_handler_agent import ErrorHandlerAgent
from app.agents.observability.monitoring_agent import MonitoringAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ERPAdapterType,
    ERPConnectionConfig,
    ERPInvoiceExportResult,
    ERPOperation,
    ERPPaymentStatusResult,
    ERPSyncLog,
    ERPSyncRequest,
    ERPSyncResult,
    ERPSyncStatus,
    ErrorCategory,
    MetricEventInput,
    WorkflowErrorInput,
)
from app.integrations.erp.base import ERPAdapterProtocol
from app.integrations.erp.mock_adapters import (
    MockOdooERPAdapter,
    MockPriorityERPAdapter,
    MockZohoBooksAdapter,
)


class ERPConnectorAgent(BaseAgent[ERPSyncRequest, ERPSyncResult]):
    name = "ERPConnectorAgent"
    responsibility = "Sync APFlow data with tenant-selected ERP adapters."

    def __init__(
        self,
        repository: InMemoryAPRepository,
        audit_agent: AuditLoggingAgent,
        monitoring_agent: MonitoringAgent,
        error_handler_agent: ErrorHandlerAgent,
        adapters: dict[ERPAdapterType, ERPAdapterProtocol] | None = None,
    ) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.monitoring_agent = monitoring_agent
        self.error_handler_agent = error_handler_agent
        self.adapters = adapters or {
            ERPAdapterType.PRIORITY: MockPriorityERPAdapter(),
            ERPAdapterType.ODOO: MockOdooERPAdapter(),
            ERPAdapterType.ZOHO_BOOKS: MockZohoBooksAdapter(),
        }

    def available_adapters(self) -> list[str]:
        return [str(adapter_type) for adapter_type in self.adapters]

    def configure_connection(self, config: ERPConnectionConfig) -> ERPConnectionConfig:
        if config.adapter_type not in self.adapters:
            raise ValueError(f"unsupported ERP adapter: {config.adapter_type}")
        self.repository.set_erp_connection_config(config)
        return config

    def run(self, request: ERPSyncRequest) -> ERPSyncResult:
        adapter_type = self._adapter_type_for(request)
        adapter = self.adapters[adapter_type]
        try:
            result = self._execute(adapter_type, adapter, request)
            self._record_success(request, result)
            return result
        except Exception as exc:
            result = ERPSyncResult(
                adapter_type=adapter_type,
                operation=request.operation,
                status=ERPSyncStatus.FAILED,
                errors=[str(exc)],
            )
            self._record_failure(request, result, exc)
            return result

    def test_connection(self, tenant_id: UUID, adapter_type: ERPAdapterType | None = None) -> ERPSyncResult:
        return self.run(
            ERPSyncRequest(
                tenant_id=tenant_id,
                adapter_type=adapter_type,
                operation=ERPOperation.TEST_CONNECTION,
            )
        )

    def sync_vendors(self, tenant_id: UUID, adapter_type: ERPAdapterType | None = None) -> ERPSyncResult:
        return self.run(
            ERPSyncRequest(
                tenant_id=tenant_id,
                adapter_type=adapter_type,
                operation=ERPOperation.SYNC_VENDORS,
            )
        )

    def sync_purchase_orders(
        self,
        tenant_id: UUID,
        adapter_type: ERPAdapterType | None = None,
    ) -> ERPSyncResult:
        return self.run(
            ERPSyncRequest(
                tenant_id=tenant_id,
                adapter_type=adapter_type,
                operation=ERPOperation.SYNC_PURCHASE_ORDERS,
            )
        )

    def export_invoice(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        adapter_type: ERPAdapterType | None = None,
    ) -> ERPSyncResult:
        return self.run(
            ERPSyncRequest(
                tenant_id=tenant_id,
                adapter_type=adapter_type,
                operation=ERPOperation.EXPORT_INVOICE,
                invoice_id=invoice_id,
            )
        )

    def update_invoice_status(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        status: str,
        adapter_type: ERPAdapterType | None = None,
    ) -> ERPSyncResult:
        return self.run(
            ERPSyncRequest(
                tenant_id=tenant_id,
                adapter_type=adapter_type,
                operation=ERPOperation.UPDATE_INVOICE_STATUS,
                invoice_id=invoice_id,
                status=status,
            )
        )

    def sync_payment_status(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        adapter_type: ERPAdapterType | None = None,
    ) -> ERPSyncResult:
        return self.run(
            ERPSyncRequest(
                tenant_id=tenant_id,
                adapter_type=adapter_type,
                operation=ERPOperation.SYNC_PAYMENT_STATUS,
                invoice_id=invoice_id,
            )
        )

    def get_sync_log(self, tenant_id: UUID) -> list[ERPSyncLog]:
        return self.repository.list_erp_sync_logs(tenant_id)

    def _adapter_type_for(self, request: ERPSyncRequest) -> ERPAdapterType:
        if request.adapter_type is not None:
            return request.adapter_type
        return self.repository.get_erp_connection_config(request.tenant_id).adapter_type

    def _execute(
        self,
        adapter_type: ERPAdapterType,
        adapter: ERPAdapterProtocol,
        request: ERPSyncRequest,
    ) -> ERPSyncResult:
        if request.operation == ERPOperation.TEST_CONNECTION:
            adapter.test_connection(request.tenant_id)
            return ERPSyncResult(
                adapter_type=adapter_type,
                operation=request.operation,
                status=ERPSyncStatus.SUCCESS,
                records_processed=1,
                details={"connected": True},
            )

        if request.operation == ERPOperation.SYNC_VENDORS:
            vendors = adapter.sync_vendors(request.tenant_id)
            for vendor in vendors:
                local = self.repository.add_vendor(
                    tenant_id=request.tenant_id,
                    name=vendor.name,
                    tax_id=vendor.tax_id,
                    bank_account_hash=vendor.bank_account_hash,
                )
                self.repository.link_external_vendor_id(
                    request.tenant_id,
                    local.vendor_id,
                    vendor.external_vendor_id,
                )
            return ERPSyncResult(
                adapter_type=adapter_type,
                operation=request.operation,
                status=ERPSyncStatus.SUCCESS,
                records_processed=len(vendors),
                details={"vendors": [vendor.model_dump(mode="json") for vendor in vendors]},
            )

        if request.operation == ERPOperation.SYNC_PURCHASE_ORDERS:
            pos = adapter.sync_purchase_orders(request.tenant_id)
            for po in pos:
                vendor = self.repository.add_vendor(
                    tenant_id=request.tenant_id,
                    name=po.vendor_name,
                    tax_id=po.vendor_tax_id,
                )
                local_po = self.repository.add_purchase_order(
                    tenant_id=request.tenant_id,
                    po_number=po.po_number,
                    vendor_id=vendor.vendor_id,
                    total_amount=po.total_amount,
                    lines=po.lines,
                    currency=po.currency,
                )
                self.repository.link_external_purchase_order_id(
                    request.tenant_id,
                    local_po.purchase_order_id,
                    po.external_po_id,
                )
            return ERPSyncResult(
                adapter_type=adapter_type,
                operation=request.operation,
                status=ERPSyncStatus.SUCCESS,
                records_processed=len(pos),
                details={"purchase_orders": [po.model_dump(mode="json") for po in pos]},
            )

        if request.operation == ERPOperation.EXPORT_INVOICE:
            invoice_id = self._require_invoice_id(request)
            export: ERPInvoiceExportResult = adapter.export_invoice(request.tenant_id, invoice_id)
            self.repository.link_external_invoice_id(
                request.tenant_id,
                invoice_id,
                export.external_invoice_id,
            )
            return ERPSyncResult(
                adapter_type=adapter_type,
                operation=request.operation,
                status=ERPSyncStatus.SUCCESS,
                records_processed=1,
                external_id=export.external_invoice_id,
                details=export.model_dump(mode="json"),
            )

        if request.operation == ERPOperation.UPDATE_INVOICE_STATUS:
            invoice_id = self._require_invoice_id(request)
            adapter.update_invoice_status(request.tenant_id, invoice_id, request.status or "approved")
            return ERPSyncResult(
                adapter_type=adapter_type,
                operation=request.operation,
                status=ERPSyncStatus.SUCCESS,
                records_processed=1,
                details={"invoice_id": str(invoice_id), "status": request.status or "approved"},
            )

        if request.operation == ERPOperation.SYNC_PAYMENT_STATUS:
            invoice_id = self._require_invoice_id(request)
            payment: ERPPaymentStatusResult = adapter.sync_payment_status(request.tenant_id, invoice_id)
            return ERPSyncResult(
                adapter_type=adapter_type,
                operation=request.operation,
                status=ERPSyncStatus.SUCCESS,
                records_processed=1,
                external_id=payment.external_invoice_id,
                details=payment.model_dump(mode="json"),
            )

        raise ValueError(f"unsupported ERP operation: {request.operation}")

    def _require_invoice_id(self, request: ERPSyncRequest) -> UUID:
        if request.invoice_id is None:
            raise ValueError(f"{request.operation} requires invoice_id")
        if not any(invoice.invoice_id == request.invoice_id for invoice in self.repository.list_invoices(request.tenant_id)):
            raise KeyError("invoice is outside tenant scope")
        return request.invoice_id

    def _record_success(self, request: ERPSyncRequest, result: ERPSyncResult) -> None:
        log = ERPSyncLog(
            sync_log_id=result.sync_id,
            tenant_id=request.tenant_id,
            adapter_type=result.adapter_type,
            operation=result.operation,
            status=result.status,
            records_processed=result.records_processed,
            external_id=result.external_id,
            invoice_id=request.invoice_id,
            errors=result.errors,
            metadata=result.details,
        )
        self.repository.store_erp_sync_log(log)
        self.audit_agent.record(
            AuditEventInput(
                tenant_id=request.tenant_id,
                actor_type=ActorType.AGENT,
                actor_id=self.name,
                action=f"erp.{request.operation}",
                entity_type="erp_sync",
                entity_id=result.sync_id,
                metadata={
                    "adapter_type": result.adapter_type,
                    "status": result.status,
                    "records_processed": result.records_processed,
                    "invoice_id": str(request.invoice_id) if request.invoice_id else None,
                },
                correlation_id=request.correlation_id,
            )
        )
        self.monitoring_agent.record_metric(
            MetricEventInput(
                tenant_id=request.tenant_id,
                metric_event="erp.sync",
                value=1,
                metadata={"adapter_type": result.adapter_type, "operation": result.operation},
            )
        )

    def _record_failure(self, request: ERPSyncRequest, result: ERPSyncResult, exc: Exception) -> None:
        self.repository.store_erp_sync_log(
            ERPSyncLog(
                sync_log_id=result.sync_id,
                tenant_id=request.tenant_id,
                adapter_type=result.adapter_type,
                operation=result.operation,
                status=ERPSyncStatus.FAILED,
                invoice_id=request.invoice_id,
                errors=[str(exc)],
            )
        )
        self.error_handler_agent.handle_error(
            WorkflowErrorInput(
                tenant_id=request.tenant_id,
                workflow_id=request.correlation_id,
                agent_name=self.name,
                error_type=ErrorCategory.INTEGRATION,
                error_message=str(exc),
                retry_count=0,
                context={
                    "operation": request.operation,
                    "adapter_type": result.adapter_type,
                    "invoice_id": str(request.invoice_id) if request.invoice_id else None,
                },
            )
        )
        self.monitoring_agent.record_metric(
            MetricEventInput(
                tenant_id=request.tenant_id,
                metric_event="erp.sync_failure",
                value=1,
                metadata={"adapter_type": result.adapter_type, "operation": result.operation},
            )
        )
