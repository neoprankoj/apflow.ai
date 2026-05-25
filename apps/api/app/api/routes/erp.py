from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.agents.data.erp_connector_agent import ERPConnectorAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import get_audit_agent, get_erp_connector_agent, get_repository, require_permission, resolve_tenant_id
from app.core.config import settings
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    ERPConnectionConfig,
    ERPOperation,
    ERPAdapterType,
    ERPSyncStatus,
    ERPSyncRequest,
    ERPSyncResult,
    Permission,
    PriorityImportedPurchaseOrderRecord,
    PriorityImportedRecordsResponse,
    PriorityImportedVendorRecord,
    PriorityImportRequest,
    PriorityImportResult,
    PriorityImportResultItem,
    PriorityImportPlanRequest,
    PriorityImportPlanResponse,
    PriorityReadinessCheck,
    PriorityReadinessResponse,
    PrioritySyncPreviewRequest,
    PrioritySyncPreviewResponse,
    PriorityMappingValidationRequest,
    PriorityMappingValidationResult,
    UsageEventSource,
    UsageEventType,
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
from app.services.usage_metering_service import UsageMeteringService

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


@router.get("/priority/readiness", response_model=PriorityReadinessResponse)
def get_priority_readiness(
    tenant_id: UUID = Depends(resolve_tenant_id),
    check_remote: bool = False,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_READ)),
) -> PriorityReadinessResponse:
    del tenant_id
    return _build_priority_readiness(erp_agent, check_remote=check_remote)


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
            source=request.source,
            limit=request.limit,
            sample_records=request.sample_records,
        ),
        erp_agent,
    )
    if preview.status != "preview_ready":
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


