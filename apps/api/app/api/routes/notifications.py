from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import get_audit_agent, get_repository, require_permission, resolve_tenant_id
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    CurrentUserContext,
    NotificationDeliveryRead,
    NotificationProviderRead,
    NotificationReadinessResponse,
    NotificationSummary,
    NotificationTestRequest,
    Permission,
)
from app.services.notification_service import NotificationService

router = APIRouter()


def _service(
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> NotificationService:
    return NotificationService(repository, audit_agent)


@router.get("/providers", response_model=list[NotificationProviderRead])
def list_notification_providers(
    _tenant_id: UUID = Depends(resolve_tenant_id),
    service: NotificationService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.NOTIFICATION_READ)),
) -> list[NotificationProviderRead]:
    return service.list_providers()


@router.get("/readiness", response_model=NotificationReadinessResponse)
def get_notification_readiness(
    _tenant_id: UUID = Depends(resolve_tenant_id),
    service: NotificationService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.NOTIFICATION_READ)),
) -> NotificationReadinessResponse:
    return service.provider_readiness()


@router.post("/test", response_model=NotificationDeliveryRead)
def send_test_notification(
    payload: NotificationTestRequest,
    service: NotificationService = Depends(_service),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_PROCESS)),
) -> NotificationDeliveryRead:
    _enforce_body_tenant(payload.tenant_id, context)
    return service.test_provider(payload, context)


@router.get("/deliveries", response_model=list[NotificationDeliveryRead])
def list_notification_deliveries(
    tenant_id: UUID = Depends(resolve_tenant_id),
    status: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    related_invoice_id: UUID | None = Query(default=None),
    service: NotificationService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.NOTIFICATION_READ)),
) -> list[NotificationDeliveryRead]:
    return service.list_deliveries(
        tenant_id,
        status=status,
        channel=channel,
        event_type=event_type,
        related_invoice_id=related_invoice_id,
    )


@router.get("/summary", response_model=NotificationSummary)
def get_notification_summary(
    tenant_id: UUID = Depends(resolve_tenant_id),
    service: NotificationService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.NOTIFICATION_READ)),
) -> NotificationSummary:
    return service.summary(tenant_id)


def _enforce_body_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
