from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.repositories import InMemoryAPRepository, VendorRecord
from app.core.schemas import (
    ActorType,
    ApprovalRoute,
    ApprovalTaskStatus,
    AuditEventInput,
    CanonicalInvoice,
    DemoSeedProfileRead,
    DemoSeedResult,
    ERPAdapterType,
    ERPConnectionConfig,
    ERPOperation,
    ERPSyncLog,
    ERPSyncStatus,
    HumanReviewFieldIssue,
    HumanReviewStatus,
    HumanReviewTask,
    InvoiceLineItem,
    InvoiceNormalizationOutput,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationRecipientType,
    NotificationType,
    PaymentStatusSource,
    PaymentStatusValue,
    PriorityEntityMapping,
    PriorityMappingConfig,
    PurchaseOrderLine,
    UsageEventSource,
    UsageEventType,
    VendorAccessCreatedResponse,
    WorkflowState,
    WorkflowStatus,
)
from app.core.vendor_portal import (
    generate_vendor_access_token,
    hash_vendor_access_token,
    vendor_access_token_prefix,
)
from app.integrations.erp.priority_mapping import config_with_priority_mapping

CONFIRM_TEXT = "SEED_DEMO_PROFILE"


@dataclass(frozen=True)
class SeedProfileDefinition:
    key: str
    label: str
    description: str
    recommended_for: str
    includes: tuple[str, ...]


PROFILE_DEFINITIONS: dict[str, SeedProfileDefinition] = {
    "clean_minimal": SeedProfileDefinition(
        key="clean_minimal",
        label="Clean Minimal",
        description="Clean tenant baseline with minimal vendor and PO fixtures.",
        recommended_for="Fresh QA starts and demos where the presenter wants to upload a new invoice live.",
        includes=("owner/admin users are preserved", "one supplier", "one purchase order", "no workflow history"),
    ),
    "ap_manager_demo": SeedProfileDefinition(
        key="ap_manager_demo",
        label="AP Manager Demo",
        description="Core AP workflow with review, approval, hold/reject, discount, and export-ready examples.",
        recommended_for="End-to-end AP manager walkthroughs.",
        includes=("review-required invoice", "pending approval", "approved/exported invoice", "discounted invoice", "blocked invoice"),
    ),
    "vendor_self_service_demo": SeedProfileDefinition(
        key="vendor_self_service_demo",
        label="Vendor Self-Service Demo",
        description="Vendor portal, safe payment statuses, and chatbot-ready invoice examples.",
        recommended_for="Supplier self-service and payment-status demos.",
        includes=("active vendor access", "scheduled payment", "paid invoice", "disputed invoice", "one-time vendor link"),
    ),
    "priority_connector_demo": SeedProfileDefinition(
        key="priority_connector_demo",
        label="Priority Connector Demo",
        description="Priority mapping and imported-record examples while keeping real writes disabled.",
        recommended_for="Priority ERP connector walkthroughs.",
        includes=("sample Priority mapping", "imported vendor", "imported PO", "mock-safe readiness"),
    ),
    "compliance_demo": SeedProfileDefinition(
        key="compliance_demo",
        label="Compliance Demo",
        description="Invoices that show compliance-ready and missing-tax-field validation outcomes.",
        recommended_for="E-invoicing validation demos.",
        includes=("Generic B2B-ready invoice", "missing supplier tax ID", "VAT/tax warning invoice", "buyer ID caveat"),
    ),
    "analytics_rich_demo": SeedProfileDefinition(
        key="analytics_rich_demo",
        label="Analytics-Rich Demo",
        description="Populates APFlow with enough deterministic activity to show analytics, usage, notifications, and vendor activity.",
        recommended_for="Founder demos, internal QA, and dashboard screenshots.",
        includes=("AP workflow examples", "payment distribution", "vendor chatbot events", "notification deliveries", "usage events", "compliance examples"),
    ),
}


