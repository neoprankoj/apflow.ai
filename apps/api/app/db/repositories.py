from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.repositories import (
    ApprovalTaskRecord,
    AuditEventRecord,
    InMemoryAPRepository,
    InvoiceRecord,
    NotificationEventRecord,
    PurchaseOrderRecord,
    RawInvoiceRecord,
    VendorRecord,
    VendorPortalAccessRecord,
)
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
    InvoiceIngestionOutput,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    NotificationType,
    UploadedInvoiceDocument,
    TenantMembershipSchema,
    TenantRecordSchema,
    PurchaseOrderLine,
    PurchaseOrderOutput,
    UserRecordSchema,
    UserRole,
    VendorMessageResult,
    WorkflowState,
)
from app.db import models as dbm


DEMO_OPERATIONAL_CLEANUP_MODELS = (
    dbm.VendorMessage,
    dbm.VendorPortalAccess,
    dbm.HumanReviewTask,
    dbm.ERPExternalReference,
    dbm.ERPSyncLog,
    dbm.WorkflowEvent,
    dbm.WorkflowState,
    dbm.NotificationEvent,
    dbm.ApprovalTask,
    dbm.InvoiceLineItem,
    dbm.UploadedInvoiceDocument,
    dbm.Invoice,
)


class SQLAlchemyAPRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.raw_invoices: dict[UUID, RawInvoiceRecord] = {}
        self.extractions = {}

    def create_tenant(
        self,
        name: str,
        slug: str,
        tenant_id: UUID | None = None,
        status: str = "active",
    ) -> TenantRecordSchema:
        row = self.session.get(dbm.Tenant, tenant_id) if tenant_id else None
        if row is None:
            row = self.session.scalar(select(dbm.Tenant).where(dbm.Tenant.slug == slug))
        if row is None:
            row = dbm.Tenant(id=tenant_id or uuid4(), name=name, slug=slug, status=status)
            self.session.add(row)
        else:
            row.name = name
            row.status = status
        self.session.commit()
        return self._tenant_schema(row)

    def get_tenant(self, tenant_id: UUID) -> TenantRecordSchema | None:
        row = self.session.get(dbm.Tenant, tenant_id)
        return self._tenant_schema(row) if row else None

    def create_user(
        self,
        email: str,
        full_name: str,
        hashed_password: str,
        is_active: bool = True,
        user_id: UUID | None = None,
    ) -> UserRecordSchema:
        normalized = email.lower()
        row = self.session.scalar(select(dbm.User).where(dbm.User.email == normalized))
        if row is None:
            row = dbm.User(
                id=user_id or uuid4(),
                email=normalized,
                full_name=full_name,
                hashed_password=hashed_password,
                is_active=is_active,
            )
            self.session.add(row)
        else:
            row.full_name = full_name
            row.hashed_password = hashed_password
            row.is_active = is_active
        self.session.commit()
        return self._user_schema(row)

    def get_user(self, user_id: UUID) -> UserRecordSchema | None:
        row = self.session.get(dbm.User, user_id)
        return self._user_schema(row) if row else None

    def get_user_by_email(self, email: str) -> UserRecordSchema | None:
        row = self.session.scalar(select(dbm.User).where(dbm.User.email == email.lower()))
        return self._user_schema(row) if row else None

    def get_user_password_hash(self, user_id: UUID) -> str | None:
        row = self.session.get(dbm.User, user_id)
        return row.hashed_password if row else None

    def create_membership(
        self,
        tenant_id: UUID,
        user_id: UUID,
        role: UserRole,
        membership_id: UUID | None = None,
    ) -> TenantMembershipSchema:
        self._ensure_tenant(tenant_id)
        row = self.session.scalar(
            select(dbm.TenantMembership).where(
                dbm.TenantMembership.tenant_id == tenant_id,
                dbm.TenantMembership.user_id == user_id,
            )
        )
        if row is None:
            row = dbm.TenantMembership(
                id=membership_id or uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                role=str(role),
            )
            self.session.add(row)
        else:
            row.role = str(role)
        self.session.commit()
        return self._membership_schema(row)

    def get_membership(self, tenant_id: UUID, user_id: UUID) -> TenantMembershipSchema | None:
        row = self.session.scalar(
            select(dbm.TenantMembership).where(
                dbm.TenantMembership.tenant_id == tenant_id,
                dbm.TenantMembership.user_id == user_id,
            )
        )
        return self._membership_schema(row) if row else None

    def list_memberships_for_user(self, user_id: UUID) -> list[TenantMembershipSchema]:
        rows = self.session.scalars(select(dbm.TenantMembership).where(dbm.TenantMembership.user_id == user_id)).all()
        return [self._membership_schema(row) for row in rows]

    def list_memberships_for_tenant(self, tenant_id: UUID) -> list[TenantMembershipSchema]:
        rows = self.session.scalars(
            select(dbm.TenantMembership).where(dbm.TenantMembership.tenant_id == tenant_id)
        ).all()
        return [self._membership_schema(row) for row in rows]

    def list_users_for_tenant(self, tenant_id: UUID) -> list[tuple[UserRecordSchema, TenantMembershipSchema]]:
        rows = self.session.execute(
            select(dbm.User, dbm.TenantMembership)
            .join(dbm.TenantMembership, dbm.TenantMembership.user_id == dbm.User.id)
            .where(dbm.TenantMembership.tenant_id == tenant_id)
        ).all()
        return [(self._user_schema(user), self._membership_schema(membership)) for user, membership in rows]

    def update_membership_role(self, tenant_id: UUID, user_id: UUID, role: UserRole) -> TenantMembershipSchema:
        row = self.session.scalar(
            select(dbm.TenantMembership).where(
                dbm.TenantMembership.tenant_id == tenant_id,
                dbm.TenantMembership.user_id == user_id,
            )
        )
        if row is None:
            raise KeyError("user is not a member of tenant")
        row.role = str(role)
        self.session.commit()
        return self._membership_schema(row)

    def deactivate_user(self, tenant_id: UUID, user_id: UUID) -> UserRecordSchema:
        if self.get_membership(tenant_id, user_id) is None:
            raise KeyError("user is not a member of tenant")
        row = self.session.get(dbm.User, user_id)
        if row is None:
            raise KeyError("user does not exist")
        row.is_active = False
        self.session.commit()
        return self._user_schema(row)

    def create_vendor_portal_access(
        self,
        tenant_id: UUID,
        vendor_id: UUID,
        email: str,
        access_token_hash: str,
        status: str = "active",
        expires_at=None,
        access_id: UUID | None = None,
    ) -> VendorPortalAccessRecord:
        self._ensure_tenant(tenant_id)
        row = dbm.VendorPortalAccess(
            id=access_id or uuid4(),
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            email=email.lower(),
            access_token_hash=access_token_hash,
            status=status,
            expires_at=expires_at,
        )
        self.session.add(row)
        self.session.commit()
        return self._vendor_access_record(row)

    def list_vendor_portal_access(self, tenant_id: UUID) -> list[VendorPortalAccessRecord]:
        rows = self.session.scalars(
            select(dbm.VendorPortalAccess).where(dbm.VendorPortalAccess.tenant_id == tenant_id)
        ).all()
        return [self._vendor_access_record(row) for row in rows]

    def get_vendor_access_by_hash(
        self,
        tenant_id: UUID,
        access_token_hash: str,
    ) -> VendorPortalAccessRecord | None:
        from datetime import UTC, datetime

        row = self.session.scalar(
            select(dbm.VendorPortalAccess).where(
                dbm.VendorPortalAccess.tenant_id == tenant_id,
                dbm.VendorPortalAccess.access_token_hash == access_token_hash,
                dbm.VendorPortalAccess.status == "active",
            )
        )
        if row is None:
            return None
        if row.expires_at is not None and row.expires_at < datetime.now(UTC):
            return None
        return self._vendor_access_record(row)

    def store_vendor_message(self, message: VendorMessageResult) -> VendorMessageResult:
        self._ensure_tenant(message.tenant_id)
        row = dbm.VendorMessage(
            id=message.message_id,
            tenant_id=message.tenant_id,
            vendor_id=message.vendor_id,
            invoice_id=message.invoice_id,
            sender_email=message.sender_email,
            message=message.message,
            status=message.status,
        )
        self.session.add(row)
        self.session.commit()
        return message

    def list_vendor_messages(
        self,
        tenant_id: UUID,
        vendor_id: UUID | None = None,
    ) -> list[VendorMessageResult]:
        query = select(dbm.VendorMessage).where(dbm.VendorMessage.tenant_id == tenant_id)
        if vendor_id is not None:
            query = query.where(dbm.VendorMessage.vendor_id == vendor_id)
        rows = self.session.scalars(query).all()
        return [self._vendor_message_result(row) for row in rows]

    def store_uploaded_document(self, document: UploadedInvoiceDocument) -> UploadedInvoiceDocument:
        self._ensure_tenant(document.tenant_id)
        row = dbm.UploadedInvoiceDocument(
            id=document.document_id,
            tenant_id=document.tenant_id,
            original_file_name=document.original_file_name,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            storage_provider=document.storage_provider,
            storage_key=document.storage_key,
            uploaded_by=document.uploaded_by,
        )
        self.session.add(row)
        self.session.commit()
        return document

    def get_uploaded_document(self, tenant_id: UUID, document_id: UUID) -> UploadedInvoiceDocument:
        row = self.session.get(dbm.UploadedInvoiceDocument, document_id)
        if row is None or row.tenant_id != tenant_id:
            raise KeyError("document is outside tenant scope")
        return self._uploaded_document(row)

    def list_uploaded_documents(self, tenant_id: UUID) -> list[UploadedInvoiceDocument]:
        rows = self.session.scalars(
            select(dbm.UploadedInvoiceDocument).where(dbm.UploadedInvoiceDocument.tenant_id == tenant_id)
        ).all()
        return [self._uploaded_document(row) for row in rows]

    def store_raw_invoice(
        self,
        output: InvoiceIngestionOutput,
        content: str | bytes | None = None,
    ) -> None:
        self._ensure_tenant(output.tenant_id)
        self.raw_invoices[output.raw_invoice_id] = RawInvoiceRecord(output=output, content=content)

    def get_raw_invoice(self, tenant_id: UUID, raw_invoice_id: UUID) -> RawInvoiceRecord:
        record = self.raw_invoices[raw_invoice_id]
        if record.output.tenant_id != tenant_id:
            raise KeyError("raw invoice is outside tenant scope")
        return record

    def store_extraction(self, output) -> None:
        self.extractions[output.extraction_id] = output

    def store_invoice(self, output: InvoiceNormalizationOutput) -> None:
        self._ensure_tenant(output.tenant_id)
        invoice = output.canonical_invoice
        existing = self.session.get(dbm.Invoice, output.invoice_id)
        if existing is None:
            existing = dbm.Invoice(
                id=output.invoice_id,
                tenant_id=output.tenant_id,
                invoice_number=invoice.invoice_number,
                invoice_date=invoice.invoice_date,
                due_date=invoice.due_date,
                currency=invoice.currency,
                subtotal=Decimal(str(invoice.subtotal)),
                tax_total=Decimal(str(invoice.tax_total)),
                grand_total=Decimal(str(invoice.grand_total)),
                file_checksum=output.file_checksum,
                canonical_payload=invoice.model_dump(mode="json"),
            )
            self.session.add(existing)
        else:
            existing.canonical_payload = invoice.model_dump(mode="json")
            existing.file_checksum = output.file_checksum

        for line in invoice.line_items:
            self.session.add(
                dbm.InvoiceLineItem(
                    tenant_id=output.tenant_id,
                    invoice_id=output.invoice_id,
                    description=line.description,
                    quantity=Decimal(str(line.quantity)),
                    unit_price=Decimal(str(line.unit_price)),
                    tax_amount=Decimal(str(line.tax_amount)),
                    total=Decimal(str(line.total)),
                    po_number=line.po_number,
                )
            )
        self.session.commit()

    def update_invoice_vendor(self, tenant_id: UUID, invoice_id: UUID, vendor_id: UUID | None) -> None:
        invoice = self._get_invoice_model(tenant_id, invoice_id)
        invoice.vendor_id = vendor_id
        self.session.commit()

    def list_invoices(self, tenant_id: UUID) -> list[InvoiceRecord]:
        rows = self.session.scalars(
            select(dbm.Invoice).where(dbm.Invoice.tenant_id == tenant_id).order_by(dbm.Invoice.created_at)
        ).all()
        return [self._invoice_record(row) for row in rows]

    def get_invoice(self, tenant_id: UUID, invoice_id: UUID) -> InvoiceRecord:
        return self._invoice_record(self._get_invoice_model(tenant_id, invoice_id))

    def add_vendor(
        self,
        tenant_id: UUID,
        name: str,
        tax_id: str | None = None,
        bank_account_hash: str | None = None,
        vendor_id: UUID | None = None,
    ) -> VendorRecord:
        self._ensure_tenant(tenant_id)
        existing = None
        if vendor_id is not None:
            existing = self.session.get(dbm.Vendor, vendor_id)
        if existing is None and tax_id:
            existing = self.session.scalar(
                select(dbm.Vendor).where(dbm.Vendor.tenant_id == tenant_id, dbm.Vendor.tax_id == tax_id)
            )
        if existing is None:
            existing = dbm.Vendor(
                id=vendor_id or uuid4(),
                tenant_id=tenant_id,
                name=name,
                tax_id=tax_id,
                bank_account_hash=bank_account_hash,
            )
            self.session.add(existing)
            self.session.commit()
        return VendorRecord(
            tenant_id=tenant_id,
            vendor_id=existing.id,
            name=existing.name,
            tax_id=existing.tax_id,
            bank_account_hash=existing.bank_account_hash,
        )

    def list_vendors(self, tenant_id: UUID) -> list[VendorRecord]:
        rows = self.session.scalars(select(dbm.Vendor).where(dbm.Vendor.tenant_id == tenant_id)).all()
        return [
            VendorRecord(
                tenant_id=row.tenant_id,
                vendor_id=row.id,
                name=row.name,
                tax_id=row.tax_id,
                bank_account_hash=row.bank_account_hash,
            )
            for row in rows
        ]

    def add_purchase_order(
        self,
        tenant_id: UUID,
        po_number: str,
        vendor_id: UUID,
        total_amount: float,
        lines: list[PurchaseOrderLine] | None = None,
        currency: str = "USD",
    ) -> PurchaseOrderOutput:
        self._ensure_tenant(tenant_id)
        existing = self.session.scalar(
            select(dbm.PurchaseOrder).where(
                dbm.PurchaseOrder.tenant_id == tenant_id,
                dbm.PurchaseOrder.po_number == po_number,
            )
        )
        if existing is None:
            existing = dbm.PurchaseOrder(
                tenant_id=tenant_id,
                po_number=po_number,
                vendor_id=vendor_id,
                total_amount=Decimal(str(total_amount)),
                currency=currency,
            )
            self.session.add(existing)
            self.session.flush()
            for line in lines or []:
                self.session.add(
                    dbm.PurchaseOrderLineItem(
                        tenant_id=tenant_id,
                        purchase_order_id=existing.id,
                        description=line.description,
                        quantity=Decimal(str(line.quantity)),
                        unit_price=Decimal(str(line.unit_price)),
                        total=Decimal(str(line.total)),
                    )
                )
            self.session.commit()
        return self._po_output(existing)

    def get_purchase_order_by_number(self, tenant_id: UUID, po_number: str) -> PurchaseOrderOutput | None:
        row = self.session.scalar(
            select(dbm.PurchaseOrder).where(
                dbm.PurchaseOrder.tenant_id == tenant_id,
                dbm.PurchaseOrder.po_number == po_number,
            )
        )
        return self._po_output(row) if row else None

    def list_purchase_orders(self, tenant_id: UUID) -> list[PurchaseOrderOutput]:
        rows = self.session.scalars(
            select(dbm.PurchaseOrder).where(dbm.PurchaseOrder.tenant_id == tenant_id)
        ).all()
        return [self._po_output(row) for row in rows]

    def set_approval_policy(self, policy: ApprovalPolicy) -> None:
        self._ensure_tenant(policy.tenant_id)
        row = self.session.scalar(
            select(dbm.ApprovalPolicy).where(dbm.ApprovalPolicy.tenant_id == policy.tenant_id)
        )
        if row is None:
            row = dbm.ApprovalPolicy(tenant_id=policy.tenant_id)
            self.session.add(row)
        row.auto_approve_limit = Decimal(str(policy.auto_approve_limit))
        row.manager_approval_limit = Decimal(str(policy.manager_approval_limit))
        row.controller_approval_limit = Decimal(str(policy.controller_approval_limit))
        row.high_risk_blocks = policy.high_risk_blocks
        self.session.commit()

    def get_approval_policy(self, tenant_id: UUID) -> ApprovalPolicy:
        row = self.session.scalar(select(dbm.ApprovalPolicy).where(dbm.ApprovalPolicy.tenant_id == tenant_id))
        if row is None:
            policy = ApprovalPolicy(tenant_id=tenant_id)
            self.set_approval_policy(policy)
            return policy
        return ApprovalPolicy(
            tenant_id=tenant_id,
            auto_approve_limit=float(row.auto_approve_limit),
            manager_approval_limit=float(row.manager_approval_limit),
            controller_approval_limit=float(row.controller_approval_limit),
            high_risk_blocks=row.high_risk_blocks,
        )

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
        self._ensure_tenant(tenant_id)
        row = dbm.ApprovalTask(
            id=approval_task_id or uuid4(),
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            route=str(route),
            assigned_role=assigned_role,
            status=str(status),
            reason=reason,
        )
        self.session.add(row)
        self.session.commit()
        return self._approval_task_record(row)

    def list_approval_tasks(self, tenant_id: UUID) -> list[ApprovalTaskRecord]:
        rows = self.session.scalars(
            select(dbm.ApprovalTask)
            .where(dbm.ApprovalTask.tenant_id == tenant_id)
            .order_by(dbm.ApprovalTask.created_at, dbm.ApprovalTask.updated_at)
        ).all()
        return [self._approval_task_record(row) for row in rows]

    def get_latest_approval_task(self, tenant_id: UUID, invoice_id: UUID) -> ApprovalTaskRecord | None:
        row = self.session.scalar(
            select(dbm.ApprovalTask)
            .where(
                dbm.ApprovalTask.tenant_id == tenant_id,
                dbm.ApprovalTask.invoice_id == invoice_id,
            )
            .order_by(dbm.ApprovalTask.created_at.desc(), dbm.ApprovalTask.updated_at.desc())
        )
        return self._approval_task_record(row) if row else None

    def update_approval_task(
        self,
        tenant_id: UUID,
        approval_task_id: UUID,
        status: ApprovalTaskStatus,
        reason: str,
    ) -> ApprovalTaskRecord:
        row = self.session.get(dbm.ApprovalTask, approval_task_id)
        if row is None or row.tenant_id != tenant_id:
            raise KeyError("approval task is outside tenant scope")
        row.status = str(status)
        row.reason = reason
        self.session.commit()
        return self._approval_task_record(row)

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
        self._ensure_tenant(tenant_id)
        row = dbm.NotificationEvent(
            id=notification_id,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            notification_type=str(notification_type),
            recipient_role=recipient_role,
            status=status,
            channel=channel,
            payload=payload,
        )
        self.session.add(row)
        self.session.commit()
        return self._notification_record(row)

    def list_notification_events(self, tenant_id: UUID) -> list[NotificationEventRecord]:
        rows = self.session.scalars(
            select(dbm.NotificationEvent).where(dbm.NotificationEvent.tenant_id == tenant_id)
        ).all()
        return [self._notification_record(row) for row in rows]

    def store_audit_event(self, event: AuditEventInput, audit_event_id: UUID) -> None:
        self._ensure_tenant(event.tenant_id)
        self.session.add(
            dbm.AuditEvent(
                id=audit_event_id,
                tenant_id=event.tenant_id,
                actor_type=str(event.actor_type),
                actor_id=event.actor_id,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                correlation_id=event.correlation_id,
                metadata_json=event.metadata,
            )
        )
        self.session.commit()

    def list_audit_events(self, tenant_id: UUID) -> list[AuditEventRecord]:
        rows = self.session.scalars(select(dbm.AuditEvent).where(dbm.AuditEvent.tenant_id == tenant_id)).all()
        return [
            AuditEventRecord(
                tenant_id=row.tenant_id,
                audit_event_id=row.id,
                actor_type=row.actor_type,
                actor_id=row.actor_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                correlation_id=row.correlation_id,
                metadata=row.metadata_json,
            )
            for row in rows
        ]

    def store_workflow_state(self, state: WorkflowState) -> None:
        self._ensure_tenant(state.tenant_id)
        row = self.session.scalar(
            select(dbm.WorkflowState).where(
                dbm.WorkflowState.tenant_id == state.tenant_id,
                dbm.WorkflowState.workflow_id == state.workflow_id,
            )
        )
        if row is None:
            row = dbm.WorkflowState(tenant_id=state.tenant_id, workflow_id=state.workflow_id)
            self.session.add(row)
        row.state = state.state
        row.status = str(state.status)
        row.current_agent = state.current_agent
        row.retry_count = state.retry_count
        row.context = {}
        self.session.commit()

    def list_workflow_states(self, tenant_id: UUID) -> list[WorkflowState]:
        rows = self.session.scalars(select(dbm.WorkflowState).where(dbm.WorkflowState.tenant_id == tenant_id)).all()
        return [
            WorkflowState(
                workflow_id=row.workflow_id,
                tenant_id=row.tenant_id,
                state=row.state,
                status=row.status,
                current_agent=row.current_agent,
                retry_count=row.retry_count,
            )
            for row in rows
        ]

    def ensure_phase3_fixtures(self, tenant_id: UUID) -> None:
        InMemoryAPRepository.ensure_phase3_fixtures(self, tenant_id)  # type: ignore[arg-type]

    def set_erp_connection_config(self, config: ERPConnectionConfig) -> None:
        self._ensure_tenant(config.tenant_id)
        row = self.session.scalar(
            select(dbm.ERPConnectionConfig).where(dbm.ERPConnectionConfig.tenant_id == config.tenant_id)
        )
        if row is None:
            row = dbm.ERPConnectionConfig(tenant_id=config.tenant_id)
            self.session.add(row)
        row.adapter_type = str(config.adapter_type)
        row.enabled = config.enabled
        row.config = config.config
        self.session.commit()

    def get_erp_connection_config(self, tenant_id: UUID) -> ERPConnectionConfig:
        row = self.session.scalar(
            select(dbm.ERPConnectionConfig).where(dbm.ERPConnectionConfig.tenant_id == tenant_id)
        )
        if row is None:
            config = ERPConnectionConfig(tenant_id=tenant_id, adapter_type=ERPAdapterType.PRIORITY)
            self.set_erp_connection_config(config)
            return config
        return ERPConnectionConfig(
            tenant_id=tenant_id,
            adapter_type=ERPAdapterType(row.adapter_type),
            enabled=row.enabled,
            config=row.config,
        )

    def store_erp_sync_log(self, log: ERPSyncLog) -> ERPSyncLog:
        self._ensure_tenant(log.tenant_id)
        self.session.add(
            dbm.ERPSyncLog(
                id=log.sync_log_id,
                tenant_id=log.tenant_id,
                adapter_type=str(log.adapter_type),
                operation=str(log.operation),
                status=str(log.status),
                records_processed=log.records_processed,
                external_id=log.external_id,
                invoice_id=log.invoice_id,
                errors=log.errors,
                metadata_json=log.metadata,
            )
        )
        self.session.commit()
        return log

    def list_erp_sync_logs(self, tenant_id: UUID) -> list[ERPSyncLog]:
        rows = self.session.scalars(select(dbm.ERPSyncLog).where(dbm.ERPSyncLog.tenant_id == tenant_id)).all()
        return [
            ERPSyncLog(
                sync_log_id=row.id,
                tenant_id=row.tenant_id,
                adapter_type=ERPAdapterType(row.adapter_type),
                operation=ERPOperation(row.operation),
                status=ERPSyncStatus(row.status),
                records_processed=row.records_processed,
                external_id=row.external_id,
                invoice_id=row.invoice_id,
                errors=row.errors,
                metadata=row.metadata_json,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def link_external_invoice_id(self, tenant_id: UUID, invoice_id: UUID, external_id: str) -> None:
        self._get_invoice_model(tenant_id, invoice_id)
        config = self.get_erp_connection_config(tenant_id)
        row = self.session.scalar(
            select(dbm.ERPExternalReference).where(
                dbm.ERPExternalReference.tenant_id == tenant_id,
                dbm.ERPExternalReference.entity_type == "invoice",
                dbm.ERPExternalReference.entity_id == invoice_id,
                dbm.ERPExternalReference.adapter_type == str(config.adapter_type),
            )
        )
        if row is None:
            row = dbm.ERPExternalReference(
                tenant_id=tenant_id,
                entity_type="invoice",
                entity_id=invoice_id,
                adapter_type=str(config.adapter_type),
                external_id=external_id,
            )
            self.session.add(row)
        else:
            row.external_id = external_id
        self.session.commit()

    def get_external_invoice_id(self, tenant_id: UUID, invoice_id: UUID) -> str | None:
        self._get_invoice_model(tenant_id, invoice_id)
        config = self.get_erp_connection_config(tenant_id)
        row = self.session.scalar(
            select(dbm.ERPExternalReference).where(
                dbm.ERPExternalReference.tenant_id == tenant_id,
                dbm.ERPExternalReference.entity_type == "invoice",
                dbm.ERPExternalReference.entity_id == invoice_id,
                dbm.ERPExternalReference.adapter_type == str(config.adapter_type),
            )
        )
        return row.external_id if row else None

    def store_review_task(self, task: HumanReviewTask) -> HumanReviewTask:
        self._ensure_tenant(task.tenant_id)
        row = dbm.HumanReviewTask(
            id=task.task_id,
            tenant_id=task.tenant_id,
            invoice_id=task.invoice_id,
            raw_invoice_id=task.raw_invoice_id,
            extraction_id=task.extraction_id,
            status=str(task.status),
            issues=[issue.model_dump(mode="json") for issue in task.issues],
            corrected_fields=task.corrected_fields,
            history=task.history,
        )
        self.session.add(row)
        self.session.commit()
        return task

    def get_review_task(self, tenant_id: UUID, task_id: UUID) -> HumanReviewTask:
        row = self.session.get(dbm.HumanReviewTask, task_id)
        if row is None or row.tenant_id != tenant_id:
            raise KeyError("review task is outside tenant scope")
        return self._review_task(row)

    def list_review_tasks(self, tenant_id: UUID) -> list[HumanReviewTask]:
        rows = self.session.scalars(
            select(dbm.HumanReviewTask).where(dbm.HumanReviewTask.tenant_id == tenant_id)
        ).all()
        return [self._review_task(row) for row in rows]

    def apply_review_corrections(
        self,
        tenant_id: UUID,
        task_id: UUID,
        request: HumanReviewCorrectionRequest,
    ) -> HumanReviewTask:
        row = self.session.get(dbm.HumanReviewTask, task_id)
        if row is None or row.tenant_id != tenant_id:
            raise KeyError("review task is outside tenant scope")
        corrected = dict(row.corrected_fields)
        corrected.update(request.corrections)
        row.corrected_fields = corrected
        row.status = str(HumanReviewStatus.CORRECTED)
        row.history = [
            *row.history,
            {
                "action": "corrected",
                "reviewer_id": request.reviewer_id,
                "fields": list(request.corrections),
            },
        ]
        self.session.commit()
        return self._review_task(row)

    def update_review_task_status(
        self,
        tenant_id: UUID,
        task_id: UUID,
        status: HumanReviewStatus,
        actor_id: str = "system",
    ) -> HumanReviewTask:
        row = self.session.get(dbm.HumanReviewTask, task_id)
        if row is None or row.tenant_id != tenant_id:
            raise KeyError("review task is outside tenant scope")
        row.status = str(status)
        row.history = [*row.history, {"action": str(status), "actor_id": actor_id}]
        self.session.commit()
        return self._review_task(row)

    def clear_demo_operational_data(self, tenant_id: UUID) -> dict[str, int]:
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
        cleared: dict[str, int] = {}
        try:
            for model in DEMO_OPERATIONAL_CLEANUP_MODELS:
                result = self.session.execute(delete(model).where(model.tenant_id == tenant_id))
                cleared[model.__tablename__] = result.rowcount or 0
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return cleared

    def link_external_vendor_id(self, tenant_id: UUID, vendor_id: UUID, external_id: str) -> None:
        vendor = self.session.get(dbm.Vendor, vendor_id)
        if vendor is None or vendor.tenant_id != tenant_id:
            raise KeyError("vendor is outside tenant scope")
        self._link_external_reference(tenant_id, "vendor", vendor_id, external_id)

    def link_external_purchase_order_id(
        self,
        tenant_id: UUID,
        purchase_order_id: UUID,
        external_id: str,
    ) -> None:
        po = self.session.get(dbm.PurchaseOrder, purchase_order_id)
        if po is None or po.tenant_id != tenant_id:
            raise KeyError("purchase order is outside tenant scope")
        self._link_external_reference(tenant_id, "purchase_order", purchase_order_id, external_id)

    def _link_external_reference(
        self,
        tenant_id: UUID,
        entity_type: str,
        entity_id: UUID,
        external_id: str,
    ) -> None:
        config = self.get_erp_connection_config(tenant_id)
        row = self.session.scalar(
            select(dbm.ERPExternalReference).where(
                dbm.ERPExternalReference.tenant_id == tenant_id,
                dbm.ERPExternalReference.entity_type == entity_type,
                dbm.ERPExternalReference.entity_id == entity_id,
                dbm.ERPExternalReference.adapter_type == str(config.adapter_type),
            )
        )
        if row is None:
            row = dbm.ERPExternalReference(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                adapter_type=str(config.adapter_type),
                external_id=external_id,
            )
            self.session.add(row)
        else:
            row.external_id = external_id
        self.session.commit()

    def _ensure_tenant(self, tenant_id: UUID) -> None:
        if self.session.get(dbm.Tenant, tenant_id) is None:
            self.session.add(
                dbm.Tenant(
                    id=tenant_id,
                    name=f"Demo Tenant {tenant_id}",
                    slug=f"tenant-{tenant_id}",
                    status="active",
                    country_code="US",
                )
            )
            self.session.commit()

    def _get_invoice_model(self, tenant_id: UUID, invoice_id: UUID) -> dbm.Invoice:
        row = self.session.get(dbm.Invoice, invoice_id)
        if row is None or row.tenant_id != tenant_id:
            raise KeyError("invoice is outside tenant scope")
        return row

    def _invoice_record(self, row: dbm.Invoice) -> InvoiceRecord:
        payload = dict(row.canonical_payload)
        if "line_items" not in payload:
            payload["line_items"] = [
                {
                    "description": line.description,
                    "quantity": float(line.quantity),
                    "unit_price": float(line.unit_price),
                    "tax_amount": float(line.tax_amount),
                    "total": float(line.total),
                    "po_number": line.po_number,
                }
                for line in row.lines
            ]
        return InvoiceRecord(
            tenant_id=row.tenant_id,
            invoice_id=row.id,
            canonical_invoice=CanonicalInvoice(**payload),
            vendor_id=row.vendor_id,
            file_checksum=row.file_checksum,
        )

    def _po_output(self, row: dbm.PurchaseOrder) -> PurchaseOrderOutput:
        return PurchaseOrderOutput(
            tenant_id=row.tenant_id,
            purchase_order_id=row.id,
            po_number=row.po_number,
            vendor_id=row.vendor_id,
            currency=row.currency,
            total_amount=float(row.total_amount),
            status=row.status,
            lines=[
                PurchaseOrderLine(
                    description=line.description,
                    quantity=float(line.quantity),
                    unit_price=float(line.unit_price),
                    total=float(line.total),
                )
                for line in row.lines
            ],
        )

    def _approval_task_record(self, row: dbm.ApprovalTask) -> ApprovalTaskRecord:
        return ApprovalTaskRecord(
            tenant_id=row.tenant_id,
            approval_task_id=row.id,
            invoice_id=row.invoice_id,
            route=ApprovalRoute(row.route),
            assigned_role=row.assigned_role,
            status=ApprovalTaskStatus(row.status),
            reason=row.reason,
        )

    def _notification_record(self, row: dbm.NotificationEvent) -> NotificationEventRecord:
        return NotificationEventRecord(
            tenant_id=row.tenant_id,
            notification_id=row.id,
            invoice_id=row.invoice_id,
            notification_type=NotificationType(row.notification_type),
            recipient_role=row.recipient_role,
            status=row.status,
            channel=row.channel,
            payload=row.payload,
        )

    def _review_task(self, row: dbm.HumanReviewTask) -> HumanReviewTask:
        from app.core.schemas import HumanReviewFieldIssue

        return HumanReviewTask(
            task_id=row.id,
            tenant_id=row.tenant_id,
            invoice_id=row.invoice_id,
            raw_invoice_id=row.raw_invoice_id,
            extraction_id=row.extraction_id,
            status=HumanReviewStatus(row.status),
            issues=[HumanReviewFieldIssue(**issue) for issue in row.issues],
            corrected_fields=row.corrected_fields,
            history=row.history,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _tenant_schema(self, row: dbm.Tenant) -> TenantRecordSchema:
        return TenantRecordSchema(
            id=row.id,
            name=row.name,
            slug=row.slug,
            status=row.status,
            created_at=row.created_at,
        )

    def _user_schema(self, row: dbm.User) -> UserRecordSchema:
        return UserRecordSchema(
            id=row.id,
            email=row.email,
            full_name=row.full_name,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    def _membership_schema(self, row: dbm.TenantMembership) -> TenantMembershipSchema:
        return TenantMembershipSchema(
            id=row.id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            role=UserRole(row.role),
            created_at=row.created_at,
        )

    def _vendor_access_record(self, row: dbm.VendorPortalAccess) -> VendorPortalAccessRecord:
        return VendorPortalAccessRecord(
            access_id=row.id,
            tenant_id=row.tenant_id,
            vendor_id=row.vendor_id,
            email=row.email,
            access_token_hash=row.access_token_hash,
            status=row.status,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )

    def _vendor_message_result(self, row: dbm.VendorMessage) -> VendorMessageResult:
        return VendorMessageResult(
            message_id=row.id,
            tenant_id=row.tenant_id,
            vendor_id=row.vendor_id,
            invoice_id=row.invoice_id,
            sender_email=row.sender_email,
            message=row.message,
            status=row.status,
            created_at=row.created_at,
        )

    def _uploaded_document(self, row: dbm.UploadedInvoiceDocument) -> UploadedInvoiceDocument:
        return UploadedInvoiceDocument(
            document_id=row.id,
            tenant_id=row.tenant_id,
            original_file_name=row.original_file_name,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            storage_provider=row.storage_provider,
            storage_key=row.storage_key,
            uploaded_by=row.uploaded_by,
            created_at=row.created_at,
        )
