from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import get_audit_agent, get_repository, require_permission, resolve_tenant_id
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    ManualUsageEventRequest,
    Permission,
    TenantUsageSummary,
    UsageEventRead,
    UsageEventSource,
    UsageEventType,
    UsagePlanRead,
)
from app.services.usage_metering_service import UsageMeteringService

router = APIRouter()


def _service(repository: InMemoryAPRepository = Depends(get_repository)) -> UsageMeteringService:
    return UsageMeteringService(repository)


@router.get("/summary", response_model=TenantUsageSummary)
def get_usage_summary(
    tenant_id: UUID = Depends(resolve_tenant_id),
    period: str = Query(default="current_month"),
    service: UsageMeteringService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> TenantUsageSummary:
    return service.summary(tenant_id, period=period)


@router.get("/events", response_model=list[UsageEventRead])
def list_usage_events(
    tenant_id: UUID = Depends(resolve_tenant_id),
    event_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    related_invoice_id: UUID | None = Query(default=None),
    service: UsageMeteringService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.AUDIT_READ)),
) -> list[UsageEventRead]:
    return service.list_events(
        tenant_id,
        event_type=event_type,
        source=source,
        date_from=date_from,
        date_to=date_to,
        related_invoice_id=related_invoice_id,
    )


@router.get("/plans", response_model=list[UsagePlanRead])
def list_usage_plans(
    _tenant_id: UUID = Depends(resolve_tenant_id),
    service: UsageMeteringService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list[UsagePlanRead]:
    return service.available_plans(current_plan_key="demo")


@router.post("/events/manual-test", response_model=UsageEventRead)
def create_manual_usage_test_event(
    payload: ManualUsageEventRequest,
    service: UsageMeteringService = Depends(_service),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
) -> UsageEventRead:
    _enforce_body_tenant(payload.tenant_id, context)
    event = service.record_usage_event(
        payload.tenant_id,
        payload.event_type or UsageEventType.MANUAL_TEST,
        source=payload.source or UsageEventSource.USER,
        quantity=payload.quantity,
        metadata=payload.metadata,
    )
    if event is None:
        raise HTTPException(status_code=500, detail="Usage event could not be recorded")
    audit_agent.record(
        AuditEventInput(
            tenant_id=payload.tenant_id,
            actor_type=ActorType.USER,
            actor_id=context.user.email,
            action="usage.manual_test_event_created",
            entity_type="usage_event",
            entity_id=event.id,
            metadata={"event_type": str(event.event_type), "quantity": event.quantity},
        )
    )
    return event


def _enforce_body_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