class DemoSeedService:
    def __init__(self, repository: InMemoryAPRepository) -> None:
        self.repository = repository

    def list_profiles(self) -> list[DemoSeedProfileRead]:
        return [
            DemoSeedProfileRead(
                key=profile.key,
                label=profile.label,
                description=profile.description,
                recommended_for=profile.recommended_for,
                includes=list(profile.includes),
                destructive=True,
            )
            for profile in PROFILE_DEFINITIONS.values()
        ]

    def seed_profile(
        self,
        *,
        tenant_id: UUID,
        profile_key: str,
        actor_id: str,
        actor_user_id: UUID | None = None,
    ) -> DemoSeedResult:
        if profile_key not in PROFILE_DEFINITIONS:
            raise ValueError(f"Unknown demo seed profile: {profile_key}")

        self._audit(tenant_id, actor_id, "demo.seed_profile_started", {"profile_key": profile_key})
        cleared = self.repository.clear_demo_operational_data(tenant_id)
        self.repository.ensure_phase3_fixtures(tenant_id)

        ctx = _SeedContext(tenant_id=tenant_id, actor_id=actor_id, actor_user_id=actor_user_id)
        if profile_key == "clean_minimal":
            self._seed_clean_minimal(ctx)
        elif profile_key == "ap_manager_demo":
            self._seed_ap_manager_demo(ctx)
        elif profile_key == "vendor_self_service_demo":
            self._seed_vendor_self_service_demo(ctx)
        elif profile_key == "priority_connector_demo":
            self._seed_priority_connector_demo(ctx)
        elif profile_key == "compliance_demo":
            self._seed_compliance_demo(ctx)
        elif profile_key == "analytics_rich_demo":
            self._seed_analytics_rich_demo(ctx)

        created_counts = dict(ctx.created_counts)
        skipped_counts = {"cleared_" + key: value for key, value in cleared.items() if value}
        self._audit(
            tenant_id,
            actor_id,
            "demo.seed_profile_completed",
            {"profile_key": profile_key, "created_counts": created_counts, "warning_count": len(ctx.warnings)},
        )
        return DemoSeedResult(
            tenant_id=tenant_id,
            profile_key=profile_key,
            status="seeded",
            created_counts=created_counts,
            skipped_counts=skipped_counts,
            warnings=ctx.warnings,
            next_steps=self._next_steps(profile_key),
            generated_vendor_links=ctx.generated_vendor_links,
            message=f"Demo seed profile `{profile_key}` completed for this tenant.",
        )

    def _seed_clean_minimal(self, ctx: "_SeedContext") -> None:
        self._vendor(ctx, "APFlow Demo Supplier Ltd.", "DEMO-TAX-0001")
        self._purchase_order(ctx, "PO-DEMO-1001", "APFlow Demo Supplier Ltd.", 1170)

    def _seed_ap_manager_demo(self, ctx: "_SeedContext") -> None:
        self._seed_clean_minimal(ctx)
        self._invoice(
            ctx,
            "AP-DEMO-REVIEW-100",
            supplier="APFlow Demo Supplier Ltd.",
            tax_id="DEMO-TAX-0001",
            subtotal=1000,
            tax_total=170,
            grand_total=1170,
            po_number="PO-DEMO-1001",
            approval_status=ApprovalTaskStatus.PENDING,
            workflow_state="approval_required",
        )
        self._review_task(ctx, "AP-DEMO-REVIEW-100")
        self._invoice(
            ctx,
            "AP-DEMO-DISCOUNT-200",
            supplier="APFlow Demo Supplier Ltd.",
            tax_id="DEMO-TAX-0001",
            subtotal=15527.06,
            tax_total=0,
            shipping_amount=159.52,
            discount_total=31.05,
            grand_total=15655.53,
            approval_status=ApprovalTaskStatus.APPROVED,
            workflow_state="approval_ready",
            line_description="Discounted invoice example",
        )
        exported = self._invoice(
            ctx,
            "AP-DEMO-EXPORTED-300",
            supplier="APFlow Demo Supplier Ltd.",
            tax_id="DEMO-TAX-0001",
            subtotal=800,
            tax_total=136,
            grand_total=936,
            approval_status=ApprovalTaskStatus.APPROVED,
            workflow_state="exported",
        )
        self.repository.store_erp_sync_log(
            ERPSyncLog(
                tenant_id=ctx.tenant_id,
                adapter_type=ERPAdapterType.PRIORITY,
                operation=ERPOperation.EXPORT_INVOICE,
                status=ERPSyncStatus.SUCCESS,
                records_processed=1,
                external_id="MOCK-ERP-AP-DEMO-EXPORTED-300",
                invoice_id=exported.invoice_id,
                metadata={"seed_profile": "ap_manager_demo", "mode": "mock"},
            )
        )
        ctx.count("erp_exports")
        self._invoice(
            ctx,
            "AP-DEMO-BLOCKED-400",
            supplier="APFlow Demo Supplier Ltd.",
            tax_id="DEMO-TAX-0001",
            subtotal=2000,
            tax_total=340,
            grand_total=2340,
            approval_status=ApprovalTaskStatus.BLOCKED,
            workflow_state="blocked",
            route=ApprovalRoute.BLOCKED,
            reason="Seeded blocker: missing purchase order requires AP review.",
            po_number=None,
        )

    def _seed_vendor_self_service_demo(self, ctx: "_SeedContext") -> None:
        vendor = self._vendor(ctx, "SuperStore", "SUP-VAT-40100")
        invoices = [
            self._invoice(ctx, "40100", supplier="SuperStore", tax_id="SUP-VAT-40100", subtotal=104.31, tax_total=0, shipping_amount=8.22, grand_total=112.53, approval_status=ApprovalTaskStatus.APPROVED, workflow_state="approval_ready"),
            self._invoice(ctx, "40101", supplier="SuperStore", tax_id="SUP-VAT-40100", subtotal=250, tax_total=42.5, grand_total=292.5, approval_status=ApprovalTaskStatus.APPROVED, workflow_state="approval_ready"),
            self._invoice(ctx, "40102", supplier="SuperStore", tax_id="SUP-VAT-40100", subtotal=90, tax_total=15.3, grand_total=105.3, approval_status=ApprovalTaskStatus.ON_HOLD, workflow_state="blocked"),
        ]
        statuses = [PaymentStatusValue.SCHEDULED, PaymentStatusValue.PAID, PaymentStatusValue.DISPUTED]
        for invoice, status in zip(invoices, statuses, strict=True):
            self._payment(ctx, invoice.invoice_id, status, amount_due=invoice.canonical_invoice.grand_total)
        self._vendor_access(ctx, vendor, "superstore-ap@example.local")
        self._audit(ctx.tenant_id, ctx.actor_id, "vendor.chat_question_answered", {"intent": "invoice_payment_status", "seed_profile": "vendor_self_service_demo"})
        self._audit(ctx.tenant_id, ctx.actor_id, "vendor.chat_question_refused", {"intent": "unsupported_or_unsafe", "seed_profile": "vendor_self_service_demo"})
        ctx.count("vendor_chat_events", 2)

    def _seed_priority_connector_demo(self, ctx: "_SeedContext") -> None:
        mapping = _sample_priority_mapping()
        config = self.repository.get_erp_connection_config(ctx.tenant_id)
        self.repository.set_erp_connection_config(
            config.model_copy(update={"config": config_with_priority_mapping(config.config, mapping)})
        )
        ctx.count("priority_mappings")
        vendor = self._vendor(ctx, "Demo Office Supplies Ltd.", "DEMO-TAX-999999999")
        po = self._purchase_order(ctx, "PO-240001", "Demo Office Supplies Ltd.", 1170)
        self.repository.link_external_vendor_id(ctx.tenant_id, vendor.vendor_id, "SUP-1001")
        self.repository.link_external_purchase_order_id(ctx.tenant_id, po.purchase_order_id, "PO-240001")
        ctx.count("priority_imported_vendors")
        ctx.count("priority_imported_purchase_orders")
        self._audit(ctx.tenant_id, ctx.actor_id, "priority.import_completed", {"seed_profile": "priority_connector_demo", "priority_writes": "disabled"})

    def _seed_compliance_demo(self, ctx: "_SeedContext") -> None:
        self._invoice(ctx, "COMP-GENERIC-READY", supplier="Compliance Ready Ltd.", tax_id="VAT-IL-123456789", subtotal=1000, tax_total=170, grand_total=1170, approval_status=ApprovalTaskStatus.PENDING, workflow_state="approval_required")
        self._invoice(ctx, "COMP-MISSING-TAX", supplier="Missing Tax Supplier", tax_id=None, subtotal=750, tax_total=127.5, grand_total=877.5, approval_status=ApprovalTaskStatus.PENDING, workflow_state="approval_required")
        self._invoice(ctx, "COMP-VAT-WARNING", supplier="VAT Warning Supplier", tax_id="VAT-000", subtotal=500, tax_total=0, grand_total=500, approval_status=ApprovalTaskStatus.PENDING, workflow_state="approval_required")
        ctx.warnings.append("Buyer identifiers are not captured in the current invoice model, so buyer tax ID checks appear as recommended missing fields.")

    def _seed_analytics_rich_demo(self, ctx: "_SeedContext") -> None:
        self._seed_ap_manager_demo(ctx)
        self._seed_vendor_self_service_demo(ctx)
        self._seed_priority_connector_demo(ctx)
        self._seed_compliance_demo(ctx)
        delivery = self.repository.store_notification_delivery(
            tenant_id=ctx.tenant_id,
            event_type="demo_seed_notification",
            channel=NotificationChannel.MOCK,
            provider="mock",
            recipient_type=NotificationRecipientType.INTERNAL_USER,
            recipient_label="AP Manager",
            status=NotificationDeliveryStatus.SENT,
            subject="Demo notification",
            body_preview="Analytics-rich demo notification",
            delivered_at=datetime.now(UTC),
        )
        ctx.count("notification_deliveries")
        for event_type in (
            UsageEventType.INVOICE_UPLOADED,
            UsageEventType.OCR_EXTRACTION_ATTEMPTED,
            UsageEventType.INVOICE_PROCESSED,
            UsageEventType.INVOICE_APPROVED,
            UsageEventType.ERP_EXPORT_MOCKED,
            UsageEventType.PAYMENT_STATUS_UPDATED,
            UsageEventType.VENDOR_CHATBOT_QUESTION_ANSWERED,
            UsageEventType.NOTIFICATION_MOCK_SENT,
            UsageEventType.ANALYTICS_VIEWED,
        ):
            self.repository.create_usage_event(
                ctx.tenant_id,
                event_type,
                source=UsageEventSource.SYSTEM,
                related_notification_delivery_id=delivery.id if event_type == UsageEventType.NOTIFICATION_MOCK_SENT else None,
                metadata={"seed_profile": "analytics_rich_demo"},
            )
        ctx.count("usage_events", 9)

    def _invoice(
        self,
        ctx: "_SeedContext",
        invoice_number: str,
        *,
        supplier: str,
        tax_id: str | None,
        subtotal: float,
        tax_total: float,
        grand_total: float,
        approval_status: ApprovalTaskStatus,
        workflow_state: str,
        shipping_amount: float = 0,
        discount_total: float = 0,
        fee_total: float = 0,
        route: ApprovalRoute = ApprovalRoute.MANAGER_APPROVAL,
        reason: str = "Seeded demo invoice.",
        po_number: str | None = "PO-DEMO-1001",
        line_description: str = "Seeded invoice line",
    ) -> InvoiceNormalizationOutput:
        vendor = self._vendor(ctx, supplier, tax_id)
        invoice = InvoiceNormalizationOutput(
            tenant_id=ctx.tenant_id,
            canonical_invoice=CanonicalInvoice(
                invoice_number=invoice_number,
                supplier_name=supplier,
                supplier_tax_id=tax_id,
                invoice_date="2026-05-16",
                due_date="2026-06-15",
                currency="USD",
                subtotal=subtotal,
                tax_total=tax_total,
                shipping_amount=shipping_amount,
                fee_total=fee_total,
                discount_total=discount_total,
                grand_total=grand_total,
                po_number=po_number,
                line_items=[
                    InvoiceLineItem(
                        description=line_description,
                        quantity=1,
                        unit_price=subtotal,
                        tax_amount=tax_total,
                        total=grand_total,
                        po_number=po_number,
                    )
                ],
            ),
            file_checksum=f"seed-{invoice_number}",
        )
        self.repository.store_invoice(invoice)
        self.repository.update_invoice_vendor(ctx.tenant_id, invoice.invoice_id, vendor.vendor_id)
        self.repository.create_approval_task(
            tenant_id=ctx.tenant_id,
            invoice_id=invoice.invoice_id,
            route=route,
            assigned_role="ap_admin" if route == ApprovalRoute.BLOCKED else "finance_manager",
            status=approval_status,
            reason=reason,
        )
        self.repository.store_notification_event(
            tenant_id=ctx.tenant_id,
            notification_id=uuid4(),
            invoice_id=invoice.invoice_id,
            notification_type=NotificationType.APPROVAL_REQUIRED if approval_status == ApprovalTaskStatus.PENDING else NotificationType.APPROVAL_DECISION_RECORDED,
            recipient_role="finance_manager",
            status="sent",
            channel="mock",
            payload={"seed_profile": "demo_seed", "invoice_number": invoice_number},
        )
        self.repository.store_workflow_state(
            WorkflowState(
                tenant_id=ctx.tenant_id,
                workflow_id=uuid4(),
                state=workflow_state,
                status=WorkflowStatus.COMPLETED,
                current_agent="DemoSeedService",
            )
        )
        ctx.count("invoices")
        ctx.count("approval_tasks")
        return invoice

    def _review_task(self, ctx: "_SeedContext", invoice_number: str) -> None:
        invoice = next(
            (
                record
                for record in self.repository.list_invoices(ctx.tenant_id)
                if record.canonical_invoice.invoice_number == invoice_number
            ),
            None,
        )
        self.repository.store_review_task(
            HumanReviewTask(
                tenant_id=ctx.tenant_id,
                invoice_id=invoice.invoice_id if invoice else None,
                status=HumanReviewStatus.REVIEW_REQUIRED,
                issues=[
                    HumanReviewFieldIssue(field_name="invoice_number", issue_type="low_confidence", message="Seeded OCR confidence issue.", confidence=0.55),
                    HumanReviewFieldIssue(field_name="supplier_tax_id", issue_type="missing_required_field", message="Supplier tax ID needs review."),
                ],
                history=[{"action": "seeded", "profile": "ap_manager_demo"}],
            )
        )
        ctx.count("review_tasks")

    def _payment(self, ctx: "_SeedContext", invoice_id: UUID, status: PaymentStatusValue, amount_due: float) -> None:
        self.repository.upsert_payment_status(
            tenant_id=ctx.tenant_id,
            invoice_id=invoice_id,
            status=status,
            source=PaymentStatusSource.MOCK,
            amount_due=amount_due,
            amount_paid=amount_due if status == PaymentStatusValue.PAID else 0,
            currency="USD",
            scheduled_payment_date=datetime.now(UTC) + timedelta(days=14) if status == PaymentStatusValue.SCHEDULED else None,
            paid_at=datetime.now(UTC) if status == PaymentStatusValue.PAID else None,
            safe_vendor_message=_safe_payment_message(status),
        )
        ctx.count("payment_statuses")

    def _vendor_access(self, ctx: "_SeedContext", vendor: VendorRecord, email: str) -> None:
        raw_token = generate_vendor_access_token()
        record = self.repository.create_vendor_portal_access(
            tenant_id=ctx.tenant_id,
            vendor_id=vendor.vendor_id,
            email=email,
            access_token_hash=hash_vendor_access_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=30),
            token_prefix=vendor_access_token_prefix(raw_token),
            label=f"{vendor.name} demo access",
            created_by_user_id=ctx.actor_user_id,
        )
        ctx.generated_vendor_links.append(
            VendorAccessCreatedResponse(
                id=record.access_id,
                tenant_id=record.tenant_id,
                vendor_id=record.vendor_id,
                vendor_name=vendor.name,
                matching_invoice_count=sum(
                    1
                    for invoice in self.repository.list_invoices(ctx.tenant_id)
                    if invoice.vendor_id == vendor.vendor_id
                ),
                email=record.email,
                label=record.label,
                status=record.status,
                expires_at=record.expires_at,
                revoked_at=record.revoked_at,
                revoked_by_user_id=record.revoked_by_user_id,
                created_by_user_id=record.created_by_user_id,
                rotated_from_access_id=record.rotated_from_access_id,
                last_used_at=record.last_used_at,
                token_prefix=record.token_prefix,
                created_at=record.created_at,
                access_token=raw_token,
                access_url=_access_url(ctx.tenant_id, raw_token),
            )
        )
        ctx.count("vendor_access")
        self._audit(ctx.tenant_id, ctx.actor_id, "vendor.access_created", {"access_id": str(record.access_id), "token_prefix": record.token_prefix, "seed_profile": "demo_seed"})

    def _vendor(self, ctx: "_SeedContext", name: str, tax_id: str | None = None) -> VendorRecord:
        existing = next((vendor for vendor in self.repository.list_vendors(ctx.tenant_id) if vendor.name == name), None)
        if existing is not None:
            return existing
        ctx.count("vendors")
        return self.repository.add_vendor(ctx.tenant_id, name, tax_id=tax_id)

    def _purchase_order(self, ctx: "_SeedContext", po_number: str, vendor_name: str, total_amount: float):
        existing = self.repository.get_purchase_order_by_number(ctx.tenant_id, po_number)
        if existing is not None:
            return existing
        vendor = self._vendor(ctx, vendor_name)
        po = self.repository.add_purchase_order(
            tenant_id=ctx.tenant_id,
            po_number=po_number,
            vendor_id=vendor.vendor_id,
            total_amount=total_amount,
            lines=[PurchaseOrderLine(description="Seeded PO line", quantity=1, unit_price=total_amount, total=total_amount)],
        )
        ctx.count("purchase_orders")
        return po

    def _audit(self, tenant_id: UUID, actor_id: str, action: str, metadata: dict) -> None:
        self.repository.store_audit_event(
            AuditEventInput(
                tenant_id=tenant_id,
                actor_type=ActorType.USER,
                actor_id=actor_id,
                action=action,
                entity_type="tenant",
                entity_id=tenant_id,
                metadata=metadata,
                correlation_id=uuid4(),
            ),
            uuid4(),
        )

    def _next_steps(self, profile_key: str) -> list[str]:
        if profile_key == "clean_minimal":
            return ["Upload a known invoice and run OCR.", "Process, approve, export, and review Audit Trail."]
        if profile_key == "vendor_self_service_demo":
            return ["Open the one-time vendor link.", "Ask a safe payment-status chatbot question.", "Revoke or rotate vendor access after the demo."]
        if profile_key == "priority_connector_demo":
            return ["Open Priority ERP Mapping.", "Validate mapping, run sample preview, and confirm no Priority data is changed."]
        if profile_key == "compliance_demo":
            return ["Open E-Invoicing Compliance.", "Compare Generic B2B, Israel Basic, and EU VAT Basic profile results."]
        if profile_key == "analytics_rich_demo":
            return ["Open Accuracy & Exceptions.", "Open Usage & Plan.", "Review Audit Trail for seeded activity."]
        return ["Open AP Workflow Guide.", "Walk through review, approval, export, and audit proof."]


