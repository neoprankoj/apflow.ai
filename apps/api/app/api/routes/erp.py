from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.api.dependencies import get_erp_connector_agent, require_permission, resolve_tenant_id
from app.core.config import settings
from app.core.schemas import (
    CurrentUserContext,
    ERPConnectionConfig,
    ERPOperation,
    ERPAdapterType,
    ERPSyncRequest,
    ERPSyncResult,
    Permission,
    PriorityImportPlanRequest,
    PriorityImportPlanResponse,
    PrioritySyncPreviewRequest,
    PrioritySyncPreviewResponse,
    PriorityMappingValidationRequest,
    PriorityMappingValidationResult,
)
from app.integrations.erp.base import ERPAdapterError
from app.integrations.erp.priority import PriorityODataAdapter
from app.integrations.erp.priority_mapping import (
    build_purchase_order_import_plan,
    build_priority_sync_preview,
    build_vendor_import_plan,
    priority_mapping_from_config,
    priority_sample_records,
    validate_priority_mapping_config,
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


@router.get("/config", response_model=ERPConnectionConfig)
def get_erp_connection_config(
    tenant_id: UUID = Depends(resolve_tenant_id),
    adapter: str | None = None,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_READ)),
) -> ERPConnectionConfig:
    config = erp_agent.get_connection_config(tenant_id)
    if adapter is not None and adapter != str(config.adapter_type):
        raise HTTPException(status_code=404, detail="ERP adapter config not found")
    return config


@router.put("/priority/mapping", response_model=ERPConnectionConfig)
def configure_priority_mapping(
    request: PriorityMappingValidationRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_CONFIGURE)),
) -> ERPConnectionConfig:
    _enforce_body_tenant(request.tenant_id, context)
    validation = validate_priority_mapping_config(request.mapping)
    if validation.status in {"invalid", "mapping_required"}:
        raise HTTPException(status_code=422, detail=validation.model_dump(mode="json"))
    return erp_agent.configure_priority_mapping(request.tenant_id, request.mapping)


@router.get("/priority/mapping")
def get_priority_mapping(
    tenant_id: UUID = Depends(resolve_tenant_id),
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_READ)),
) -> dict:
    config = erp_agent.get_connection_config(tenant_id)
    mapping = priority_mapping_from_config(config.config)
    return {
        "tenant_id": tenant_id,
        "mapping": mapping.model_dump(mode="json") if mapping is not None else None,
    }


@router.post("/priority/validate-mapping", response_model=PriorityMappingValidationResult)
def validate_priority_mapping(
    request: PriorityMappingValidationRequest,
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_CONFIGURE)),
) -> PriorityMappingValidationResult:
    _enforce_body_tenant(request.tenant_id, context)
    return validate_priority_mapping_config(request.mapping)


