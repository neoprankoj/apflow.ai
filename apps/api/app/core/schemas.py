from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.events import WorkflowEventType


class ActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    VENDOR = "vendor"


class ResourceAction(StrEnum):
    READ = "read"
    WRITE = "write"
    APPROVE = "approve"
    EXPORT = "export"
    ADMIN = "admin"


class WorkflowStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_FOR_HUMAN = "waiting_for_human"


class ErrorCategory(StrEnum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    INTEGRATION = "integration"
    SECURITY = "security"
    UNKNOWN = "unknown"


class ErrorResolutionAction(StrEnum):
    RETRY = "retry"
    ESCALATE = "escalate"
    DEAD_LETTER = "dead_letter"
    IGNORE = "ignore"
    MANUAL_REVIEW = "manual_review"


class InvoiceSource(StrEnum):
    EMAIL = "email"
    UPLOAD = "upload"
    API = "api"
    SFTP = "sftp"
    EINVOICE_NETWORK = "einvoice_network"


class ExtractionReviewReason(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    UNSUPPORTED_MIME_TYPE = "unsupported_mime_type"
    MISSING_REQUIRED_FIELD = "missing_required_field"


class SupplierMatchStatus(StrEnum):
    MATCHED = "matched"
    POSSIBLE_MATCH = "possible_match"
    UNKNOWN_VENDOR = "unknown_vendor"


class InvoiceValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class DuplicateStatus(StrEnum):
    CLEAR = "clear"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    LIKELY_DUPLICATE = "likely_duplicate"


class POMatchStatus(StrEnum):
    MATCHED = "matched"
    PARTIAL_MATCH = "partial_match"
    AMOUNT_VARIANCE = "amount_variance"
    QUANTITY_VARIANCE = "quantity_variance"
    MISSING_PO = "missing_po"
    VENDOR_MISMATCH = "vendor_mismatch"
    NEEDS_REVIEW = "needs_review"


class POMatchRecommendedAction(StrEnum):
    AUTO_APPROVE = "auto_approve"
    ROUTE_EXCEPTION = "route_exception"
    REQUEST_REVIEW = "request_review"
    BLOCK = "block"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudRecommendedAction(StrEnum):
    CONTINUE = "continue"
    MANAGER_REVIEW = "manager_review"
    BLOCK_PAYMENT = "block_payment"


class ApprovalRoute(StrEnum):
    AUTO_APPROVE = "auto_approve"
    AP_REVIEW = "ap_review"
    MANAGER_APPROVAL = "manager_approval"
    CONTROLLER_APPROVAL = "controller_approval"
    BLOCKED = "blocked"


class ApprovalTaskStatus(StrEnum):
    AUTO_APPROVED = "auto_approved"
    PENDING = "pending"
    BLOCKED = "blocked"
    APPROVED = "approved"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"


class ApprovalDecisionAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    HOLD = "hold"


class NotificationType(StrEnum):
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DECISION_RECORDED = "approval_decision_recorded"
    INVOICE_BLOCKED = "invoice_blocked"
    DUPLICATE_DETECTED = "duplicate_detected"
    VALIDATION_FAILED = "validation_failed"
    VENDOR_MESSAGE_RECEIVED = "vendor_message_received"


class NotificationChannel(StrEnum):
    MOCK = "mock"
    EMAIL = "email"
    SLACK = "slack"
    TEAMS = "teams"
    WEBHOOK = "webhook"


class NotificationDeliveryStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    DISABLED = "disabled"


class NotificationRecipientType(StrEnum):
    INTERNAL_USER = "internal_user"
    VENDOR = "vendor"
    APPROVER = "approver"
    ADMIN = "admin"
    SYSTEM = "system"


class ERPAdapterType(StrEnum):
    PRIORITY = "priority"
    ODOO = "odoo"
    ZOHO_BOOKS = "zoho_books"


class ERPOperation(StrEnum):
    TEST_CONNECTION = "test_connection"
    SYNC_VENDORS = "sync_vendors"
    SYNC_PURCHASE_ORDERS = "sync_purchase_orders"
    EXPORT_INVOICE = "export_invoice"
    UPDATE_INVOICE_STATUS = "update_invoice_status"
    SYNC_PAYMENT_STATUS = "sync_payment_status"


class ERPSyncStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class OCRProviderName(StrEnum):
    MOCK = "mock"
    AZURE = "azure"
    GOOGLE = "google"
    AWS = "aws"
    OCR_SPACE = "ocr_space"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HumanReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    REVIEW_REQUIRED = "review_required"
    IN_REVIEW = "in_review"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class VendorSafeStatus(StrEnum):
    RECEIVED = "received"
    UNDER_REVIEW = "under_review"
    NEEDS_INFORMATION = "needs_information"
    APPROVED = "approved"
    SCHEDULED_FOR_PAYMENT = "scheduled_for_payment"
    PAID = "paid"
    REJECTED = "rejected"


class VendorChatIntent(StrEnum):
    INVOICE_RECEIVED = "invoice_received"
    APPROVAL_STATUS = "approval_status"
    PAYMENT_STATUS = "payment_status"
    INVOICE_PAYMENT_STATUS = "invoice_payment_status"
    INVOICE_DUE_OR_SCHEDULED_DATE = "invoice_due_or_scheduled_date"
    INVOICE_PAID_STATUS = "invoice_paid_status"
    LIST_PENDING_INVOICES = "list_pending_invoices"
    LIST_PAID_INVOICES = "list_paid_invoices"
    LIST_DISPUTED_INVOICES = "list_disputed_invoices"
    LIST_ALL_VISIBLE_INVOICES = "list_all_visible_invoices"
    HELP = "help"
    REJECTION_REASON_PUBLIC = "rejection_reason_public"
    MISSING_INFORMATION = "missing_information"
    UNSUPPORTED_OR_UNSAFE = "unsupported_or_unsafe"
    UNKNOWN = "unknown"


class PaymentStatusValue(StrEnum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    FAILED = "failed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class PaymentStatusSource(StrEnum):
    MANUAL = "manual"
    MOCK = "mock"
    ERP = "erp"
    IMPORTED = "imported"
    SYSTEM = "system"


class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    CONTROLLER = "controller"
    AP_MANAGER = "ap_manager"
    APPROVER = "approver"
    VIEWER = "viewer"


class Permission(StrEnum):
    INVOICE_READ = "invoice:read"
    INVOICE_PROCESS = "invoice:process"
    INVOICE_APPROVE = "invoice:approve"
    INVOICE_EXPORT_ERP = "invoice:export_erp"
    REVIEW_READ = "review:read"
    REVIEW_CORRECT = "review:correct"
    ERP_READ = "erp:read"
    ERP_CONFIGURE = "erp:configure"
    ERP_SYNC = "erp:sync"
    AUDIT_READ = "audit:read"
    NOTIFICATION_READ = "notification:read"
    TENANT_ADMIN = "tenant:admin"


class APFlowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ProductReadinessCheck(APFlowModel):
    key: str
    label: str
    status: str
    category: str
    message: str
    next_step: str | None = None
    safe_detail: str | None = None


class ProductReadinessLevel(APFlowModel):
    key: str
    status: str
    summary: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProductReadinessResponse(APFlowModel):
    environment: str
    generated_at: datetime
    demo_ready: ProductReadinessLevel
    pilot_ready: ProductReadinessLevel
    production_ready: ProductReadinessLevel
    checks: list[ProductReadinessCheck]
    message: str


class AnalyticsMetric(APFlowModel):
    key: str
    label: str
    value: float | int
    unit: str | None = None
    trend: str | None = None
    status: str = "neutral"
    description: str | None = None


class AnalyticsBreakdownItem(APFlowModel):
    key: str
    label: str
    count: int
    percentage: float | None = None


class AnalyticsExceptionItem(APFlowModel):
    key: str
    label: str
    count: int
    severity: str = "medium"
    next_step: str | None = None


class AccuracyAnalyticsResponse(APFlowModel):
    tenant_id: UUID
    generated_at: datetime
    date_range: dict[str, str | None] = Field(default_factory=dict)
    invoice_volume: list[AnalyticsMetric] = Field(default_factory=list)
    ocr_accuracy: list[AnalyticsMetric] = Field(default_factory=list)
    review_workload: list[AnalyticsMetric] = Field(default_factory=list)
    approval_health: list[AnalyticsMetric] = Field(default_factory=list)
    exception_breakdown: list[AnalyticsExceptionItem] = Field(default_factory=list)
    erp_export_health: list[AnalyticsMetric] = Field(default_factory=list)
    payment_status_health: list[AnalyticsBreakdownItem] = Field(default_factory=list)
    vendor_self_service: list[AnalyticsMetric] = Field(default_factory=list)
    notification_health: list[AnalyticsMetric] = Field(default_factory=list)
    top_blockers: list[AnalyticsExceptionItem] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AgentContext(APFlowModel):
    tenant_id: UUID | None = None
    actor_id: str = "system"
    actor_type: ActorType = ActorType.SYSTEM
    correlation_id: UUID = Field(default_factory=uuid4)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SecurityDecisionInput(APFlowModel):
    tenant_id: UUID
    actor_id: str
    actor_type: ActorType
    resource: str
    action: ResourceAction
    context: dict[str, Any] = Field(default_factory=dict)


class SecurityDecisionOutput(APFlowModel):
    allowed: bool
    reason: str
    policy_id: str


class AuditEventInput(APFlowModel):
    tenant_id: UUID
    actor_type: ActorType
    actor_id: str
    action: str
    entity_type: str
    entity_id: UUID
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)


class AuditEventOutput(APFlowModel):
    audit_event_id: UUID = Field(default_factory=uuid4)
    status: str = "recorded"


class StoredAuditEvent(AuditEventInput):
    audit_event_id: UUID = Field(default_factory=uuid4)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetricEventInput(APFlowModel):
    tenant_id: UUID | None = None
    metric_event: str
    value: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricEventOutput(APFlowModel):
    metric_id: UUID = Field(default_factory=uuid4)
    status: str
    alerts: list[str] = Field(default_factory=list)


class StoredMetricEvent(MetricEventInput):
    metric_id: UUID = Field(default_factory=uuid4)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    alerts: list[str] = Field(default_factory=list)


class WorkflowErrorInput(APFlowModel):
    tenant_id: UUID
    workflow_id: UUID
    agent_name: str
    error_type: ErrorCategory
    error_message: str
    retry_count: int = Field(ge=0)
    context: dict[str, Any] = Field(default_factory=dict)


class ErrorResolutionOutput(APFlowModel):
    resolution: ErrorResolutionAction
    next_attempt_at: datetime | None = None
    notification_required: bool


class WorkflowEventInput(APFlowModel):
    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    workflow_id: UUID
    event_type: WorkflowEventType
    entity_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)


class OrchestratorOutput(APFlowModel):
    workflow_id: UUID
    next_agent: str
    state: str
    status: WorkflowStatus
    context: dict[str, Any] = Field(default_factory=dict)


class WorkflowState(APFlowModel):
    workflow_id: UUID
    tenant_id: UUID
    state: str
    status: str
    current_agent: str | None = None
    retry_count: int = 0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InvoiceIngestionMetadata(APFlowModel):
    sender_email: str | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    original_filename: str
    mime_type: str = "application/pdf"


class InvoiceIngestionInput(APFlowModel):
    tenant_id: UUID
    source: InvoiceSource
    file_url: str
    metadata: InvoiceIngestionMetadata
    content: str | bytes | None = None
    correlation_id: UUID = Field(default_factory=uuid4)


class InvoiceIngestionOutput(APFlowModel):
    raw_invoice_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    storage_url: str
    mime_type: str
    source: InvoiceSource
    file_checksum: str
    status: str = "stored"
    original_file_name: str | None = None


class DocumentReference(APFlowModel):
    document_id: UUID
    tenant_id: UUID
    storage_provider: str
    storage_key: str
    content_type: str


class UploadedInvoiceDocument(APFlowModel):
    document_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    original_file_name: str
    content_type: str
    size_bytes: int
    storage_provider: str
    storage_key: str
    uploaded_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InvoiceUploadResult(APFlowModel):
    document: UploadedInvoiceDocument
    document_reference: DocumentReference


class InvoiceProcessFromUploadRequest(APFlowModel):
    tenant_id: UUID
    correlation_id: UUID = Field(default_factory=uuid4)


class InvoiceProcessFromUploadResult(APFlowModel):
    document: UploadedInvoiceDocument
    extraction_result: "InvoiceExtractionOutput | None" = None
    pipeline_result: dict[str, Any] | None = None
    review_status: HumanReviewStatus | None = None
    workflow_status: str
    corrected_fields_applied: bool = False
    corrected_field_count: int = 0
    unresolved_review_fields: list[str] = Field(default_factory=list)
    invoice_created: bool = False
    blocker_reason: str | None = None


class InvoiceLineItem(APFlowModel):
    description: str
    quantity: float = 1
    unit_price: float = 0
    tax_amount: float = 0
    total: float = 0
    po_number: str | None = None


class ExtractedInvoiceFields(APFlowModel):
    invoice_number: str | None = None
    supplier_name: str | None = None
    supplier_tax_id: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax_total: float | None = None
    shipping_amount: float | None = None
    fee_total: float | None = None
    discount_total: float | None = None
    grand_total: float | None = None
    po_number: str | None = None


class InvoiceExtractionInput(APFlowModel):
    raw_invoice_id: UUID
    tenant_id: UUID
    storage_url: str
    mime_type: str
    correlation_id: UUID = Field(default_factory=uuid4)


class InvoiceExtractionOutput(APFlowModel):
    extraction_id: UUID = Field(default_factory=uuid4)
    raw_invoice_id: UUID
    tenant_id: UUID
    fields: ExtractedInvoiceFields
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    needs_review: bool
    review_reasons: list[ExtractionReviewReason] = Field(default_factory=list)
    ocr_result: "OCRExtractionResult | None" = None
    confidence_summary: "OCRConfidenceSummary | None" = None


class InvoiceNormalizationInput(APFlowModel):
    extraction_id: UUID
    raw_invoice_id: UUID
    tenant_id: UUID
    fields: ExtractedInvoiceFields
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    file_checksum: str | None = None
    correlation_id: UUID = Field(default_factory=uuid4)


class CanonicalInvoice(APFlowModel):
    invoice_number: str
    supplier_name: str
    supplier_tax_id: str | None = None
    invoice_date: str
    due_date: str | None = None
    currency: str = "USD"
    subtotal: float
    tax_total: float
    shipping_amount: float = 0
    fee_total: float = 0
    discount_total: float = 0
    grand_total: float
    total_components_complete: bool = True
    po_number: str | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)


