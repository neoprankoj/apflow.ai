from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    PaymentStatusRead,
    PaymentStatusSource,
    PaymentStatusSummary,
    PaymentStatusSyncRequest,
    PaymentStatusUpdate,
    PaymentStatusValue,
    UsageEventSource,
    UsageEventType,
)
from app.services.usage_metering_service import UsageMeteringService


class PaymentStatusService:
    def __init__(self, repository: InMemoryAPRepository, audit_agent: AuditLoggingAgent) -> None:
        self.repository = repository
        self.audit_agent = audit_agent

    def list_statuses(
        self,
        tenant_id: UUID,
        *,
        invoice_id: UUID | None = None,
        status: str | None = None,
    ) -> list[PaymentStatusRead]:
        return self.repository.list_payment_statuses(tenant_id, invoice_id=invoice_id, status=status)

    def get_status(self, tenant_id: UUID, payment_status_id: UUID) -> PaymentStatusRead:
        return self.repository.get_payment_status(tenant_id, payment_status_id)

    def summary(self, tenant_id: UUID) -> PaymentStatusSummary:
        return self.repository.get_payment_status_summary(tenant_id)

    def update_status(
        self,
        tenant_id: UUID,
        payment_status_id: UUID,
        update: PaymentStatusUpdate,
        context: CurrentUserContext,
    ) -> PaymentStatusRead:
        existing = self.repository.get_payment_status(tenant_id, payment_status_id)
        patched = self.repository.update_payment_status(
            tenant_id,
            payment_status_id,
            self._with_safe_message(existing, update),
            source=PaymentStatusSource.MANUAL,
            updated_by_user_id=context.user.id,
        )
        self._record_audit(
            tenant_id,
            context,
            "payment.status_updated",
            patched.invoice_id,
            {
                "payment_status_id": str(patched.id),
                "status": str(patched.status),
                "source": str(patched.source),
                "safe_vendor_message": patched.safe_vendor_message,
            },
        )
        UsageMeteringService(self.repository).record_usage_event(
            tenant_id,
            UsageEventType.PAYMENT_STATUS_UPDATED,
            source=UsageEventSource.USER,
            related_invoice_id=patched.invoice_id,
            related_payment_status_id=patched.id,
            metadata={"status": str(patched.status), "source": str(patched.source)},
        )
        return patched

    def run_mock_sync(self, request: PaymentStatusSyncRequest, context: CurrentUserContext) -> list[PaymentStatusRead]:
        if request.mode not in {"mock", "manual"}:
            raise ValueError("Payment sync mode must be mock or manual.")
        invoices = self.repository.list_invoices(request.tenant_id)
        if request.invoice_id is not None:
            invoices = [invoice for invoice in invoices if invoice.invoice_id == request.invoice_id]
            if not invoices:
                raise KeyError("invoice is outside tenant scope")
        results: list[PaymentStatusRead] = []
        for index, invoice in enumerate(invoices):
            status = request.status or self._demo_status_for(index)
            existing = self.repository.get_payment_status_by_invoice(request.tenant_id, invoice.invoice_id)
            paid_at = datetime.now(UTC) if status == PaymentStatusValue.PAID else None
            scheduled_at = datetime.now(UTC) + timedelta(days=7) if status == PaymentStatusValue.SCHEDULED else None
            amount_paid = invoice.canonical_invoice.grand_total if status == PaymentStatusValue.PAID else 0
            record = self.repository.upsert_payment_status(
                request.tenant_id,
                invoice.invoice_id,
                status=status,
                source=PaymentStatusSource.MOCK,
                amount_due=invoice.canonical_invoice.grand_total,
                amount_paid=amount_paid,
                currency=invoice.canonical_invoice.currency,
                scheduled_payment_date=scheduled_at,
                paid_at=paid_at,
                safe_vendor_message=self.safe_vendor_message(status, scheduled_at, paid_at),
                internal_note="Mock payment sync generated this demo payment status.",
                updated_by_user_id=context.user.id,
            )
            results.append(record)
            self._record_audit(
                request.tenant_id,
                context,
                "payment.status_updated" if existing else "payment.status_created",
                invoice.invoice_id,
                {
                    "payment_status_id": str(record.id),
                    "status": str(record.status),
                    "source": str(record.source),
                    "message": "Mock payment sync updated APFlow payment status only.",
                },
            )
            UsageMeteringService(self.repository).record_usage_event(
                request.tenant_id,
                UsageEventType.PAYMENT_STATUS_UPDATED,
                source=UsageEventSource.MOCK,
                related_invoice_id=invoice.invoice_id,
                related_payment_status_id=record.id,
                metadata={"status": str(record.status), "source": str(record.source)},
            )
        self._record_audit(
            request.tenant_id,
            context,
            "payment.mock_sync_run",
            request.invoice_id or request.tenant_id,
            {
                "records_processed": len(results),
                "mode": request.mode,
                "message": "Mock payment sync updated APFlow payment statuses only.",
            },
        )
        UsageMeteringService(self.repository).record_usage_event(
            request.tenant_id,
            UsageEventType.PAYMENT_MOCK_SYNC_RUN,
            source=UsageEventSource.MOCK,
            quantity=max(1, len(results)),
            related_invoice_id=request.invoice_id,
            metadata={"records_processed": len(results), "mode": request.mode},
        )
        return results

    def ensure_status_for_invoice(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        *,
        source: PaymentStatusSource = PaymentStatusSource.SYSTEM,
        status: PaymentStatusValue = PaymentStatusValue.PENDING,
    ) -> PaymentStatusRead:
        invoice = self.repository.get_invoice(tenant_id, invoice_id)
        existing = self.repository.get_payment_status_by_invoice(tenant_id, invoice_id)
        if existing is not None:
            return existing
        return self.repository.upsert_payment_status(
            tenant_id,
            invoice_id,
            status=status,
            source=source,
            amount_due=invoice.canonical_invoice.grand_total,
            amount_paid=0,
            currency=invoice.canonical_invoice.currency,
            safe_vendor_message=self.safe_vendor_message(status, None, None),
        )

    def safe_vendor_message(
        self,
        status: PaymentStatusValue | str,
        scheduled_payment_date,
        paid_at,
    ) -> str:
        value = str(status)
        if value == PaymentStatusValue.PAID:
            return "Payment has been marked as paid."
        if value == PaymentStatusValue.SCHEDULED:
            return "Payment is scheduled by AP."
        if value == PaymentStatusValue.PARTIALLY_PAID:
            return "A partial payment has been recorded."
        if value == PaymentStatusValue.FAILED:
            return "Payment could not be completed. AP is reviewing it."
        if value == PaymentStatusValue.DISPUTED:
            return "Payment is on hold while AP reviews a dispute."
        if value == PaymentStatusValue.CANCELLED:
            return "Payment was cancelled. Contact AP for next steps."
        if value == PaymentStatusValue.PENDING:
            return "Payment is pending AP processing."
        return "Payment status is not available yet."

    def _with_safe_message(self, existing: PaymentStatusRead, update: PaymentStatusUpdate) -> PaymentStatusUpdate:
        if update.safe_vendor_message:
            return update
        status = update.status or existing.status
        return PaymentStatusUpdate(
            **{
                **update.model_dump(exclude_unset=True),
                "safe_vendor_message": self.safe_vendor_message(
                    status,
                    update.scheduled_payment_date or existing.scheduled_payment_date,
                    update.paid_at or existing.paid_at,
                ),
            }
        )

    def _demo_status_for(self, index: int) -> PaymentStatusValue:
        return [PaymentStatusValue.SCHEDULED, PaymentStatusValue.PENDING, PaymentStatusValue.PAID][index % 3]

    def _record_audit(
        self,
        tenant_id: UUID,
        context: CurrentUserContext,
        action: str,
        entity_id: UUID,
        metadata: dict,
    ) -> None:
        self.audit_agent.record(
            AuditEventInput(
                tenant_id=tenant_id,
                actor_type=ActorType.USER,
                actor_id=str(context.user.id),
                action=action,
                entity_type="payment_status",
                entity_id=entity_id,
                metadata=metadata,
            )
        )