@router.post("/priority/import", response_model=PriorityImportResult)
def import_priority_records(
    request: PriorityImportRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PriorityImportResult:
    _enforce_body_tenant(request.tenant_id, context)
    if request.confirmation != "IMPORT_SELECTED":
        raise HTTPException(status_code=400, detail="Type IMPORT_SELECTED to import selected records into APFlow.")
    selected_external_ids = _dedupe_selected_external_ids(request.selected_external_ids)
    if not selected_external_ids:
        raise HTTPException(status_code=400, detail="Select at least one Priority external ID to import.")

    plan = plan_priority_import(
        PriorityImportPlanRequest(
            tenant_id=request.tenant_id,
            kind=request.kind,
            source=request.source,
            limit=request.limit,
        ),
        erp_agent,
        context,
    )
    if plan.status != "plan_ready":
        return PriorityImportResult(
            status=plan.status,
            kind=plan.kind,
            summary=_empty_import_summary(),
            items=[],
            warnings=plan.warnings,
            errors=plan.errors,
            message=plan.message,
        )

    _record_priority_import_event(
        audit_agent,
        request,
        context,
        action="priority.import_started",
        entity_type="tenant",
        entity_id=request.tenant_id,
        metadata={
            "kind": plan.kind,
            "selected_external_ids": selected_external_ids,
            "allow_creates": request.allow_creates,
            "allow_updates": request.allow_updates,
            "source": plan.source,
            "priority_data_changed": False,
        },
    )

    if plan.kind == "vendors":
        result = _import_priority_vendors(request, plan, selected_external_ids, erp_agent, audit_agent, context)
    else:
        result = _import_priority_purchase_orders(request, plan, selected_external_ids, erp_agent, audit_agent, context)

    _record_priority_import_event(
        audit_agent,
        request,
        context,
        action="priority.import_completed",
        entity_type="tenant",
        entity_id=request.tenant_id,
        metadata={
            "kind": result.kind,
            "status": result.status,
            "summary": result.summary,
            "priority_data_changed": False,
        },
    )
    return result


@router.post("/priority/import/vendors", response_model=PriorityImportResult)
def import_priority_vendors(
    request: PriorityImportRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PriorityImportResult:
    request.kind = "vendors"
    return import_priority_records(request, erp_agent, audit_agent, context)


@router.post("/priority/import/purchase-orders", response_model=PriorityImportResult)
def import_priority_purchase_orders(
    request: PriorityImportRequest,
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> PriorityImportResult:
    request.kind = "purchase_orders"
    return import_priority_records(request, erp_agent, audit_agent, context)


@router.get("/priority/imported/vendors", response_model=PriorityImportedRecordsResponse)
def list_priority_imported_vendors(
    tenant_id: UUID = Depends(resolve_tenant_id),
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_READ)),
) -> PriorityImportedRecordsResponse:
    external_ids = erp_agent.repository.list_external_vendor_ids(tenant_id)
    import_events = _latest_priority_import_events(tenant_id, erp_agent, "vendor")
    records = [
        PriorityImportedVendorRecord(
            apflow_vendor_id=vendor.vendor_id,
            external_id=external_ids.get(vendor.vendor_id),
            name=vendor.name,
            tax_id=vendor.tax_id,
            imported_from_priority=vendor.vendor_id in external_ids,
            last_imported_at=_event_recorded_at(import_events.get(vendor.vendor_id)),
            last_import_action=_event_result(import_events.get(vendor.vendor_id)),
        )
        for vendor in erp_agent.repository.list_vendors(tenant_id)
    ]
    records.sort(key=lambda record: (not record.imported_from_priority, record.name.lower()))
    return PriorityImportedRecordsResponse(tenant_id=tenant_id, kind="vendors", records=records)


@router.get("/priority/imported/purchase-orders", response_model=PriorityImportedRecordsResponse)
def list_priority_imported_purchase_orders(
    tenant_id: UUID = Depends(resolve_tenant_id),
    erp_agent: ERPConnectorAgent = Depends(get_erp_connector_agent),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_READ)),
) -> PriorityImportedRecordsResponse:
    external_ids = erp_agent.repository.list_external_purchase_order_ids(tenant_id)
    vendor_external_ids = erp_agent.repository.list_external_vendor_ids(tenant_id)
    import_events = _latest_priority_import_events(tenant_id, erp_agent, "purchase_order")
    records = []
    for po in erp_agent.repository.list_purchase_orders(tenant_id):
        event = import_events.get(po.purchase_order_id)
        records.append(
            PriorityImportedPurchaseOrderRecord(
                apflow_purchase_order_id=po.purchase_order_id,
                po_number=po.po_number,
                external_id=external_ids.get(po.purchase_order_id),
                vendor_id=po.vendor_id,
                vendor_external_id=vendor_external_ids.get(po.vendor_id),
                status=po.status,
                total_amount=po.total_amount,
                currency=po.currency,
                imported_from_priority=po.purchase_order_id in external_ids,
                last_imported_at=_event_recorded_at(event),
                last_import_action=_event_result(event),
            )
        )
    records.sort(key=lambda record: (not record.imported_from_priority, record.po_number.lower()))
    return PriorityImportedRecordsResponse(tenant_id=tenant_id, kind="purchase_orders", records=records)