class InvoiceNormalizationOutput(APFlowModel):
    invoice_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    canonical_invoice: CanonicalInvoice
    normalization_warnings: list[str] = Field(default_factory=list)
    file_checksum: str | None = None


class SupplierIdentityInput(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID
    supplier_name: str
    supplier_tax_id: str | None = None
    bank_account_hash: str | None = None
    correlation_id: UUID = Field(default_factory=uuid4)


class SupplierIdentityOutput(APFlowModel):
    invoice_id: UUID
    vendor_id: UUID | None = None
    match_confidence: float
    status: SupplierMatchStatus
    evidence: list[str] = Field(default_factory=list)


class InvoiceValidationInput(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID
    canonical_invoice: CanonicalInvoice
    vendor_id: UUID | None = None
    correlation_id: UUID = Field(default_factory=uuid4)


class InvoiceValidationOutput(APFlowModel):
    invoice_id: UUID
    validation_status: InvoiceValidationStatus
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DuplicateDetectionInput(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID
    vendor_id: UUID | None = None
    invoice_number: str
    invoice_date: str
    grand_total: float
    file_checksum: str | None = None
    correlation_id: UUID = Field(default_factory=uuid4)


class DuplicateEvidence(APFlowModel):
    invoice_id: UUID
    reason: str
    score: float


class DuplicateDetectionOutput(APFlowModel):
    invoice_id: UUID
    duplicate_score: float
    possible_duplicates: list[DuplicateEvidence] = Field(default_factory=list)
    status: DuplicateStatus


class PurchaseOrderLine(APFlowModel):
    description: str
    quantity: float
    unit_price: float
    total: float


class PurchaseOrderInput(APFlowModel):
    tenant_id: UUID
    po_number: str
    vendor_id: UUID
    currency: str = "USD"
    total_amount: float
    lines: list[PurchaseOrderLine] = Field(default_factory=list)
    status: str = "open"


class PurchaseOrderOutput(PurchaseOrderInput):
    purchase_order_id: UUID = Field(default_factory=uuid4)


class PaymentStatusRead(APFlowModel):
    id: UUID
    tenant_id: UUID
    invoice_id: UUID
    status: PaymentStatusValue
    source: PaymentStatusSource
    amount_due: float | None = None
    amount_paid: float | None = None
    currency: str = "USD"
    scheduled_payment_date: datetime | None = None
    paid_at: datetime | None = None
    external_payment_reference: str | None = None
    safe_vendor_message: str | None = None
    internal_note: str | None = None
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by_user_id: UUID | None = None


class PaymentStatusUpdate(APFlowModel):
    status: PaymentStatusValue | None = None
    amount_paid: float | None = None
    scheduled_payment_date: datetime | None = None
    paid_at: datetime | None = None
    safe_vendor_message: str | None = None
    internal_note: str | None = None
    external_payment_reference: str | None = None


class PaymentStatusSyncRequest(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID | None = None
    mode: str = "mock"
    status: PaymentStatusValue | None = None


class PaymentStatusSummary(APFlowModel):
    tenant_id: UUID
    totals_by_status: dict[str, int] = Field(default_factory=dict)
    pending_count: int = 0
    scheduled_count: int = 0
    paid_count: int = 0
    failed_or_disputed_count: int = 0
    latest_updates: list[PaymentStatusRead] = Field(default_factory=list)


class VendorSafePaymentStatus(APFlowModel):
    invoice_id: UUID
    invoice_number: str
    status: PaymentStatusValue
    safe_status_label: str
    safe_message: str
    amount_due: float | None = None
    amount_paid: float | None = None
    currency: str = "USD"
    scheduled_payment_date: datetime | None = None
    paid_at: datetime | None = None


class PurchaseOrderMatchingInput(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID
    vendor_id: UUID | None = None
    po_number: str | None = None
    invoice_lines: list[InvoiceLineItem] = Field(default_factory=list)
    invoice_total: float
    currency: str = "USD"
    correlation_id: UUID = Field(default_factory=uuid4)


class VarianceDetail(APFlowModel):
    field: str
    expected: str | float | None
    actual: str | float | None
    message: str


class PurchaseOrderMatchingOutput(APFlowModel):
    invoice_id: UUID
    match_status: POMatchStatus
    variance_details: list[VarianceDetail] = Field(default_factory=list)
    recommended_action: POMatchRecommendedAction
    matched_po_id: UUID | None = None
    is_three_way_ready: bool = False


class FraudRiskScoringInput(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID
    vendor_id: UUID | None = None
    invoice_total: float
    duplicate_result: DuplicateDetectionOutput
    supplier_result: SupplierIdentityOutput
    po_match_result: PurchaseOrderMatchingOutput
    validation_result: InvoiceValidationOutput
    correlation_id: UUID = Field(default_factory=uuid4)


class FraudRiskScoringOutput(APFlowModel):
    invoice_id: UUID
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)
    recommended_action: FraudRecommendedAction


class ApprovalPolicy(APFlowModel):
    tenant_id: UUID
    auto_approve_limit: float = 500
    manager_approval_limit: float = 10000
    controller_approval_limit: float = 50000
    high_risk_blocks: bool = True


class ApprovalRoutingInput(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID
    amount: float
    department: str | None = None
    cost_center: str | None = None
    match_status: POMatchStatus
    risk_level: RiskLevel
    validation_status: InvoiceValidationStatus
    duplicate_status: DuplicateStatus
    correlation_id: UUID = Field(default_factory=uuid4)


class ApprovalRoutingOutput(APFlowModel):
    invoice_id: UUID
    approval_task_id: UUID
    route: ApprovalRoute
    assigned_role: str
    approval_status: ApprovalTaskStatus
    reason: str


class ApprovalDecisionRequest(APFlowModel):
    tenant_id: UUID
    action: ApprovalDecisionAction
    reason: str | None = None
    correlation_id: UUID = Field(default_factory=uuid4)


class ApprovalDecisionResult(APFlowModel):
    invoice_id: UUID
    approval_task_id: UUID
    action: ApprovalDecisionAction
    route: ApprovalRoute
    approval_status: ApprovalTaskStatus
    reason: str
    workflow_status: str
    erp_export_ready: bool
    blocker_reason: str | None = None


class NotificationInput(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID
    notification_type: NotificationType
    recipient_role: str
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)


class NotificationOutput(APFlowModel):
    notification_id: UUID = Field(default_factory=uuid4)
    invoice_id: UUID
    status: str = "sent"
    channel: str = "mock"
    notification_type: NotificationType
    recipient_role: str


class NotificationProviderRead(APFlowModel):
    provider: str
    channel: NotificationChannel
    configured: bool
    enabled: bool
    mode: str
    safe_message: str


class NotificationTestRequest(APFlowModel):
    tenant_id: UUID
    channel: NotificationChannel = NotificationChannel.MOCK
    recipient_label: str | None = None
    recipient_address: str | None = None
    subject: str | None = None
    message: str | None = None


class NotificationDeliveryRead(APFlowModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    event_type: str
    channel: NotificationChannel
    provider: str
    recipient_type: NotificationRecipientType
    recipient_label: str
    recipient_address_redacted: str | None = None
    subject: str | None = None
    body_preview: str | None = None
    status: NotificationDeliveryStatus
    reason: str | None = None
    related_invoice_id: UUID | None = None
    related_payment_status_id: UUID | None = None
    related_vendor_access_id: UUID | None = None
    delivery_metadata: dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    delivered_at: datetime | None = None


class NotificationSummary(APFlowModel):
    total: int = 0
    sent: int = 0
    queued: int = 0
    failed: int = 0
    skipped: int = 0
    disabled: int = 0
    by_channel: dict[str, int] = Field(default_factory=dict)
    latest_deliveries: list[NotificationDeliveryRead] = Field(default_factory=list)


class OCRProviderMetadata(APFlowModel):
    provider_name: OCRProviderName
    configured: bool
    model_version: str | None = None
    raw_provider_status: str | None = None
    is_errored_on_processing: bool | None = None
    ocr_exit_code: int | str | None = None
    parsed_result_count: int | None = None
    parsed_text_length: int | None = None
    detected_content_type: str | None = None
    sent_file_name: str | None = None
    sent_filetype: str | None = None
    sent_content_type: str | None = None
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    engine_used: str | None = None
    fallback_engine: str | None = None
    fallback_used: bool | None = None
    primary_provider_error_code: str | None = None
    primary_provider_error_message: str | None = None


class OCRExtractedField(APFlowModel):
    field_name: str
    value: str | float | int | None = None
    confidence: float = Field(ge=0, le=1)
    source_page: int | None = None
    bounding_box: list[float] | None = None
    raw_text: str | None = None
    requires_review: bool = False


class OCRExtractedLineItem(APFlowModel):
    fields: list[OCRExtractedField] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    requires_review: bool = False


class OCRConfidenceSummary(APFlowModel):
    average_confidence: float = Field(ge=0, le=1)
    high_confidence_fields: int = 0
    medium_confidence_fields: int = 0
    low_confidence_fields: int = 0
    required_fields_missing: list[str] = Field(default_factory=list)
    required_fields_low_confidence: list[str] = Field(default_factory=list)


class OCRExtractionResult(APFlowModel):
    extraction_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    provider_metadata: OCRProviderMetadata
    fields: list[OCRExtractedField] = Field(default_factory=list)
    line_items: list[OCRExtractedLineItem] = Field(default_factory=list)
    confidence_summary: OCRConfidenceSummary
    raw_response: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class HumanReviewFieldIssue(APFlowModel):
    field_name: str
    issue_type: str
    message: str
    current_value: str | float | int | None = None
    confidence: float | None = None


class HumanReviewTask(APFlowModel):
    task_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    invoice_id: UUID | None = None
    raw_invoice_id: UUID | None = None
    extraction_id: UUID | None = None
    status: HumanReviewStatus
    issues: list[HumanReviewFieldIssue] = Field(default_factory=list)
    corrected_fields: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HumanReviewCorrectionRequest(APFlowModel):
    tenant_id: UUID
    corrections: dict[str, Any]
    reviewer_id: str = "demo-reviewer"


class HumanReviewCorrectionResult(APFlowModel):
    task_id: UUID
    status: HumanReviewStatus
    corrected_fields: dict[str, Any]


class ERPConnectionConfig(APFlowModel):
    tenant_id: UUID
    adapter_type: ERPAdapterType = ERPAdapterType.PRIORITY
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class PriorityEntityMapping(APFlowModel):
    entity_name: str
    external_id_field: str
    fields: dict[str, str] = Field(default_factory=dict)
    line_items_entity_name: str | None = None
    line_item_fields: dict[str, str] | None = None
    enabled: bool = True


class PriorityMappingConfig(APFlowModel):
    vendors: PriorityEntityMapping | None = None
    purchase_orders: PriorityEntityMapping | None = None
    invoice_export: PriorityEntityMapping | None = None
    version: str = "1.0"
    updated_at: datetime | None = None


class PriorityMappingValidationRequest(APFlowModel):
    tenant_id: UUID
    mapping: PriorityMappingConfig


class PriorityMappingValidationResult(APFlowModel):
    status: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class PriorityReadinessCheck(APFlowModel):
    key: str
    label: str
    status: str
    message: str
    safe_detail: str | None = None


class PriorityReadinessResponse(APFlowModel):
    status: str
    mode: str
    read_only_fetch_enabled: bool
    writes_enabled: bool
    base_url_configured: bool
    company_configured: bool
    environment_configured: bool
    auth_configured: bool
    service_root_checked: bool = False
    metadata_checked: bool = False
    service_root_available: bool | None = None
    metadata_available: bool | None = None
    checks: list[PriorityReadinessCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str


class PrioritySyncPreviewRequest(APFlowModel):
    tenant_id: UUID
    kind: str = "vendors"
    source: str = "sample"
    limit: int = Field(default=10, ge=1, le=50)
    sample_records: list[dict[str, Any]] | None = None


class PrioritySyncPreviewResponse(APFlowModel):
    status: str
    kind: str
    mode: str
    source: str
    mapping_status: str
    records_previewed: int = 0
    raw_records: list[dict[str, Any]] = Field(default_factory=list)
    mapped_records: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str


class PriorityImportPlanRequest(APFlowModel):
    tenant_id: UUID
    kind: str = "vendors"
    source: str = "sample"
    limit: int = Field(default=10, ge=1, le=50)
    sample_records: list[dict[str, Any]] | None = None


class PriorityImportPlanItem(APFlowModel):
    action: str
    reason: str
    mapped_record: dict[str, Any]
    matched_existing_id: str | None = None
    diff: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class PriorityImportPlanResponse(APFlowModel):
    status: str
    kind: str
    mode: str
    source: str
    records_planned: int = 0
    summary: dict[str, int] = Field(default_factory=dict)
    items: list[PriorityImportPlanItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str


class PriorityImportRequest(APFlowModel):
    tenant_id: UUID
    kind: str = "vendors"
    source: str = "sample"
    selected_external_ids: list[str] = Field(default_factory=list)
    confirmation: str
    allow_updates: bool = False
    allow_creates: bool = True
    limit: int = Field(default=10, ge=1, le=50)


class PriorityImportResultItem(APFlowModel):
    external_id: str | None = None
    action_requested: str
    result: str
    apflow_record_id: str | None = None
    reason: str
    warnings: list[str] = Field(default_factory=list)


class PriorityImportResult(APFlowModel):
    status: str
    kind: str
    summary: dict[str, int] = Field(default_factory=dict)
    items: list[PriorityImportResultItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str


class PriorityImportedVendorRecord(APFlowModel):
    apflow_vendor_id: UUID
    external_id: str | None = None
    name: str
    tax_id: str | None = None
    email: str | None = None
    payment_terms: str | None = None
    source_adapter: str = "priority"
    imported_from_priority: bool = False
    last_imported_at: datetime | None = None
    last_import_action: str | None = None
    external_reference_id: UUID | None = None


class PriorityImportedPurchaseOrderRecord(APFlowModel):
    apflow_purchase_order_id: UUID
    po_number: str
    external_id: str | None = None
    vendor_id: UUID | None = None
    vendor_external_id: str | None = None
    status: str
    total_amount: float
    currency: str
    source_adapter: str = "priority"
    imported_from_priority: bool = False
    last_imported_at: datetime | None = None
    last_import_action: str | None = None
    external_reference_id: UUID | None = None


class PriorityImportedRecordsResponse(APFlowModel):
    tenant_id: UUID
    kind: str
    records: list[PriorityImportedVendorRecord | PriorityImportedPurchaseOrderRecord] = Field(default_factory=list)


class ERPSyncRequest(APFlowModel):
    tenant_id: UUID
    operation: ERPOperation = ERPOperation.TEST_CONNECTION
    adapter_type: ERPAdapterType | None = None
    invoice_id: UUID | None = None
    status: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)


class ERPVendorRecord(APFlowModel):
    tenant_id: UUID
    external_vendor_id: str
    name: str
    tax_id: str | None = None
    bank_account_hash: str | None = None
    email: str | None = None
    payment_terms: str | None = None


class ERPPurchaseOrderRecord(APFlowModel):
    tenant_id: UUID
    external_po_id: str
    po_number: str
    external_vendor_id: str
    vendor_name: str
    vendor_tax_id: str | None = None
    currency: str = "USD"
    total_amount: float
    lines: list[PurchaseOrderLine] = Field(default_factory=list)


class ERPInvoiceExportResult(APFlowModel):
    invoice_id: UUID
    external_invoice_id: str
    exported: bool


class ERPPaymentStatusResult(APFlowModel):
    invoice_id: UUID
    external_invoice_id: str | None = None
    payment_status: str
    paid_at: str | None = None


class ERPSyncLog(APFlowModel):
    sync_log_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    adapter_type: ERPAdapterType
    operation: ERPOperation
    status: ERPSyncStatus
    records_processed: int = 0
    external_id: str | None = None
    invoice_id: UUID | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ERPSyncResult(APFlowModel):
    sync_id: UUID = Field(default_factory=uuid4)
    adapter_type: ERPAdapterType
    operation: ERPOperation
    status: ERPSyncStatus
    records_processed: int = 0
    external_id: str | None = None
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class TenantRecordSchema(APFlowModel):
    id: UUID
    name: str
    slug: str
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserRecordSchema(APFlowModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TenantMembershipSchema(APFlowModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    role: UserRole
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RegisterDemoTenantRequest(APFlowModel):
    tenant_name: str = "Demo Tenant"
    tenant_slug: str = "demo"
    email: str = "owner@example.com"
    full_name: str = "Demo Owner"
    password: str = Field(min_length=8)


class LoginRequest(APFlowModel):
    email: str
    password: str
    tenant_id: UUID | None = None


class TokenResponse(APFlowModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserRecordSchema
    tenant: TenantRecordSchema
    role: UserRole
    permissions: list[Permission]


class CurrentUserContext(APFlowModel):
    user: UserRecordSchema
    tenant: TenantRecordSchema
    membership: TenantMembershipSchema
    permissions: list[Permission]
    auth_enabled: bool = True
    demo_mode: bool = False


class CreateTenantUserRequest(APFlowModel):
    email: str
    full_name: str
    password: str = Field(min_length=8)
    role: UserRole = UserRole.VIEWER


class UpdateUserRoleRequest(APFlowModel):
    role: UserRole


class AdminUserRecord(APFlowModel):
    user: UserRecordSchema
    role: UserRole
    is_active: bool


class VendorPortalAccessCreate(APFlowModel):
    tenant_id: UUID
    email: str
    vendor_id: UUID | None = None
    vendor_name: str | None = None
    expires_at: datetime | None = None
    ttl_days: int | None = Field(default=None, ge=1, le=365)
    label: str | None = None


class VendorPortalAccessResult(APFlowModel):
    access_id: UUID
    tenant_id: UUID
    vendor_id: UUID
    email: str
    status: str
    access_token: str | None = None
    token_prefix: str | None = None
    label: str | None = None
    access_url: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VendorAccessCreateRequest(APFlowModel):
    tenant_id: UUID
    email: str
    vendor_id: UUID | None = None
    vendor_name: str | None = None
    supplier_name: str | None = None
    label: str | None = None
    expires_at: datetime | None = None
    ttl_days: int | None = Field(default=30, ge=1, le=365)


class VendorAccessRead(APFlowModel):
    id: UUID
    tenant_id: UUID
    vendor_id: UUID
    vendor_name: str | None = None
    matching_invoice_count: int = 0
    email: str
    label: str | None = None
    status: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    rotated_from_access_id: UUID | None = None
    last_used_at: datetime | None = None
    token_prefix: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class VendorAccessCreatedResponse(VendorAccessRead):
    access_token: str
    access_url: str | None = None
    message: str = "Copy this token now. It will not be shown again."


class VendorAccessRotateResponse(APFlowModel):
    old_access: VendorAccessRead
    new_access: VendorAccessRead
    access_token: str
    access_url: str | None = None
    message: str = "Copy this replacement token now. It will not be shown again."


class VendorAccessRevokeResponse(APFlowModel):
    id: UUID
    status: str
    revoked_at: datetime | None = None
    message: str


class VendorAccessValidationResult(APFlowModel):
    valid: bool
    status: str
    reason: str | None = None
    tenant_id: UUID | None = None
    vendor_id: UUID | None = None
    vendor_name: str | None = None


class VendorInvoiceListItem(APFlowModel):
    invoice_id: UUID
    invoice_number: str
    supplier_name: str
    invoice_date: str
    currency: str
    grand_total: float
    status: VendorSafeStatus
    payment_status: str | None = None


class VendorInvoiceStatus(VendorInvoiceListItem):
    due_date: str | None = None
    public_message: str
    missing_information: list[str] = Field(default_factory=list)
    line_item_count: int = 0
    payment_status_detail: VendorSafePaymentStatus | None = None


class VendorMessageCreate(APFlowModel):
    tenant_id: UUID
    invoice_id: UUID | None = None
    sender_email: str
    message: str = Field(min_length=1, max_length=4000)


class VendorMessageResult(APFlowModel):
    message_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    vendor_id: UUID
    invoice_id: UUID | None = None
    sender_email: str
    message: str
    status: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VendorChatRequest(APFlowModel):
    tenant_id: UUID
    question: str = Field(min_length=1, max_length=1000)
    invoice_id: UUID | None = None
    invoice_number: str | None = None
    access_token: str | None = None
    sender_email: str | None = None


class VendorChatResponse(APFlowModel):
    session_id: UUID = Field(default_factory=uuid4)
    message_id: UUID = Field(default_factory=uuid4)
    intent: VendorChatIntent
    answer: str
    invoice_id: UUID | None = None
    status: VendorSafeStatus | None = None
    confidence: str = "medium"
    matched_invoice_ids: list[UUID] = Field(default_factory=list)
    matched_invoices: list[VendorInvoiceListItem] = Field(default_factory=list)
    safe_suggestions: list[str] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: str | None = None
    escalated: bool = False
