from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.schemas import (
    ApprovalPolicy,
    ApprovalRoute,
    ApprovalTaskStatus,
    AuditEventInput,
    CanonicalInvoice,
    ERPAdapterType,
    ERPConnectionConfig,
    ERPOperation,
    ERPSyncLog,
    ERPSyncStatus,
    HumanReviewCorrectionRequest,
    HumanReviewStatus,
    HumanReviewTask,
    InvoiceExtractionOutput,
    InvoiceIngestionOutput,
    InvoiceNormalizationOutput,
    NotificationType,
    UploadedInvoiceDocument,
    TenantMembershipSchema,
    TenantRecordSchema,
    PurchaseOrderInput,
    PurchaseOrderLine,
    PurchaseOrderOutput,
    UserRecordSchema,
    UserRole,
    VendorMessageResult,
    WorkflowState,
)


@dataclass(frozen=True)
class VendorRecord:
    tenant_id: UUID
    vendor_id: UUID
    name: str
    tax_id: str | None = None
    bank_account_hash: str | None = None


@dataclass
class InvoiceRecord:
    tenant_id: UUID
    invoice_id: UUID
    canonical_invoice: CanonicalInvoice
    vendor_id: UUID | None = None
    file_checksum: str | None = None


@dataclass
class RawInvoiceRecord:
    output: InvoiceIngestionOutput
    content: str | bytes | None = None


@dataclass
class PurchaseOrderRecord:
    output: PurchaseOrderOutput


@dataclass
class ApprovalPolicyRecord:
    policy: ApprovalPolicy


@dataclass
class ApprovalTaskRecord:
    tenant_id: UUID
    approval_task_id: UUID
    invoice_id: UUID
    route: str
    assigned_role: str
    status: str
    reason: str


@dataclass
class NotificationEventRecord:
    tenant_id: UUID
    notification_id: UUID
    invoice_id: UUID
    notification_type: NotificationType
    recipient_role: str
    status: str
    channel: str
    payload: dict


@dataclass
class AuditEventRecord:
    tenant_id: UUID
    audit_event_id: UUID
    actor_type: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: UUID
    correlation_id: UUID
    metadata: dict


@dataclass
class ERPConnectionConfigRecord:
    config: ERPConnectionConfig


@dataclass
class VendorPortalAccessRecord:
    access_id: UUID
    tenant_id: UUID
    vendor_id: UUID
    email: str
    access_token_hash: str
    status: str
    created_at: datetime
    expires_at: datetime | None = None