def _build_priority_preview(
    request: PrioritySyncPreviewRequest,
    erp_agent: ERPConnectorAgent,
) -> PrioritySyncPreviewResponse:
    try:
        kind = _normalize_preview_kind(request.kind)
        source = _normalize_preview_source(request.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    config = erp_agent.get_connection_config(request.tenant_id)
    mapping = priority_mapping_from_config(config.config)
    mode = settings.priority_erp_mode if settings.priority_erp_mode in {"mock", "real"} else "mock"
    limit = max(1, min(request.limit, settings.priority_erp_max_preview_records))
    raw_records = request.sample_records if source == "sample" else None

    if source == "sample":
        raw_records = raw_records if raw_records is not None else priority_sample_records(kind, limit)
    else:
        blocked = _priority_read_only_fetch_blocker(kind, mode, mapping)
        if blocked is not None:
            return blocked
        entity_mapping = getattr(mapping, kind)
        adapter = erp_agent.adapters.get(ERPAdapterType.PRIORITY)
        if not isinstance(adapter, PriorityODataAdapter):
            return PrioritySyncPreviewResponse(
                status="real_mode_required",
                kind=kind,
                mode=mode,
                source="priority",
                mapping_status="unknown",
                errors=["Priority real adapter is not active."],
                warnings=[],
                message="Priority read-only fetch requires PRIORITY_ERP_MODE=real.",
            )
        try:
            raw_records = adapter.with_mapping_config(mapping).fetch_entity_rows_read_only(
                entity_mapping.entity_name,
                limit=limit,
            )
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

    return build_priority_sync_preview(
        kind=kind,
        mode=mode,
        source=source,
        mapping_config=mapping,
        raw_records=raw_records,
        limit=limit,
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
    repository: InMemoryAPRepository = Depends(get_repository),
    context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_EXPORT_ERP)),
) -> ERPSyncResult:
    _enforce_body_tenant(request.tenant_id, context)
    request.operation = ERPOperation.EXPORT_INVOICE
    result = erp_agent.run(request)
    if result.status == ERPSyncStatus.SUCCESS:
        UsageMeteringService(repository).record_usage_event(
            request.tenant_id,
            UsageEventType.ERP_EXPORT_MOCKED,
            source=UsageEventSource.USER,
            related_invoice_id=request.invoice_id,
            metadata={"adapter_type": str(request.adapter_type), "operation": str(request.operation)},
        )
    return result


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


def _normalize_preview_source(source: str) -> str:
    normalized = source.strip().lower()
    if normalized in {"sample", "samples"}:
        return "sample"
    if normalized in {"priority", "real", "odata"}:
        return "priority"
    raise ValueError("Priority sync preview source must be sample or priority.")


