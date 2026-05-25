from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_repository, require_permission, resolve_tenant_id
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import AccuracyAnalyticsResponse, CurrentUserContext, Permission, UsageEventSource, UsageEventType
from app.services.analytics_service import AnalyticsService
from app.services.usage_metering_service import UsageMeteringService

router = APIRouter()


def _service(repository: InMemoryAPRepository = Depends(get_repository)) -> AnalyticsService:
    return AnalyticsService(repository)


@router.get("/accuracy", response_model=AccuracyAnalyticsResponse)
def get_accuracy_analytics(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    service: AnalyticsService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> AccuracyAnalyticsResponse:
    UsageMeteringService(repository).record_usage_event(
        tenant_id,
        UsageEventType.ANALYTICS_VIEWED,
        source=UsageEventSource.USER,
        metadata={"dashboard": "accuracy"},
    )
    return service.accuracy_exception_dashboard(tenant_id)
