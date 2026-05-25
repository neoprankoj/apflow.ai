from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_repository, require_permission, resolve_tenant_id
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import AccuracyAnalyticsResponse, CurrentUserContext, Permission
from app.services.analytics_service import AnalyticsService

router = APIRouter()


def _service(repository: InMemoryAPRepository = Depends(get_repository)) -> AnalyticsService:
    return AnalyticsService(repository)


@router.get("/accuracy", response_model=AccuracyAnalyticsResponse)
def get_accuracy_analytics(
    tenant_id: UUID = Depends(resolve_tenant_id),
    service: AnalyticsService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> AccuracyAnalyticsResponse:
    return service.accuracy_exception_dashboard(tenant_id)
