from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class TenantScopedMixin:
    tenant_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, default="demo", index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="US")
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class TenantMembership(Base, TimestampMixin):
    __tablename__ = "tenant_memberships"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)


class Vendor(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "vendors"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    bank_account_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    erp_vendor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Invoice(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    vendor_id: Mapped[PyUUID | None] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(255), index=True)
    invoice_date: Mapped[str] = mapped_column(String(32), nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="received")
    file_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    canonical_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    lines: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class InvoiceLineItem(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "invoice_line_items"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("invoices.id"), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    po_number: Mapped[str | None] = mapped_column(String(255), nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class PurchaseOrder(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    vendor_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=False)
    po_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="open")

    lines: Mapped[list["PurchaseOrderLineItem"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )


class PurchaseOrderLineItem(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "purchase_order_line_items"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    purchase_order_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("purchase_orders.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class GoodsReceipt(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "goods_receipts"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    purchase_order_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("purchase_orders.id"))
    receipt_number: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ApprovalPolicy(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "approval_policies"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    auto_approve_limit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=500)
    manager_approval_limit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=10000)
    controller_approval_limit: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=50000)
    high_risk_blocks: Mapped[bool] = mapped_column(default=True, nullable=False)


class ApprovalTask(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "approval_tasks"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("invoices.id"), index=True)
    route: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_role: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class ApprovalFlow(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "approval_flows"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("invoices.id"), index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending_approval")
    assigned_approvers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class NotificationEvent(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "notification_events"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("invoices.id"), index=True)
    notification_type: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Notification(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    recipient_type: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_id: Mapped[PyUUID] = mapped_column(Uuid, nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    template_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")


class NotificationDelivery(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "notification_deliveries"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_label: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_address_redacted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_invoice_id: Mapped[PyUUID | None] = mapped_column(Uuid, ForeignKey("invoices.id"), nullable=True, index=True)
    related_payment_status_id: Mapped[PyUUID | None] = mapped_column(
        Uuid,
        ForeignKey("payment_statuses.id"),
        nullable=True,
        index=True,
    )
    related_vendor_access_id: Mapped[PyUUID | None] = mapped_column(
        Uuid,
        ForeignKey("vendor_portal_access.id"),
        nullable=True,
        index=True,
    )
    delivery_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[PyUUID | None] = mapped_column(Uuid, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[PyUUID] = mapped_column(Uuid, index=True, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[PyUUID] = mapped_column(Uuid, nullable=False, index=True)
    correlation_id: Mapped[PyUUID] = mapped_column(Uuid, nullable=False, default=uuid4)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


class WorkflowState(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflow_states"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[PyUUID] = mapped_column(Uuid, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    current_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class WorkflowEvent(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflow_events"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[PyUUID] = mapped_column(Uuid, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[PyUUID] = mapped_column(Uuid, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IntegrationCredential(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "integration_credentials"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")


class ERPConnectionConfig(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "erp_connection_configs"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    adapter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ERPSyncLog(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "erp_sync_logs"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    adapter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    records_processed: Mapped[int] = mapped_column(default=0, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_id: Mapped[PyUUID | None] = mapped_column(Uuid, ForeignKey("invoices.id"), nullable=True)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class PaymentStatus(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "payment_statuses"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("invoices.id"), index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="not_started", index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    amount_due: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    scheduled_payment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    safe_vendor_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_user_id: Mapped[PyUUID | None] = mapped_column(Uuid, nullable=True)


class ERPExternalReference(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "erp_external_references"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[PyUUID] = mapped_column(Uuid, nullable=False, index=True)
    adapter_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)


class HumanReviewTask(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "human_review_tasks"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invoice_id: Mapped[PyUUID | None] = mapped_column(Uuid, ForeignKey("invoices.id"), nullable=True)
    raw_invoice_id: Mapped[PyUUID | None] = mapped_column(Uuid, nullable=True)
    extraction_id: Mapped[PyUUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    issues: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    corrected_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    history: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)


class UploadedInvoiceDocument(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "uploaded_invoice_documents"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    original_file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VendorPortalAccess(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "vendor_portal_access"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    vendor_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    access_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_prefix: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[PyUUID | None] = mapped_column(Uuid, nullable=True)
    created_by_user_id: Mapped[PyUUID | None] = mapped_column(Uuid, nullable=True)
    rotated_from_access_id: Mapped[PyUUID | None] = mapped_column(Uuid, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VendorMessage(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "vendor_messages"

    id: Mapped[PyUUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    vendor_id: Mapped[PyUUID] = mapped_column(Uuid, ForeignKey("vendors.id"), nullable=False, index=True)
    invoice_id: Mapped[PyUUID | None] = mapped_column(Uuid, ForeignKey("invoices.id"), nullable=True, index=True)
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="submitted")


InvoiceLine = InvoiceLineItem
WorkflowStateModel = WorkflowState