def _build_priority_readiness(
    erp_agent: ERPConnectorAgent,
    *,
    check_remote: bool,
) -> PriorityReadinessResponse:
    mode = settings.priority_erp_mode if settings.priority_erp_mode in {"mock", "real"} else "mock"
    read_only_enabled = settings.priority_erp_read_only_fetch_enabled
    writes_enabled = settings.priority_erp_enable_writes
    base_url_configured = bool(settings.priority_erp_base_url.strip())
    company_configured = bool(settings.priority_erp_company.strip())
    environment_configured = bool(settings.priority_erp_environment.strip())
    auth_configured = bool(settings.priority_erp_username.strip() and _priority_secret_configured())
    checks = [
        _readiness_check(
            "mode",
            "Priority mode real",
            "ok" if mode == "real" else "disabled",
            "Priority real mode is configured." if mode == "real" else "Priority is currently running in mock mode.",
        ),
        _readiness_check(
            "base_url",
            "Base URL configured",
            "ok" if base_url_configured else "missing",
            "Priority base URL is configured." if base_url_configured else "Set PRIORITY_ERP_BASE_URL on the server.",
            safe_detail=_priority_base_url_host(),
        ),
        _readiness_check(
            "company",
            "Company configured",
            "ok" if company_configured else "not_applicable",
            "Priority company is configured." if company_configured else "Company may be embedded in the Priority OData base URL.",
        ),
        _readiness_check(
            "environment",
            "Environment configured",
            "ok" if environment_configured else "not_applicable",
            "Priority environment is configured." if environment_configured else "Environment may be embedded in the Priority OData base URL.",
        ),
        _readiness_check(
            "auth",
            "Authentication configured",
            "ok" if auth_configured else "missing",
            "Priority username and password/token are configured." if auth_configured else "Set Priority username and password or API key on the server.",
        ),
        _readiness_check(
            "read_only_fetch",
            "Read-only fetch enabled",
            "ok" if read_only_enabled else "disabled",
            "Read-only fetch is enabled." if read_only_enabled else "Set PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=true before real previews.",
        ),
        _readiness_check(
            "writes_disabled",
            "Real writes disabled",
            "ok" if not writes_enabled else "warning",
            "Priority writes are disabled." if not writes_enabled else "Priority writes are enabled. Confirm this is intentional.",
        ),
    ]
    warnings: list[str] = []
    errors: list[str] = []
    service_root_checked = False
    metadata_checked = False
    service_root_available: bool | None = None
    metadata_available: bool | None = None

    remote_blocker = _priority_remote_drill_blocker(mode, read_only_enabled, base_url_configured, auth_configured)
    if check_remote and remote_blocker is not None:
        checks.append(remote_blocker)
        errors.append(remote_blocker.message)
    elif check_remote:
        adapter = erp_agent.adapters.get(ERPAdapterType.PRIORITY)
        if not isinstance(adapter, PriorityODataAdapter):
            check = _readiness_check(
                "real_adapter",
                "Priority real adapter active",
                "missing",
                "Priority real adapter is not active.",
            )
            checks.append(check)
            errors.append(check.message)
        else:
            service_root_checked = True
            service_root_result = adapter.check_service_root()
            service_root_available = service_root_result.get("status") == "ok"
            checks.append(_remote_result_check("service_root", "Service root reachable", service_root_result))
            if not service_root_available:
                errors.append(str(service_root_result.get("message", "Priority service root check failed.")))
            else:
                metadata_checked = True
                metadata_result = adapter.check_metadata()
                metadata_available = metadata_result.get("status") == "ok"
                checks.append(_remote_result_check("metadata", "Metadata reachable", metadata_result))
                if not metadata_available:
                    warnings.append(str(metadata_result.get("message", "Priority metadata was not available.")))
    else:
        checks.extend(
            [
                _readiness_check(
                    "service_root",
                    "Service root reachable",
                    "not_applicable",
                    "Run the remote connection drill to check service-root reachability.",
                ),
                _readiness_check(
                    "metadata",
                    "Metadata reachable",
                    "not_applicable",
                    "Run the remote connection drill to check metadata reachability.",
                ),
            ]
        )

    local_ready = mode == "real" and read_only_enabled and base_url_configured and auth_configured
    if check_remote and service_root_available and metadata_available and local_ready:
        status = "ready"
        message = "Priority real read-only connection is ready for limited preview fetches."
    elif check_remote and local_ready and service_root_available:
        status = "partially_ready"
        message = "Priority service root is reachable, but metadata was not confirmed."
    elif check_remote and local_ready:
        status = "not_ready"
        message = "Priority remote connection drill did not complete. Review the checklist before real preview fetches."
    elif local_ready:
        status = "partially_ready"
        message = "Priority local configuration is present. Run the remote connection drill before real preview fetches."
    else:
        status = "not_ready"
        message = "Priority real read-only fetch is not ready. Review the checklist before enabling real previews."
    if writes_enabled:
        warnings.append("Priority real writes are enabled. Keep PRIORITY_ERP_ENABLE_WRITES=false during read-only testing.")

    return PriorityReadinessResponse(
        status=status,
        mode=mode,
        read_only_fetch_enabled=read_only_enabled,
        writes_enabled=writes_enabled,
        base_url_configured=base_url_configured,
        company_configured=company_configured,
        environment_configured=environment_configured,
        auth_configured=auth_configured,
        service_root_checked=service_root_checked,
        metadata_checked=metadata_checked,
        service_root_available=service_root_available,
        metadata_available=metadata_available,
        checks=checks,
        warnings=warnings,
        errors=errors,
        message=message,
    )


def _priority_secret_configured() -> bool:
    return bool(settings.priority_erp_password.strip() or settings.priority_erp_api_key.strip())


def _priority_base_url_host() -> str | None:
    return urlparse(settings.priority_erp_base_url).hostname


def _readiness_check(
    key: str,
    label: str,
    status: str,
    message: str,
    *,
    safe_detail: str | None = None,
) -> PriorityReadinessCheck:
    return PriorityReadinessCheck(
        key=key,
        label=label,
        status=status,
        message=message,
        safe_detail=safe_detail,
    )


