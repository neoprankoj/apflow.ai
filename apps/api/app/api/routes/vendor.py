from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.agents.interface.payment_status_chatbot_agent import PaymentStatusChatbotAgent
from app.agents.interface.vendor_communication_agent import VendorCommunicationAgent
from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.api.dependencies import (
    get_audit_agent,
    get_payment_status_chatbot_agent,
    get_repository,
    get_vendor_communication_agent,
    require_permission,
    resolve_tenant_id,
)
from app.core.repositories import InMemoryAPRepository, VendorPortalAccessRecord
from app.core.config import settings
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    MetricEventInput,
    Permission,
    VendorAccessCreateRequest,
    VendorAccessCreatedResponse,
    VendorAccessRead,
    VendorAccessRevokeResponse,
    VendorAccessRotateResponse,
    VendorChatRequest,
    VendorChatResponse,
    VendorInvoiceListItem,
    VendorInvoiceStatus,
    VendorMessageCreate,
    VendorMessageResult,
    VendorPortalAccessCreate,
    VendorPortalAccessResult,
)
from app.core.vendor_portal import (
    generate_vendor_access_token,
    hash_vendor_access_token,
    invoice_is_visible_to_vendor,
    vendor_access_token_prefix,
    vendor_invoice_list_item,
    vendor_invoice_status,
)
from app.api.dependencies import get_monitoring_agent

router = APIRouter()


