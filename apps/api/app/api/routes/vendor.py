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
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    MetricEventInput,
    Permission,
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
    vendor_id = payload.vendor_id
    if vendor_id is None:
        vendors = repository.list_vendors(payload.tenant_id)
        if payload.vendor_name:
            vendor = repository.add_vendor(payload.tenant_id, payload.vendor_name)
        elif vendors:
            vendor = vendors[0]
        else:
            vendor = repository.add_vendor(payload.tenant_id, payload.email.split("@")[0])
        vendor_id = vendor.vendor_id
    elif not any(vendor.vendor_id == vendor_id for vendor in repository.list_vendors(payload.tenant_id)):
        raise HTTPException(status_code=404, detail="Vendor not found for tenant")

    raw_token = generate_vendor_access_token()
    record = repository.create_vendor_portal_access(
        tenant_id=payload.tenant_id,
        vendor_id=vendor_id,
        email=payload.email,
        access_token_hash=hash_vendor_access_token(raw_token),
        expires_at=payload.expires_at,
    )
    audit_agent.record(
        AuditEventInput(
            tenant_id=payload.tenant_id,
            actor_type=ActorType.USER,
            actor_id="vendor-access-demo",
            action="vendor.access_created",
            entity_type="vendor",
            entity_id=vendor_id,
            metadata={"email": payload.email, "access_id": str(record.access_id)},
        )
    )
    return VendorPortalAccessResult(
        access_id=record.access_id,
        tenant_id=record.tenant_id,
        vendor_id=record.vendor_id,
        email=record.email,
        status=record.status,
        access_token=raw_token,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


@router.get("/invoices", response_model=list[VendorInvoiceListItem])
def list_vendor_invoices(
    tenant_id: UUID,
    x_vendor_access_token: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
) -> list[VendorInvoiceListItem]:
    access = _resolve_vendor_access(tenant_id, x_vendor_access_token or access_token, repository)
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
) -> VendorInvoiceStatus:
    access = _resolve_vendor_access(tenant_id, x_vendor_access_token or access_token, repository)
    try:
        invoice = repository.get_invoice(tenant_id, invoice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Invoice not found") from exc
    if not invoice_is_visible_to_vendor(invoice, access.vendor_id):
        raise HTTPException(status_code=403, detail="Invoice is outside vendor scope")
    return vendor_invoice_status(repository, tenant_id, invoice)


@router.post("/messages", response_model=VendorMessageResult)
def submit_vendor_message(
    payload: VendorMessageCreate,
    x_vendor_access_token: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
    communication_agent: VendorCommunicationAgent = Depends(get_vendor_communication_agent),
) -> VendorMessageResult:
    access = _resolve_vendor_access(payload.tenant_id, x_vendor_access_token or access_token, repository)
    return communication_agent.submit_message(payload, access.vendor_id)


@router.post("/chat", response_model=VendorChatResponse)
def vendor_chat(
    payload: VendorChatRequest,
    x_vendor_access_token: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    repository: InMemoryAPRepository = Depends(get_repository),
    chatbot_agent: PaymentStatusChatbotAgent = Depends(get_payment_status_chatbot_agent),
) -> VendorChatResponse:
    access = _resolve_vendor_access(payload.tenant_id, x_vendor_access_token or access_token, repository)
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
    return access
