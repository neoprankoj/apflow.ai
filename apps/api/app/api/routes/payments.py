from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import (
    get_audit_agent,
    get_repository,
    require_permission,
    resolve_tenant_id,
)
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    CurrentUserContext,
    PaymentStatusRead,
    PaymentStatusSummary,
    PaymentStatusSyncRequest,
    PaymentStatusUpdate,
    Permission,
)
from app.core.config import settings
from app.services.payment_status_service import PaymentStatusService

router = APIRouter()


def _service(
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> PaymentStatusService:
    return PaymentStatusService(repository, audit_agent)


@router.get("/statuses", response_model=list[PaymentStatusRead])
def list_payment_statuses(
    tenant_id: UUID = Depends(resolve_tenant_id),
    invoice_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    service: PaymentStatusService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list[PaymentStatusRead]:
    return service.list_statuses(tenant_id, invoice_id=invoice_id, status=status)


@router.get("/statuses/{payment_status_id}", response_model=PaymentStatusRead)
def get_payment_status(
    payment_status_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    service: PaymentStatusService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> PaymentStatusRead:
    try:
        return service.get_status(tenant_id, payment_status_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment status not found") from exc


@router.patch("/statuses/{payment_status_id}", response_model=PaymentStatusRead)
def update_payment_status(
    payment_status_id: UUID,
    payload: PaymentStatusUpdate,
    tenant_id: UUID = Depends(resolve_tenant_id),
    service: PaymentStatusService = Depends(_service),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> PaymentStatusRead:
    try:
        return service.update_status(tenant_id, payment_status_id, payload, context)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payment status not found") from exc


@router.post("/sync/mock", response_model=list[PaymentStatusRead])
def run_mock_payment_sync(
    payload: PaymentStatusSyncRequest,
    service: PaymentStatusService = Depends(_service),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> list[PaymentStatusRead]:
    _enforce_body_tenant(payload.tenant_id, context)
    try:
        return service.run_mock_sync(payload, context)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Invoice not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/summary", response_model=PaymentStatusSummary)
def get_payment_summary(
    tenant_id: UUID = Depends(resolve_tenant_id),
    service: PaymentStatusService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> PaymentStatusSummary:
    return service.summary(tenant_id)


def _enforce_body_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
