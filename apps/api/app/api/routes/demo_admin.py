from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import (
    get_audit_agent,
    get_repository,
    require_permission,
)
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    Permission,
)

router = APIRouter()


@router.post("/demo/reset")
def reset_demo_data(
    seed_mode: str = Query(default="clean", pattern="^(clean)$"),
    context: CurrentUserContext = Depends(require_permission(Permission.TENANT_ADMIN)),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> dict:
    if settings.app_env != "staging" or not settings.allow_demo_reset:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")

    tenant_id = context.tenant.id
    repository.clear_demo_operational_data(tenant_id)
    repository.ensure_phase3_fixtures(tenant_id)

    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="admin.demo_reset",
            entity_type="tenant",
            entity_id=tenant_id,
            metadata={
                "seed_mode": seed_mode,
                "workflow_status": "clean",
            },
        )
    )
    return {
        "message": "Demo data reset successfully.",
        "tenant_id": tenant_id,
        "tenant_name": context.tenant.name,
        "user_email": context.user.email,
        "invoice_id": None,
        "invoice_number": None,
        "workflow_status": "clean",
        "seed_mode": seed_mode,
        "erp_export_ready": False,
        "vendor_count": len(repository.list_vendors(tenant_id)),
        "purchase_order_count": len(repository.list_purchase_orders(tenant_id)),
        "approval_task_count": len(repository.list_approval_tasks(tenant_id)),
        "notification_count": len(repository.list_notification_events(tenant_id)),
        "reset_at": datetime.now(UTC).isoformat(),
    }
