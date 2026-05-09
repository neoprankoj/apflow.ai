from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.api.dependencies import get_erp_connector_agent, require_permission, resolve_tenant_id
from app.core.config import settings
from app.core.schemas import (
    CurrentUserContext,
    ERPConnectionConfig,
    ERPOperation,
    ERPSyncRequest,
    ERPSyncResult,
    Permission,
)

router = APIRouter()


@router.get("/adapters")
def list_erp_adapters(
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
) -> list[str]:
    return erp_agent.available_adapters()


@router.post("/config", response_model=ERPConnectionConfig)
def configure_erp_connection(
    config: ERPConnectionConfig,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_CONFIGURE)),
) -> ERPConnectionConfig:
    _enforce_body_tenant(config.tenant_id, context)
    return erp_agent.configure_connection(config)


@router.post("/test-connection", response_model=ERPSyncResult)
def test_erp_connection(
    request: ERPSyncRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_READ)),
) -> ERPSyncResult:
    _enforce_body_tenant(request.tenant_id, context)
    request.operation = ERPOperation.TEST_CONNECTION
    return erp_agent.run(request)


@router.post("/sync-vendors", response_model=ERPSyncResult)
def sync_erp_vendors(
    request: ERPSyncRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> ERPSyncResult:
    _enforce_body_tenant(request.tenant_id, context)
    request.operation = ERPOperation.SYNC_VENDORS
    return erp_agent.run(request)


@router.post("/sync-purchase-orders", response_model=ERPSyncResult)
def sync_erp_purchase_orders(
    request: ERPSyncRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> ERPSyncResult:
    _enforce_body_tenant(request.tenant_id, context)
    request.operation = ERPOperation.SYNC_PURCHASE_ORDERS
    return erp_agent.run(request)


@router.post("/export-invoice", response_model=ERPSyncResult)
def export_invoice_to_erp(
    request: ERPSyncRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_EXPORT_ERP)),
) -> ERPSyncResult:
    _enforce_body_tenant(request.tenant_id, context)
    request.operation = ERPOperation.EXPORT_INVOICE
    return erp_agent.run(request)


@router.post("/update-invoice-status", response_model=ERPSyncResult)
def update_erp_invoice_status(
    request: ERPSyncRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> ERPSyncResult:
    _enforce_body_tenant(request.tenant_id, context)
    request.operation = ERPOperation.UPDATE_INVOICE_STATUS
    return erp_agent.run(request)


@router.post("/sync-payment-status", response_model=ERPSyncResult)
def sync_erp_payment_status(
    request: ERPSyncRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> ERPSyncResult:
    _enforce_body_tenant(request.tenant_id, context)
    request.operation = ERPOperation.SYNC_PAYMENT_STATUS
    return erp_agent.run(request)


@router.get("/sync-logs")
def list_erp_sync_logs(
    tenant_id: UUID = Depends(resolve_tenant_id),
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_READ)),
) -> list:
    return erp_agent.get_sync_log(tenant_id)


def _enforce_body_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