def _priority_remote_drill_blocker(
    mode: str,
    read_only_enabled: bool,
    base_url_configured: bool,
    auth_configured: bool,
) -> PriorityReadinessCheck | None:
    if mode != "real":
        return _readiness_check(
            "remote_drill",
            "Remote connection drill",
            "disabled",
            "Remote drill requires PRIORITY_ERP_MODE=real.",
        )
    if not read_only_enabled:
        return _readiness_check(
            "remote_drill",
            "Remote connection drill",
            "disabled",
            "Remote drill requires PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=true.",
        )
    if not base_url_configured:
        return _readiness_check(
            "remote_drill",
            "Remote connection drill",
            "missing",
            "Remote drill requires PRIORITY_ERP_BASE_URL.",
        )
    if not auth_configured:
        return _readiness_check(
            "remote_drill",
            "Remote connection drill",
            "missing",
            "Remote drill requires Priority username and password or API key.",
        )
    return None


def _remote_result_check(key: str, label: str, result: dict) -> PriorityReadinessCheck:
    status = "ok" if result.get("status") == "ok" else "warning"
    return _readiness_check(
        key,
        label,
        status,
        str(result.get("message") or "Priority remote check completed."),
        safe_detail=str(result.get("base_url_host") or "") or None,
    )


def _priority_read_only_fetch_blocker(
    kind: str,
    mode: str,
    mapping,
) -> PrioritySyncPreviewResponse | None:
    entity_mapping = getattr(mapping, kind, None) if mapping is not None else None
    if mode != "real":
        return PrioritySyncPreviewResponse(
            status="real_mode_required",
            kind=kind,
            mode=mode,
            source="priority",
            mapping_status="unknown",
            errors=["Priority read-only fetch requires PRIORITY_ERP_MODE=real."],
            warnings=[],
            message="Use sample preview until Priority real mode is configured.",
        )
    if not settings.priority_erp_read_only_fetch_enabled:
        return PrioritySyncPreviewResponse(
            status="read_only_fetch_disabled",
            kind=kind,
            mode=mode,
            source="priority",
            mapping_status="unknown",
            errors=["Priority read-only fetch is disabled."],
            warnings=[],
            message="Priority read-only fetch is disabled. Use sample preview or enable it in environment configuration.",
        )
    if entity_mapping is None or not entity_mapping.enabled:
        return PrioritySyncPreviewResponse(
            status="mapping_required",
            kind=kind,
            mode=mode,
            source="priority",
            mapping_status="mapping_required",
            errors=[f"Priority {kind.replace('_', ' ')} mapping is not configured."],
            warnings=[],
            message="Save a Priority mapping before running a read-only fetch preview.",
        )
    return None


def _import_priority_vendors(
    request: PriorityImportRequest,
    plan: PriorityImportPlanResponse,
    selected_external_ids: list[str],
    erp_agent: ERPConnectorAgent,
    audit_agent: AuditLoggingAgent,
    context: CurrentUserContext,
) -> PriorityImportResult:
    plan_items = _plan_items_by_external_id(plan)
    result_items: list[PriorityImportResultItem] = []
    for external_id in selected_external_ids:
        item = plan_items.get(external_id)
        if item is None:
            result_items.append(_missing_selection_result(external_id))
            continue
        result = _import_priority_vendor_item(request, item, erp_agent, audit_agent, context)
        result_items.append(result)
    return _priority_import_response("vendors", result_items)