@dataclass
class InMemoryAPRepository:
    raw_invoices: dict[UUID, RawInvoiceRecord] = field(default_factory=dict)
    extractions: dict[UUID, InvoiceExtractionOutput] = field(default_factory=dict)
    invoices: dict[UUID, InvoiceRecord] = field(default_factory=dict)
    vendors: dict[UUID, VendorRecord] = field(default_factory=dict)
    purchase_orders: dict[UUID, PurchaseOrderRecord] = field(default_factory=dict)
    approval_policies: dict[UUID, ApprovalPolicyRecord] = field(default_factory=dict)
    approval_tasks: dict[UUID, ApprovalTaskRecord] = field(default_factory=dict)
    notification_events: dict[UUID, NotificationEventRecord] = field(default_factory=dict)
    audit_events: dict[UUID, AuditEventRecord] = field(default_factory=dict)
    workflow_states: dict[UUID, WorkflowState] = field(default_factory=dict)
    erp_connection_configs: dict[UUID, ERPConnectionConfigRecord] = field(default_factory=dict)
    erp_sync_logs: dict[UUID, ERPSyncLog] = field(default_factory=dict)
    invoice_external_ids: dict[UUID, str] = field(default_factory=dict)
    vendor_external_ids: dict[UUID, str] = field(default_factory=dict)
    po_external_ids: dict[UUID, str] = field(default_factory=dict)
    review_tasks: dict[UUID, HumanReviewTask] = field(default_factory=dict)
    uploaded_documents: dict[UUID, UploadedInvoiceDocument] = field(default_factory=dict)
    tenants: dict[UUID, TenantRecordSchema] = field(default_factory=dict)
    users: dict[UUID, UserRecordSchema] = field(default_factory=dict)
    user_passwords: dict[UUID, str] = field(default_factory=dict)
    memberships: dict[UUID, TenantMembershipSchema] = field(default_factory=dict)
    vendor_portal_access: dict[UUID, VendorPortalAccessRecord] = field(default_factory=dict)
    vendor_messages: dict[UUID, VendorMessageResult] = field(default_factory=dict)

    def create_tenant(
        self,
        name: str,
        slug: str,
        tenant_id: UUID | None = None,
        status: str = "active",
    ) -> TenantRecordSchema:
        tenant = TenantRecordSchema(
            id=tenant_id or uuid4(),
            name=name,
            slug=slug,
            status=status,
            created_at=datetime.now(UTC),
        )
        self.tenants[tenant.id] = tenant
        return tenant

    def get_tenant(self, tenant_id: UUID) -> TenantRecordSchema | None:
        return self.tenants.get(tenant_id)

    def create_user(
        self,
        email: str,
        full_name: str,
        hashed_password: str,
        is_active: bool = True,
        user_id: UUID | None = None,
    ) -> UserRecordSchema:
        existing = self.get_user_by_email(email)
        if existing is not None:
            self.user_passwords[existing.id] = hashed_password
            return existing
        user = UserRecordSchema(
            id=user_id or uuid4(),
            email=email.lower(),
            full_name=full_name,
            is_active=is_active,
            created_at=datetime.now(UTC),
        )
        self.users[user.id] = user
        self.user_passwords[user.id] = hashed_password
        return user

    def get_user(self, user_id: UUID) -> UserRecordSchema | None:
        return self.users.get(user_id)

    def get_user_by_email(self, email: str) -> UserRecordSchema | None:
        normalized = email.lower()
        return next((user for user in self.users.values() if user.email == normalized), None)

    def get_user_password_hash(self, user_id: UUID) -> str | None:
        return self.user_passwords.get(user_id)

    def create_membership(
        self,
        tenant_id: UUID,
        user_id: UUID,
        role: UserRole,
        membership_id: UUID | None = None,
    ) -> TenantMembershipSchema:
        existing = self.get_membership(tenant_id, user_id)
        if existing is not None:
            return existing
        membership = TenantMembershipSchema(
            id=membership_id or uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            created_at=datetime.now(UTC),
        )
        self.memberships[membership.id] = membership
        return membership

    def get_membership(self, tenant_id: UUID, user_id: UUID) -> TenantMembershipSchema | None:
        return next(
            (
                membership
                for membership in self.memberships.values()
                if membership.tenant_id == tenant_id and membership.user_id == user_id
            ),
            None,
        )

    def list_memberships_for_user(self, user_id: UUID) -> list[TenantMembershipSchema]:
        return [membership for membership in self.memberships.values() if membership.user_id == user_id]

    def list_memberships_for_tenant(self, tenant_id: UUID) -> list[TenantMembershipSchema]:
        return [membership for membership in self.memberships.values() if membership.tenant_id == tenant_id]

    def list_users_for_tenant(self, tenant_id: UUID) -> list[tuple[UserRecordSchema, TenantMembershipSchema]]:
        records: list[tuple[UserRecordSchema, TenantMembershipSchema]] = []
        for membership in self.list_memberships_for_tenant(tenant_id):
            user = self.get_user(membership.user_id)
            if user is not None:
                records.append((user, membership))
        return records

    def update_membership_role(self, tenant_id: UUID, user_id: UUID, role: UserRole) -> TenantMembershipSchema:
        membership = self.get_membership(tenant_id, user_id)
        if membership is None:
            raise KeyError("user is not a member of tenant")
        updated = membership.model_copy(update={"role": role})
        self.memberships[membership.id] = updated
        return updated

    def deactivate_user(self, tenant_id: UUID, user_id: UUID) -> UserRecordSchema:
        if self.get_membership(tenant_id, user_id) is None:
            raise KeyError("user is not a member of tenant")
        user = self.users[user_id]
        updated = user.model_copy(update={"is_active": False})
        self.users[user_id] = updated
        return updated

    def create_vendor_portal_access(
        self,
        tenant_id: UUID,
        vendor_id: UUID,
        email: str,
        access_token_hash: str,
        status: str = "active",
        expires_at: datetime | None = None,
        access_id: UUID | None = None,
    ) -> VendorPortalAccessRecord:
        record = VendorPortalAccessRecord(
            access_id=access_id or uuid4(),
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            email=email.lower(),
            access_token_hash=access_token_hash,
            status=status,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
        )
        self.vendor_portal_access[record.access_id] = record
        return record

    def list_vendor_portal_access(self, tenant_id: UUID) -> list[VendorPortalAccessRecord]:
        return [record for record in self.vendor_portal_access.values() if record.tenant_id == tenant_id]

    def get_vendor_access_by_hash(
        self,
        tenant_id: UUID,
        access_token_hash: str,
    ) -> VendorPortalAccessRecord | None:
        now = datetime.now(UTC)
        for record in self.list_vendor_portal_access(tenant_id):
            if record.access_token_hash != access_token_hash or record.status != "active":
                continue
            if record.expires_at is not None and record.expires_at < now:
                continue
            return record
        return None

    def store_vendor_message(self, message: VendorMessageResult) -> VendorMessageResult:
        self.vendor_messages[message.message_id] = message
        return message

    def list_vendor_messages(
        self,
        tenant_id: UUID,
        vendor_id: UUID | None = None,
    ) -> list[VendorMessageResult]:
        return [
            message
            for message in self.vendor_messages.values()
            if message.tenant_id == tenant_id and (vendor_id is None or message.vendor_id == vendor_id)
        ]

    def store_uploaded_document(self, document: UploadedInvoiceDocument) -> UploadedInvoiceDocument:
        self.uploaded_documents[document.document_id] = document
        return document

    def get_uploaded_document(self, tenant_id: UUID, document_id: UUID) -> UploadedInvoiceDocument:
        document = self.uploaded_documents[document_id]
        if document.tenant_id != tenant_id:
            raise KeyError("document is outside tenant scope")
        return document

    def list_uploaded_documents(self, tenant_id: UUID) -> list[UploadedInvoiceDocument]:
        return [
            document
            for document in self.uploaded_documents.values()
            if document.tenant_id == tenant_id
        ]

    def store_raw_invoice(
        self,
        output: InvoiceIngestionOutput,
        content: str | bytes | None = None,
    ) -> None:
        self.raw_invoices[output.raw_invoice_id] = RawInvoiceRecord(output=output, content=content)

    def get_raw_invoice(self, tenant_id: UUID, raw_invoice_id: UUID) -> RawInvoiceRecord:
        record = self.raw_invoices[raw_invoice_id]
        if record.output.tenant_id != tenant_id:
            raise KeyError("raw invoice is outside tenant scope")
        return record

    def store_extraction(self, output: InvoiceExtractionOutput) -> None:
        self.extractions[output.extraction_id] = output

    def store_invoice(self, output: InvoiceNormalizationOutput) -> None:
        self.invoices[output.invoice_id] = InvoiceRecord(
            tenant_id=output.tenant_id,
            invoice_id=output.invoice_id,
            canonical_invoice=output.canonical_invoice,
            file_checksum=output.file_checksum,
        )

    def update_invoice_vendor(self, tenant_id: UUID, invoice_id: UUID, vendor_id: UUID | None) -> None:
        record = self.invoices[invoice_id]
        if record.tenant_id != tenant_id:
            raise KeyError("invoice is outside tenant scope")
        record.vendor_id = vendor_id

    def list_invoices(self, tenant_id: UUID) -> list[InvoiceRecord]:
        return [record for record in self.invoices.values() if record.tenant_id == tenant_id]

    def get_invoice(self, tenant_id: UUID, invoice_id: UUID) -> InvoiceRecord:
        record = self.invoices[invoice_id]
        if record.tenant_id != tenant_id:
            raise KeyError("invoice is outside tenant scope")
        return record

    def add_vendor(
        self,
        tenant_id: UUID,
        name: str,
        tax_id: str | None = None,
        bank_account_hash: str | None = None,
        vendor_id: UUID | None = None,
    ) -> VendorRecord:
        record = VendorRecord(
            tenant_id=tenant_id,
            vendor_id=vendor_id or uuid4(),
            name=name,
            tax_id=tax_id,
            bank_account_hash=bank_account_hash,
        )
        self.vendors[record.vendor_id] = record
        return record

    def list_vendors(self, tenant_id: UUID) -> list[VendorRecord]:
        return [record for record in self.vendors.values() if record.tenant_id == tenant_id]

    def add_purchase_order(
        self,
        tenant_id: UUID,
        po_number: str,
        vendor_id: UUID,
        total_amount: float,
        lines: list[PurchaseOrderLine] | None = None,
        currency: str = "USD",
    ) -> PurchaseOrderOutput:
        output = PurchaseOrderOutput(
            tenant_id=tenant_id,
            po_number=po_number,
            vendor_id=vendor_id,
            currency=currency,
            total_amount=total_amount,
            lines=lines or [],
        )
        self.purchase_orders[output.purchase_order_id] = PurchaseOrderRecord(output=output)
        return output

    def get_purchase_order_by_number(
        self,
        tenant_id: UUID,
        po_number: str,
    ) -> PurchaseOrderOutput | None:
        for record in self.purchase_orders.values():
            if record.output.tenant_id == tenant_id and record.output.po_number == po_number:
                return record.output
        return None

    def list_purchase_orders(self, tenant_id: UUID) -> list[PurchaseOrderOutput]:
        return [
            record.output
            for record in self.purchase_orders.values()
            if record.output.tenant_id == tenant_id
        ]

    def set_approval_policy(self, policy: ApprovalPolicy) -> None:
        self.approval_policies[policy.tenant_id] = ApprovalPolicyRecord(policy=policy)

    def get_approval_policy(self, tenant_id: UUID) -> ApprovalPolicy:
        record = self.approval_policies.get(tenant_id)
        if record is None:
            policy = ApprovalPolicy(tenant_id=tenant_id)
            self.set_approval_policy(policy)
            return policy
        return record.policy

    def create_approval_task(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        route: ApprovalRoute,
        assigned_role: str,
        status: ApprovalTaskStatus,
        reason: str,
        approval_task_id: UUID | None = None,
    ) -> ApprovalTaskRecord:
        record = ApprovalTaskRecord(
            tenant_id=tenant_id,
            approval_task_id=approval_task_id or uuid4(),
            invoice_id=invoice_id,
            route=route,
            assigned_role=assigned_role,
            status=status,
            reason=reason,
        )
        self.approval_tasks[record.approval_task_id] = record
        return record

    def list_approval_tasks(self, tenant_id: UUID) -> list[ApprovalTaskRecord]:
        return [record for record in self.approval_tasks.values() if record.tenant_id == tenant_id]

    def get_latest_approval_task(self, tenant_id: UUID, invoice_id: UUID) -> ApprovalTaskRecord | None:
        tasks = [
            task
            for task in self.list_approval_tasks(tenant_id)
            if task.invoice_id == invoice_id
        ]
        return tasks[-1] if tasks else None

    def update_approval_task(
        self,
        tenant_id: UUID,
        approval_task_id: UUID,
        status: ApprovalTaskStatus,
        reason: str,
    ) -> ApprovalTaskRecord:
        task = self.approval_tasks[approval_task_id]
        if task.tenant_id != tenant_id:
            raise KeyError("approval task is outside tenant scope")
        task.status = status
        task.reason = reason
        return task

    def store_notification_event(
        self,
        tenant_id: UUID,
        notification_id: UUID,
        invoice_id: UUID,
        notification_type: NotificationType,
        recipient_role: str,
        status: str,
        channel: str,
        payload: dict,
    ) -> NotificationEventRecord:
        record = NotificationEventRecord(
            tenant_id=tenant_id,
            notification_id=notification_id,
            invoice_id=invoice_id,
            notification_type=notification_type,
            recipient_role=recipient_role,
            status=status,
            channel=channel,
            payload=payload,
        )
        self.notification_events[notification_id] = record
        return record

    def list_notification_events(self, tenant_id: UUID) -> list[NotificationEventRecord]:
        return [record for record in self.notification_events.values() if record.tenant_id == tenant_id]

    def store_audit_event(self, event: AuditEventInput, audit_event_id: UUID) -> None:
        self.audit_events[audit_event_id] = AuditEventRecord(
            tenant_id=event.tenant_id,
            audit_event_id=audit_event_id,
            actor_type=str(event.actor_type),
            actor_id=event.actor_id,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            correlation_id=event.correlation_id,
            metadata=event.metadata,
        )

    def list_audit_events(self, tenant_id: UUID) -> list[AuditEventRecord]:
        return [record for record in self.audit_events.values() if record.tenant_id == tenant_id]

    def store_workflow_state(self, state: WorkflowState) -> None:
        self.workflow_states[state.workflow_id] = state

    def list_workflow_states(self, tenant_id: UUID) -> list[WorkflowState]:
        return [record for record in self.workflow_states.values() if record.tenant_id == tenant_id]

    def set_erp_connection_config(self, config: ERPConnectionConfig) -> None:
        self.erp_connection_configs[config.tenant_id] = ERPConnectionConfigRecord(config=config)

    def get_erp_connection_config(self, tenant_id: UUID) -> ERPConnectionConfig:
        record = self.erp_connection_configs.get(tenant_id)
        if record is None:
            config = ERPConnectionConfig(tenant_id=tenant_id, adapter_type=ERPAdapterType.PRIORITY)
            self.set_erp_connection_config(config)
            return config
        return record.config

    def store_erp_sync_log(self, log: ERPSyncLog) -> ERPSyncLog:
        self.erp_sync_logs[log.sync_log_id] = log
        return log

    def list_erp_sync_logs(self, tenant_id: UUID) -> list[ERPSyncLog]:
        return [record for record in self.erp_sync_logs.values() if record.tenant_id == tenant_id]

    def link_external_invoice_id(self, tenant_id: UUID, invoice_id: UUID, external_id: str) -> None:
        invoice = next(
            (record for record in self.list_invoices(tenant_id) if record.invoice_id == invoice_id),
            None,
        )
        if invoice is None:
            raise KeyError("invoice is outside tenant scope")
        self.invoice_external_ids[invoice_id] = external_id

    def get_external_invoice_id(self, tenant_id: UUID, invoice_id: UUID) -> str | None:
        if not any(record.invoice_id == invoice_id for record in self.list_invoices(tenant_id)):
            raise KeyError("invoice is outside tenant scope")
        return self.invoice_external_ids.get(invoice_id)

    def link_external_vendor_id(self, tenant_id: UUID, vendor_id: UUID, external_id: str) -> None:
        if not any(record.vendor_id == vendor_id for record in self.list_vendors(tenant_id)):
            raise KeyError("vendor is outside tenant scope")
        self.vendor_external_ids[vendor_id] = external_id

    def link_external_purchase_order_id(
        self,
        tenant_id: UUID,
        purchase_order_id: UUID,
        external_id: str,
    ) -> None:
        if not any(record.purchase_order_id == purchase_order_id for record in self.list_purchase_orders(tenant_id)):
            raise KeyError("purchase order is outside tenant scope")
        self.po_external_ids[purchase_order_id] = external_id

    def store_review_task(self, task: HumanReviewTask) -> HumanReviewTask:
        self.review_tasks[task.task_id] = task
        return task

    def get_review_task(self, tenant_id: UUID, task_id: UUID) -> HumanReviewTask:
        task = self.review_tasks[task_id]
        if task.tenant_id != tenant_id:
            raise KeyError("review task is outside tenant scope")
        return task

    def list_review_tasks(self, tenant_id: UUID) -> list[HumanReviewTask]:
        return [task for task in self.review_tasks.values() if task.tenant_id == tenant_id]

    def apply_review_corrections(
        self,
        tenant_id: UUID,
        task_id: UUID,
        request: HumanReviewCorrectionRequest,
    ) -> HumanReviewTask:
        task = self.get_review_task(tenant_id, task_id)
        task.corrected_fields.update(request.corrections)
        task.status = HumanReviewStatus.CORRECTED
        task.history.append(
            {
                "action": "corrected",
                "reviewer_id": request.reviewer_id,
                "fields": list(request.corrections),
            }
        )
        return task

    def update_review_task_status(
        self,
        tenant_id: UUID,
        task_id: UUID,
        status: HumanReviewStatus,
        actor_id: str = "system",
    ) -> HumanReviewTask:
        task = self.get_review_task(tenant_id, task_id)
        task.status = status
        task.history.append({"action": str(status), "actor_id": actor_id})
        return task

    def clear_demo_operational_data(self, tenant_id: UUID) -> dict[str, int]:
        invoice_ids = {record.invoice_id for record in self.list_invoices(tenant_id)}
        cleared = {
            "vendor_messages": sum(message.tenant_id == tenant_id for message in self.vendor_messages.values()),
            "vendor_portal_access": sum(
                record.tenant_id == tenant_id for record in self.vendor_portal_access.values()
            ),
            "human_review_tasks": sum(task.tenant_id == tenant_id for task in self.review_tasks.values()),
            "erp_external_references": sum(invoice_id in self.invoice_external_ids for invoice_id in invoice_ids),
            "erp_sync_logs": sum(record.tenant_id == tenant_id for record in self.erp_sync_logs.values()),
            "workflow_events": 0,
            "workflow_states": sum(record.tenant_id == tenant_id for record in self.workflow_states.values()),
            "notification_events": sum(
                record.tenant_id == tenant_id for record in self.notification_events.values()
            ),
            "approval_tasks": sum(record.tenant_id == tenant_id for record in self.approval_tasks.values()),
            "invoice_line_items": sum(
                len(record.canonical_invoice.line_items)
                for record in self.invoices.values()
                if record.tenant_id == tenant_id
            ),
            "uploaded_invoice_documents": sum(
                document.tenant_id == tenant_id for document in self.uploaded_documents.values()
            ),
            "invoices": len(invoice_ids),
        }
        self.raw_invoices = {
            raw_invoice_id: record
            for raw_invoice_id, record in self.raw_invoices.items()
            if record.output.tenant_id != tenant_id
        }
        self.extractions = {
            extraction_id: record
            for extraction_id, record in self.extractions.items()
            if record.tenant_id != tenant_id
        }
        self.invoices = {
            invoice_id: record
            for invoice_id, record in self.invoices.items()
            if record.tenant_id != tenant_id
        }
        self.approval_tasks = {
            task_id: record
            for task_id, record in self.approval_tasks.items()
            if record.tenant_id != tenant_id
        }
        self.notification_events = {
            notification_id: record
            for notification_id, record in self.notification_events.items()
            if record.tenant_id != tenant_id
        }
        self.workflow_states = {
            workflow_id: record
            for workflow_id, record in self.workflow_states.items()
            if record.tenant_id != tenant_id
        }
        self.erp_sync_logs = {
            sync_log_id: record
            for sync_log_id, record in self.erp_sync_logs.items()
            if record.tenant_id != tenant_id
        }
        self.review_tasks = {
            task_id: task
            for task_id, task in self.review_tasks.items()
            if task.tenant_id != tenant_id
        }
        self.uploaded_documents = {
            document_id: document
            for document_id, document in self.uploaded_documents.items()
            if document.tenant_id != tenant_id
        }
        self.vendor_portal_access = {
            access_id: record
            for access_id, record in self.vendor_portal_access.items()
            if record.tenant_id != tenant_id
        }
        self.vendor_messages = {
            message_id: message
            for message_id, message in self.vendor_messages.items()
            if message.tenant_id != tenant_id
        }
        for invoice_id in invoice_ids:
            self.invoice_external_ids.pop(invoice_id, None)
        return cleared

    def ensure_phase3_fixtures(self, tenant_id: UUID) -> None:
        vendors = self.list_vendors(tenant_id)
        if vendors:
            vendor = vendors[0]
        else:
            vendor = self.add_vendor(
                tenant_id=tenant_id,
                name="Northstar Components",
                tax_id="TAX-12345",
            )

        if not self.list_purchase_orders(tenant_id):
            self.add_purchase_order(
                tenant_id=tenant_id,
                po_number="PO-100",
                vendor_id=vendor.vendor_id,
                total_amount=1170,
                lines=[
                    PurchaseOrderLine(
                        description="Mock extracted invoice line",
                        quantity=1,
                        unit_price=1000,
                        total=1170,
                    )
                ],
            )

        self.get_approval_policy(tenant_id)
