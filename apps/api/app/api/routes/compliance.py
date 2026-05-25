from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_repository, require_permission, resolve_tenant_id
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    ComplianceProfileRead,
    ComplianceSummary,
    CurrentUserContext,
    InvoiceComplianceResult,
    Permission,
)
from app.services.compliance_service import ComplianceService

router = APIRouter()


def _service(repository: InMemoryAPRepository = Depends(get_repository)) -> ComplianceService:
    return ComplianceService(repository)


@router.get("/profiles", response_model=list[ComplianceProfileRead])
def list_compliance_profiles(
    service: ComplianceService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list[ComplianceProfileRead]:
    return service.list_compliance_profiles()


@router.get("/invoices/{invoice_id}", response_model=InvoiceComplianceResult)
def get_invoice_compliance(
    invoice_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    profile_key: str = Query("generic_b2b"),
    repository: InMemoryAPRepository = Depends(get_repository),
    service: ComplianceService = Depends(_service),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> InvoiceComplianceResult:
    try:
        result = service.validate_invoice_compliance(tenant_id, invoice_id, profile_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Invoice not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repository.store_audit_event(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action="invoice.compliance_validated",
            entity_type="invoice",
            entity_id=invoice_id,
            metadata={
                "profile_key": result.profile_key,
                "status": str(result.status),
                "missing_required_count": len(result.missing_required_fields),
                "warning_count": len(result.warnings),
            },
            correlation_id=uuid4(),
        ),
        uuid4(),
    )
    return result


@router.get("/summary", response_model=ComplianceSummary)
def get_compliance_summary(
    tenant_id: UUID = Depends(resolve_tenant_id),
    profile_key: str = Query("generic_b2b"),
    service: ComplianceService = Depends(_service),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> ComplianceSummary:
    try:
        return service.get_compliance_summary(tenant_id, profile_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