@router.post("/priority/sync-preview", response_model=PrioritySyncPreviewResponse)
def preview_priority_sync(
    request: PrioritySyncPreviewRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PrioritySyncPreviewResponse:
    _enforce_body_tenant(request.tenant_id, context)
    return _build_priority_preview(request, erp_agent)


@router.post("/priority/import-plan", response_model=PriorityImportPlanResponse)
def plan_priority_import(
    request: PriorityImportPlanRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PriorityImportPlanResponse:
    _enforce_body_tenant(request.tenant_id, context)
    preview = _build_priority_preview(
        PrioritySyncPreviewRequest(
            tenant_id=request.tenant_id,
            kind=request.kind,
            limit=request.limit,
            sample_records=request.sample_records,
        ),
        erp_agent,
    )
    if preview.status in {"mapping_required", "invalid_mapping"}:
        return PriorityImportPlanResponse(
            status=preview.status,
            kind=preview.kind,
            mode=preview.mode,
            source=preview.source,
            records_planned=0,
            summary={
                "would_create": 0,
                "would_update": 0,
                "would_skip": 0,
                "would_conflict": 0,
            },
            items=[],
            warnings=preview.warnings,
            errors=preview.errors,
            message=preview.message,
        )
    if preview.kind == "vendors":
        return build_vendor_import_plan(
            preview.mapped_records,
            erp_agent.repository.list_vendors(request.tenant_id),
            erp_agent.repository.list_external_vendor_ids(request.tenant_id),
            kind=preview.kind,
            mode=preview.mode,
            source=preview.source,
            inherited_warnings=preview.warnings,
        )
    return build_purchase_order_import_plan(
        preview.mapped_records,
        erp_agent.repository.list_purchase_orders(request.tenant_id),
        erp_agent.repository.list_external_purchase_order_ids(request.tenant_id),
        kind=preview.kind,
        mode=preview.mode,
        source=preview.source,
        inherited_warnings=preview.warnings,
    )


@router.post("/priority/import-plan/vendors", response_model=PriorityImportPlanResponse)
def plan_priority_vendor_import(
    request: PriorityImportPlanRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PriorityImportPlanResponse:
    request.kind = "vendors"
    return plan_priority_import(request, erp_agent, context)


@router.post("/priority/import-plan/purchase-orders", response_model=PriorityImportPlanResponse)
def plan_priority_purchase_order_import(
    request: PriorityImportPlanRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PriorityImportPlanResponse:
    request.kind = "purchase_orders"
    return plan_priority_import(request, erp_agent, context)


def _build_priority_preview(
    request: PrioritySyncPreviewRequest,
    erp_agent: ERPConnectorAgent,
) -> PrioritySyncPreviewResponse:
    try:
        kind = _normalize_preview_kind(request.kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    config = erp_agent.get_connection_config(request.tenant_id)
    mapping = priority_mapping_from_config(config.config)
    mode = settings.priority_erp_mode if settings.priority_erp_mode in {"mock", "real"} else "mock"
    source = "sample"
    raw_records = request.sample_records

    if raw_records is None:
        entity_mapping = getattr(mapping, kind, None) if mapping is not None else None
        adapter = erp_agent.adapters.get(ERPAdapterType.PRIORITY)
        if mode == "real" and isinstance(adapter, PriorityODataAdapter) and entity_mapping is not None:
            try:
                raw_records = adapter.with_mapping_config(mapping).fetch_entity_rows(
                    entity_mapping.entity_name,
                    limit=request.limit,
                )
                source = "priority"
            except ERPAdapterError as exc:
                return PrioritySyncPreviewResponse(
                    status=str(exc.code),
                    kind=kind,
                    mode=mode,
                    source="priority",
                    mapping_status="unknown",
                    errors=[exc.message],
                    warnings=[],
                    message="Priority read-only preview failed before any data was imported.",
                )
        else:
            raw_records = priority_sample_records(kind, request.limit)

    return build_priority_sync_preview(
        kind=kind,
        mode=mode,
        source=source,
        mapping_config=mapping,
        raw_records=raw_records,
        limit=request.limit,
    )


@router.post("/priority/sync-preview/vendors", response_model=PrioritySyncPreviewResponse)
def preview_priority_vendor_sync(
    request: PrioritySyncPreviewRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PrioritySyncPreviewResponse:
    request.kind = "vendors"
    return preview_priority_sync(request, erp_agent, context)


@router.post("/priority/sync-preview/purchase-orders", response_model=PrioritySyncPreviewResponse)
def preview_priority_purchase_order_sync(
    request: PrioritySyncPreviewRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PrioritySyncPreviewResponse:
    request.kind = "purchase_orders"
    return preview_priority_sync(request, erp_agent, context)


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


def _normalize_preview_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized in {"vendor", "vendors"}:
        return "vendors"
    if normalized in {"purchase_order", "purchase_orders", "po", "pos"}:
        return "purchase_orders"
    raise ValueError("Priority sync preview kind must be vendors or purchase_orders.")