def _import_priority_vendor_item(
    request: PriorityImportRequest,
    item,
    erp_agent: ERPConnectorAgent,
    audit_agent: AuditLoggingAgent,
    context: CurrentUserContext,
) -> PriorityImportResultItem:
    external_id = _string_or_none(item.mapped_record.get("external_id"))
    action = item.action
    if action == "would_conflict":
        result = _blocked_result(external_id, action, "conflict", "Conflicts are never imported.", item.warnings)
        _record_item_event(audit_agent, request, context, "priority.vendor_import_conflict", result)
        return result
    if action == "would_skip":
        return PriorityImportResultItem(
            external_id=external_id,
            action_requested=action,
            result="skipped",
            apflow_record_id=item.matched_existing_id,
            reason="Existing vendor already matches mapped fields.",
            warnings=item.warnings,
        )
    if action == "would_create":
        if not request.allow_creates:
            return _blocked_result(external_id, action, "blocked", "Creates were not enabled.", item.warnings)
        name = _string_or_none(item.mapped_record.get("name"))
        if not name:
            return _blocked_result(external_id, action, "blocked", "Vendor name is required before import.", item.warnings)
        vendor = erp_agent.repository.add_vendor(
            tenant_id=request.tenant_id,
            name=name,
            tax_id=_string_or_none(item.mapped_record.get("tax_id")),
        )
        if external_id:
            erp_agent.repository.link_external_vendor_id(request.tenant_id, vendor.vendor_id, external_id)
        result = PriorityImportResultItem(
            external_id=external_id,
            action_requested=action,
            result="created",
            apflow_record_id=str(vendor.vendor_id),
            reason="Vendor imported into APFlow. No Priority data was changed.",
            warnings=_unsupported_vendor_field_warnings(item.mapped_record),
        )
        _record_item_event(audit_agent, request, context, "priority.vendor_created", result)
        return result
    if action == "would_update":
        if not request.allow_updates:
            return _blocked_result(external_id, action, "blocked", "Updates were not enabled.", item.warnings)
        if item.matched_existing_id is None:
            return _blocked_result(external_id, action, "blocked", "Matched vendor ID is missing.", item.warnings)
        vendor = erp_agent.repository.update_vendor(
            request.tenant_id,
            UUID(item.matched_existing_id),
            name=_string_or_none(item.mapped_record.get("name")),
            tax_id=_string_or_none(item.mapped_record.get("tax_id")),
        )
        if external_id:
            erp_agent.repository.link_external_vendor_id(request.tenant_id, vendor.vendor_id, external_id)
        result = PriorityImportResultItem(
            external_id=external_id,
            action_requested=action,
            result="updated",
            apflow_record_id=str(vendor.vendor_id),
            reason="Vendor updated in APFlow. No Priority data was changed.",
            warnings=_unsupported_vendor_field_warnings(item.mapped_record),
        )
        _record_item_event(audit_agent, request, context, "priority.vendor_updated", result)
        return result
    return _blocked_result(external_id, action, "blocked", "This import-plan action is not importable.", item.warnings)


def _import_priority_purchase_orders(
    request: PriorityImportRequest,
    plan: PriorityImportPlanResponse,
    selected_external_ids: list[str],
    erp_agent: ERPConnectorAgent,
    audit_agent: AuditLoggingAgent,
    context: CurrentUserContext,
) -> PriorityImportResult:
    plan_items = _plan_items_by_external_id(plan)
    result_items: list[PriorityImportResultItem] = []
    for external_id in selected_external_ids:
        item = plan_items.get(external_id)
        if item is None:
            result_items.append(_missing_selection_result(external_id))
            continue
        result = _import_priority_purchase_order_item(request, item, erp_agent, audit_agent, context)
        result_items.append(result)
    return _priority_import_response("purchase_orders", result_items)