@dataclass
class _SeedContext:
    tenant_id: UUID
    actor_id: str
    actor_user_id: UUID | None
    created_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    generated_vendor_links: list[VendorAccessCreatedResponse] = field(default_factory=list)

    def count(self, key: str, amount: int = 1) -> None:
        self.created_counts[key] = self.created_counts.get(key, 0) + amount


def _safe_payment_message(status: PaymentStatusValue) -> str:
    if status == PaymentStatusValue.PAID:
        return "Payment is marked as paid."
    if status == PaymentStatusValue.SCHEDULED:
        return "Payment is scheduled by AP."
    if status == PaymentStatusValue.DISPUTED:
        return "Payment is under AP review."
    return "Payment status is available in APFlow."


def _sample_priority_mapping() -> PriorityMappingConfig:
    return PriorityMappingConfig(
        version="1",
        vendors=PriorityEntityMapping(
            entity_name="SUPPLIERS",
            external_id_field="SUPNAME",
            fields={"name": "SUPDES", "tax_id": "VATNUM", "email": "EMAIL", "payment_terms": "PAYCODE"},
        ),
        purchase_orders=PriorityEntityMapping(
            entity_name="PORDERS",
            external_id_field="ORDNAME",
            fields={
                "po_number": "ORDNAME",
                "vendor_external_id": "SUPNAME",
                "status": "ORDSTATUSDES",
                "total_amount": "TOTPRICE",
                "currency": "CODE",
            },
        ),
        invoice_export=PriorityEntityMapping(
            entity_name="APINVOICES",
            external_id_field="IVNUM",
            fields={
                "invoice_number": "IVNUM",
                "invoice_date": "IVDATE",
                "vendor_external_id": "SUPNAME",
                "total_amount": "TOTPRICE",
                "currency": "CODE",
                "description": "DETAILS",
            },
        ),
    )


def _access_url(tenant_id: UUID, raw_token: str) -> str | None:
    if not settings.public_app_url:
        return None
    return f"{settings.public_app_url.rstrip('/')}/vendor?tenant_id={tenant_id}&access_token={raw_token}"