@router.post("/access", response_model=VendorPortalAccessResult)
def create_vendor_access(
    payload: VendorPortalAccessCreate,
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> VendorPortalAccessResult:
    if settings.app_env == "production":
        raise HTTPException(status_code=403, detail="Demo vendor access creation is disabled in production")
    raw_token, record = _create_vendor_access(
        repository,
        tenant_id=payload.tenant_id,
        email=payload.email,
        vendor_id=payload.vendor_id,
        vendor_name=payload.vendor_name,
        expires_at=_expires_at(payload.expires_at, payload.ttl_days),
        label=payload.label or "Demo vendor portal access",
    )
    audit_agent.record(
        AuditEventInput(
            tenant_id=payload.tenant_id,
            actor_type=ActorType.USER,
            actor_id="vendor-access-demo",
            action="vendor.access_created",
            entity_type="vendor",
            entity_id=record.vendor_id,
            metadata={"email": payload.email, "access_id": str(record.access_id), "token_prefix": record.token_prefix},
        )
    )
    return VendorPortalAccessResult(
        access_id=record.access_id,
        tenant_id=record.tenant_id,
        vendor_id=record.vendor_id,
        email=record.email,
        status=record.status,
        access_token=raw_token,
        token_prefix=record.token_prefix,
        label=record.label,
        access_url=_access_url(raw_token),
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


@router.post("/accesses", response_model=VendorAccessCreatedResponse)
def create_vendor_access_for_admin(
    payload: VendorAccessCreateRequest,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> VendorAccessCreatedResponse:
    if payload.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
    raw_token, record = _create_vendor_access(
        repository,
        tenant_id=tenant_id,
        email=payload.email,
        vendor_id=payload.vendor_id,
        vendor_name=payload.vendor_name or payload.supplier_name,
        expires_at=_expires_at(payload.expires_at, payload.ttl_days),
        label=payload.label,
        created_by_user_id=context.user.id,
    )
    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id=context.user.email,
            action="vendor.access_created",
            entity_type="vendor",
            entity_id=record.vendor_id,
            metadata={"access_id": str(record.access_id), "token_prefix": record.token_prefix, "email": record.email},
        )
    )
    return VendorAccessCreatedResponse(
        **_vendor_access_read(repository, record).model_dump(),
        access_token=raw_token,
        access_url=_access_url(raw_token),
    )


@router.get("/accesses", response_model=list[VendorAccessRead])
def list_vendor_accesses(
    tenant_id: UUID = Depends(resolve_tenant_id),
    vendor_id: UUID | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> list[VendorAccessRead]:
    records = repository.list_vendor_portal_access(tenant_id)
    if vendor_id is not None:
        records = [record for record in records if record.vendor_id == vendor_id]
    return [_vendor_access_read(repository, record) for record in records]


@router.get("/accesses/{access_id}", response_model=VendorAccessRead)
def get_vendor_access(
    access_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> VendorAccessRead:
    try:
        record = repository.get_vendor_portal_access(tenant_id, access_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Vendor access not found") from exc
    return _vendor_access_read(repository, record)


@router.post("/accesses/{access_id}/revoke", response_model=VendorAccessRevokeResponse)
def revoke_vendor_access(
    access_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> VendorAccessRevokeResponse:
    try:
        record = repository.revoke_vendor_portal_access(tenant_id, access_id, revoked_by_user_id=context.user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Vendor access not found") from exc
    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id=context.user.email,
            action="vendor.access_revoked",
            entity_type="vendor",
            entity_id=record.vendor_id,
            metadata={"access_id": str(record.access_id), "token_prefix": record.token_prefix},
        )
    )
    return VendorAccessRevokeResponse(
        id=record.access_id,
        status=record.status,
        revoked_at=record.revoked_at,
        message="Vendor access was revoked. The old token no longer works.",
    )


@router.post("/accesses/{access_id}/rotate", response_model=VendorAccessRotateResponse)
def rotate_vendor_access(
    access_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
    context: CurrentUserContext = Depends(require_permission(Permission.ERP_SYNC)),
) -> VendorAccessRotateResponse:
    try:
        old_record = repository.revoke_vendor_portal_access(tenant_id, access_id, revoked_by_user_id=context.user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Vendor access not found") from exc
    raw_token, new_record = _create_vendor_access(
        repository,
        tenant_id=tenant_id,
        email=old_record.email,
        vendor_id=old_record.vendor_id,
        vendor_name=None,
        expires_at=old_record.expires_at,
        label=old_record.label,
        created_by_user_id=context.user.id,
        rotated_from_access_id=old_record.access_id,
    )
    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.USER,
            actor_id=context.user.email,
            action="vendor.access_rotated",
            entity_type="vendor",
            entity_id=old_record.vendor_id,
            metadata={
                "old_access_id": str(old_record.access_id),
                "new_access_id": str(new_record.access_id),
                "new_token_prefix": new_record.token_prefix,
            },
        )
    )
    return VendorAccessRotateResponse(
        old_access=_vendor_access_read(repository, old_record),
        new_access=_vendor_access_read(repository, new_record),
        access_token=raw_token,
        access_url=_access_url(raw_token),
    )


@router.get("/invoices", response_model=list[VendorInvoiceListItem])
def list_vendor_invoices(
    tenant_id: UUID,
    x_vendor_access_token: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> list[VendorInvoiceListItem]:
    access = _resolve_vendor_access(tenant_id, x_vendor_access_token or access_token, repository, audit_agent)
    invoices = [
        invoice
        for invoice in repository.list_invoices(tenant_id)
        if invoice_is_visible_to_vendor(invoice, access.vendor_id)
    ]
    return [vendor_invoice_list_item(repository, tenant_id, invoice) for invoice in invoices]


@router.get("/invoices/{invoice_id}", response_model=VendorInvoiceStatus)
def get_vendor_invoice(
    invoice_id: UUID,
    tenant_id: UUID,
    x_vendor_access_token: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> VendorInvoiceStatus:
    access = _resolve_vendor_access(tenant_id, x_vendor_access_token or access_token, repository, audit_agent)
    try:
        invoice = repository.get_invoice(tenant_id, invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Invoice not found") from exc
    if not invoice_is_visible_to_vendor(invoice, access.vendor_id):
        raise HTTPException(status_code=403, detail="Invoice is outside vendor scope")
    result = vendor_invoice_status(repository, tenant_id, invoice)
    audit_agent.record(
        AuditEventInput(
            tenant_id=tenant_id,
            actor_type=ActorType.VENDOR,
            actor_id=access.email,
            action="vendor.invoice_preview_viewed",
            entity_type="invoice",
            entity_id=invoice.invoice_id,
            metadata={"access_id": str(access.access_id), "token_prefix": access.token_prefix},
        )
    )
    return result


@router.get("/preview/invoices/{invoice_id}", response_model=VendorInvoiceStatus)
def preview_vendor_invoice_for_internal_user(
    invoice_id: UUID,
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> VendorInvoiceStatus:
    try:
        invoice = repository.get_invoice(tenant_id, invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Invoice not found") from exc
    return vendor_invoice_status(repository, tenant_id, invoice)


@router.post("/messages", response_model=VendorMessageResult)
def submit_vendor_message(
    payload: VendorMessageCreate,
    x_vendor_access_token: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
    communication_agent: VendorCommunicationAgent = Depends(get_vendor_communication_agent),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> VendorMessageResult:
    access = _resolve_vendor_access(payload.tenant_id, x_vendor_access_token or access_token, repository, audit_agent)
    return communication_agent.submit_message(payload, access.vendor_id)


@router.post("/chat", response_model=VendorChatResponse)
def vendor_chat(
    payload: VendorChatRequest,
    x_vendor_access_token: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
    chatbot_agent: PaymentStatusChatbotAgent = Depends(get_payment_status_chatbot_agent),
    audit_agent: AuditLoggingAgent = Depends(get_audit_agent),
) -> VendorChatResponse:
    access = _resolve_vendor_access(payload.tenant_id, x_vendor_access_token or access_token, repository, audit_agent)
    return chatbot_agent.answer(payload, access.vendor_id)


@router.get("/messages", response_model=list[VendorMessageResult])
def list_vendor_messages_for_internal_users(
    tenant_id: UUID = Depends(resolve_tenant_id),
    repository: InMemoryAPRepository = Depends(get_repository),
    _context: CurrentUserContext = Depends(require_permission(Permission.INVOICE_READ)),
) -> list[VendorMessageResult]:
    return repository.list_vendor_messages(tenant_id)


def _resolve_vendor_access(
    tenant_id: UUID,
    token: str | None,
    repository: InMemoryAPRepository,
    audit_agent: AuditLoggingAgent | None = None,
) -> VendorPortalAccessRecord:
    if not token:
        get_monitoring_agent().record_metric(
            MetricEventInput(
                tenant_id=tenant_id,
                metric_event="vendor.access_missing",
                value=1,
                metadata={},
            )
        )
        raise HTTPException(status_code=401, detail="Missing vendor access token")
    access = repository.get_vendor_access_by_hash(tenant_id, hash_vendor_access_token(token))
    if access is None:
        get_monitoring_agent().record_metric(
            MetricEventInput(
                tenant_id=tenant_id,
                metric_event="vendor.access_denied",
                value=1,
                metadata={},
            )
        )
        raise HTTPException(status_code=403, detail="Invalid vendor access")
    access = repository.mark_vendor_access_used(tenant_id, access.access_id)
    if audit_agent is not None:
        audit_agent.record(
            AuditEventInput(
                tenant_id=tenant_id,
                actor_type=ActorType.VENDOR,
                actor_id=access.email,
                action="vendor.access_used",
                entity_type="vendor",
                entity_id=access.vendor_id,
                metadata={"access_id": str(access.access_id), "token_prefix": access.token_prefix},
            )
        )
    return access


def _create_vendor_access(
    repository: InMemoryAPRepository,
    *,
    tenant_id: UUID,
    email: str,
    vendor_id: UUID | None,
    vendor_name: str | None,
    expires_at: datetime | None,
    label: str | None,
    created_by_user_id: UUID | None = None,
    rotated_from_access_id: UUID | None = None,
) -> tuple[str, VendorPortalAccessRecord]:
    resolved_vendor_id = vendor_id
    if resolved_vendor_id is None:
        vendors = repository.list_vendors(tenant_id)
        if vendor_name:
            vendor = repository.add_vendor(tenant_id, vendor_name)
        elif vendors:
            vendor = vendors[0]
        else:
            vendor = repository.add_vendor(tenant_id, email.split("@")[0])
        resolved_vendor_id = vendor.vendor_id
    elif not any(vendor.vendor_id == resolved_vendor_id for vendor in repository.list_vendors(tenant_id)):
        raise HTTPException(status_code=404, detail="Vendor not found for tenant")

    raw_token = generate_vendor_access_token()
    record = repository.create_vendor_portal_access(
        tenant_id=tenant_id,
        vendor_id=resolved_vendor_id,
        email=email,
        access_token_hash=hash_vendor_access_token(raw_token),
        expires_at=expires_at,
        token_prefix=vendor_access_token_prefix(raw_token),
        label=label,
        created_by_user_id=created_by_user_id,
        rotated_from_access_id=rotated_from_access_id,
    )
    return raw_token, record


def _vendor_access_read(repository: InMemoryAPRepository, record: VendorPortalAccessRecord) -> VendorAccessRead:
    vendor_name = next(
        (vendor.name for vendor in repository.list_vendors(record.tenant_id) if vendor.vendor_id == record.vendor_id),
        None,
    )
    status = record.status
    if status == "active" and record.expires_at is not None and record.expires_at < datetime.now(UTC):
        status = "expired"
    return VendorAccessRead(
        id=record.access_id,
        tenant_id=record.tenant_id,
        vendor_id=record.vendor_id,
        vendor_name=vendor_name,
        email=record.email,
        label=record.label,
        status=status,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        revoked_by_user_id=record.revoked_by_user_id,
        created_by_user_id=record.created_by_user_id,
        rotated_from_access_id=record.rotated_from_access_id,
        last_used_at=record.last_used_at,
        token_prefix=record.token_prefix,
        created_at=record.created_at,
    )


def _expires_at(explicit: datetime | None, ttl_days: int | None) -> datetime | None:
    if explicit is not None:
        return explicit
    if ttl_days is None:
        return None
    return datetime.now(UTC) + timedelta(days=ttl_days)


def _access_url(raw_token: str) -> str | None:
    if not settings.public_app_url:
        return None
    return f"{settings.public_app_url.rstrip('/')}/vendor?access_token={raw_token}"