def _import_priority_purchase_order_item(
    request: PriorityImportRequest,
    item,
    erp_agent: ERPConnectorAgent,
    audit_agent: AuditLoggingAgent,
    context: CurrentUserContext,
) -> PriorityImportResultItem:
    external_id = _string_or_none(item.mapped_record.get("external_id"))
    action = item.action
    if action == "would_conflict":
        result = _blocked_result(external_id, action, "conflict", "Conflicts are never imported.", item.warnings)
        _record_item_event(audit_agent, request, context, "priority.purchase_order_import_conflict", result)
        return result
    if action == "would_skip":
        return PriorityImportResultItem(
            external_id=external_id,
            action_requested=action,
            result="skipped",
            apflow_record_id=item.matched_existing_id,
            reason="Existing purchase order already matches mapped fields.",
            warnings=item.warnings,
        )
    vendor_id, vendor_warning = _resolve_vendor_id_for_po(request.tenant_id, item.mapped_record, erp_agent)
    if vendor_id is None:
        result = _blocked_result(
            external_id,
            action,
            "blocked",
            vendor_warning or "Vendor must be imported before purchase orders.",
            item.warnings,
        )
        _record_item_event(audit_agent, request, context, "priority.purchase_order_import_blocked", result)
        return result
    if action == "would_create":
        if not request.allow_creates:
            return _blocked_result(external_id, action, "blocked", "Creates were not enabled.", item.warnings)
        po_number = _string_or_none(item.mapped_record.get("po_number"))
        total_amount = _float_or_none(item.mapped_record.get("total_amount"))
        if not po_number or total_amount is None:
            return _blocked_result(
                external_id,
                action,
                "blocked",
                "PO number and numeric amount are required before import.",
                item.warnings,
            )
        po = erp_agent.repository.add_purchase_order(
            tenant_id=request.tenant_id,
            po_number=po_number,
            vendor_id=vendor_id,
            total_amount=total_amount,
            currency=_string_or_none(item.mapped_record.get("currency")) or "USD",
        )
        status = _string_or_none(item.mapped_record.get("status"))
        if status:
            po = erp_agent.repository.update_purchase_order(request.tenant_id, po.purchase_order_id, status=status)
        if external_id:
            erp_agent.repository.link_external_purchase_order_id(request.tenant_id, po.purchase_order_id, external_id)
        result = PriorityImportResultItem(
            external_id=external_id,
            action_requested=action,
            result="created",
            apflow_record_id=str(po.purchase_order_id),
            reason="Purchase order imported into APFlow. No Priority data was changed.",
            warnings=item.warnings,
        )
        _record_item_event(audit_agent, request, context, "priority.purchase_order_created", result)
        return result
    if action == "would_update":
        if not request.allow_updates:
            return _blocked_result(external_id, action, "blocked", "Updates were not enabled.", item.warnings)
        if item.matched_existing_id is None:
            return _blocked_result(external_id, action, "blocked", "Matched purchase order ID is missing.", item.warnings)
        po = erp_agent.repository.update_purchase_order(
            request.tenant_id,
            UUID(item.matched_existing_id),
            po_number=_string_or_none(item.mapped_record.get("po_number")),
            vendor_id=vendor_id,
            total_amount=_float_or_none(item.mapped_record.get("total_amount")),
            currency=_string_or_none(item.mapped_record.get("currency")),
            status=_string_or_none(item.mapped_record.get("status")),
        )
        if external_id:
            erp_agent.repository.link_external_purchase_order_id(request.tenant_id, po.purchase_order_id, external_id)
        result = PriorityImportResultItem(
            external_id=external_id,
            action_requested=action,
            result="updated",
            apflow_record_id=str(po.purchase_order_id),
            reason="Purchase order updated in APFlow. No Priority data was changed.",
            warnings=item.warnings,
        )
        _record_item_event(audit_agent, request, context, "priority.purchase_order_updated", result)
        return result
    return _blocked_result(external_id, action, "blocked", "This import-plan action is not importable.", item.warnings)


def _resolve_vendor_id_for_po(tenant_id: UUID, mapped_record: dict, erp_agent: ERPConnectorAgent) -> tuple[UUID | None, str | None]:
    vendor_external_id = _string_or_none(mapped_record.get("vendor_external_id"))
    if not vendor_external_id:
        return None, "Vendor external ID is required before importing purchase orders."
    external_vendor_ids = erp_agent.repository.list_external_vendor_ids(tenant_id)
    for vendor_id, external_id in external_vendor_ids.items():
        if external_id == vendor_external_id:
            return vendor_id, None
    return None, f"Vendor {vendor_external_id} must be imported before this purchase order."


def _priority_import_response(kind: str, items: list[PriorityImportResultItem]) -> PriorityImportResult:
    summary = _empty_import_summary()
    for item in items:
        summary_key = "conflicts" if item.result == "conflict" else item.result
        summary[summary_key] = summary.get(summary_key, 0) + 1
    successful = summary["created"] + summary["updated"] + summary["skipped"]
    blocked = summary["blocked"] + summary["conflicts"] + summary["failed"]
    if blocked and successful:
        status = "partial"
    elif blocked:
        status = "blocked"
    else:
        status = "imported"
    return PriorityImportResult(
        status=status,
        kind=kind,
        summary=summary,
        items=items,
        message="Selected records were imported into APFlow. No Priority data was changed."
        if successful
        else "Selected records were not imported. No Priority data was changed.",
    )


