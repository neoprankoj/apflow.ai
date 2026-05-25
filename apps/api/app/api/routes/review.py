from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agents.interface.human_review_agent import HumanReviewAgent
from app.api.dependencies import get_human_review_agent, get_repository, require_permission, resolve_tenant_id
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    CurrentUserContext,
    HumanReviewCorrectionRequest,
    HumanReviewTask,
    Permission,
    UsageEventSource,
    UsageEventType,
)
from app.services.usage_metering_service import UsageMeteringService

router = APIRouter()


@router.get("/tasks")
def list_review_tasks(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.REVIEW_READ)),
) -> list[HumanReviewTask]:
    return repository.list_review_tasks(tenant_id)


@router.get("/tasks/{task_id}")
def get_review_task(
    task_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.REVIEW_READ)),
) -> HumanReviewTask:
    return repository.get_review_task(tenant_id, task_id)


@router.post("/tasks/{task_id}/corrections")
def submit_review_corrections(
    task_id: UUID,
    payload: HumanReviewCorrectionRequest,
    review_agent: HumanReviewAgent = Depends(get_human_review_agent),
    repository: InMemoryAPRepository = Depends(get_repository),
    context: CurrentUserContext = Depends(require_permission(Permission.REVIEW_CORRECT)),
):
    _enforce_body_tenant(payload.tenant_id, context)
    result = review_agent.submit_corrections(task_id, payload)
    task = repository.get_review_task(payload.tenant_id, task_id)
    UsageMeteringService(repository).record_usage_event(
        payload.tenant_id,
        UsageEventType.REVIEW_CORRECTION_SUBMITTED,
        source=UsageEventSource.USER,
        related_invoice_id=task.invoice_id,
        metadata={"corrected_field_count": len(result.corrected_fields)},
    )
    return result


@router.post("/tasks/{task_id}/approve")
def approve_review_task(
    task_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    review_agent: HumanReviewAgent = Depends(get_human_review_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.REVIEW_CORRECT)),
) -> HumanReviewTask:
    return review_agent.approve(tenant_id, task_id)


@router.post("/tasks/{task_id}/reject")
def reject_review_task(
    task_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    review_agent: HumanReviewAgent = Depends(get_human_review_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.REVIEW_CORRECT)),
) -> HumanReviewTask:
    return review_agent.reject(tenant_id, task_id)


def _enforce_body_tenant(tenant_id: UUID, context: CurrentUserContext) -> None:
    if settings.auth_enabled and tenant_id != context.tenant.id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