def _plan_items_by_external_id(plan: PriorityImportPlanResponse) -> dict[str, object]:
    items: dict[str, object] = {}
    for item in plan.items:
        external_id = _string_or_none(item.mapped_record.get("external_id"))
        if external_id:
            items[external_id] = item
    return items


def _dedupe_selected_external_ids(values: list[str]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            selected.append(normalized)
            seen.add(normalized)
    return selected


def _empty_import_summary() -> dict[str, int]:
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "conflicts": 0,
        "blocked": 0,
        "failed": 0,
    }


def _missing_selection_result(external_id: str) -> PriorityImportResultItem:
    return PriorityImportResultItem(
        external_id=external_id,
        action_requested="not_found",
        result="failed",
        reason="Selected external ID was not found in the current server-side import plan.",
    )


def _blocked_result(
    external_id: str | None,
    action: str,
    result: str,
    reason: str,
    warnings: list[str] | None = None,
) -> PriorityImportResultItem:
    return PriorityImportResultItem(
        external_id=external_id,
        action_requested=action,
        result=result,
        reason=reason,
        warnings=warnings or [],
    )


def _record_item_event(
    audit_agent: AuditLoggingAgent,
    request: PriorityImportRequest,
    context: CurrentUserContext,
    action: str,
    item: PriorityImportResultItem,
) -> None:
    _record_priority_import_event(
        audit_agent,
        request,
        context,
        action=action,
        entity_type=request.kind,
        entity_id=UUID(item.apflow_record_id) if item.apflow_record_id else request.tenant_id,
        metadata={
            "external_id": item.external_id,
            "action_requested": item.action_requested,
            "result": item.result,
            "reason": item.reason,
            "priority_data_changed": False,
        },
    )


def _record_priority_import_event(
    audit_agent: AuditLoggingAgent,
    request: PriorityImportRequest,
    context: CurrentUserContext,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    metadata: dict,
) -> None:
    audit_agent.record(
        AuditEventInput(
            tenant_id=request.tenant_id,
            actor_type=ActorType.USER,
            actor_id=str(context.user.id),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata={"source": "Priority sync import", **metadata},
        )
    )


def _latest_priority_import_events(tenant_id: UUID, erp_agent: ERPConnectorAgent, entity_label: str) -> dict[UUID, object]:
    events: dict[UUID, object] = {}
    action_prefix = f"priority.{entity_label}_"
    for event in erp_agent.repository.list_audit_events(tenant_id):
        if not event.action.startswith(action_prefix):
            continue
        if not event.action.endswith(("_created", "_updated")):
            continue
        previous = events.get(event.entity_id)
        if previous is None or event.recorded_at > previous.recorded_at:
            events[event.entity_id] = event
    return events


def _event_recorded_at(event: object | None):
    return getattr(event, "recorded_at", None) if event is not None else None


def _event_result(event: object | None) -> str | None:
    if event is None:
        return None
    metadata = getattr(event, "metadata", {}) or {}
    result = metadata.get("result")
    if result:
        return str(result)
    action = getattr(event, "action", "")
    if action.startswith("priority.vendor_"):
        return action.removeprefix("priority.vendor_")
    if action.startswith("priority.purchase_order_"):
        return action.removeprefix("priority.purchase_order_")
    return None


def _unsupported_vendor_field_warnings(mapped_record: dict) -> list[str]:
    warnings: list[str] = []
    if mapped_record.get("email"):
        warnings.append("Vendor email is not stored by the current APFlow vendor model.")
    if mapped_record.get("payment_terms"):
        warnings.append("Vendor payment terms are not stored by the current APFlow vendor model.")
    return warnings


def _float_or_none(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
