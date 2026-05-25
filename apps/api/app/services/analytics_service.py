from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    AccuracyAnalyticsResponse,
    AnalyticsBreakdownItem,
    AnalyticsExceptionItem,
    AnalyticsMetric,
    ApprovalTaskStatus,
    ERPOperation,
    ERPSyncStatus,
    NotificationDeliveryStatus,
    PaymentStatusValue,
)


class AnalyticsService:
    def __init__(self, repository: InMemoryAPRepository) -> None:
        self.repository = repository

    def accuracy_exception_dashboard(self, tenant_id: UUID) -> AccuracyAnalyticsResponse:
        invoices = self.repository.list_invoices(tenant_id)
        review_tasks = self.repository.list_review_tasks(tenant_id)
        approval_tasks = self.repository.list_approval_tasks(tenant_id)
        audit_events = self.repository.list_audit_events(tenant_id)
        erp_logs = self.repository.list_erp_sync_logs(tenant_id)
        payment_statuses = self.repository.list_payment_statuses(tenant_id)
        vendor_accesses = self.repository.list_vendor_portal_access(tenant_id)
        notification_deliveries = self.repository.list_notification_deliveries(tenant_id)

        total_invoices = len(invoices)
        review_required_ids = {
            task.invoice_id
            for task in review_tasks
            if task.invoice_id is not None and str(task.status) in {"review_required", "in_review"}
        }
        corrected_count = sum(1 for event in audit_events if event.action == "review.corrected")
        approval_counter = Counter(str(task.status) for task in approval_tasks)
        exported_count = sum(
            1
            for log in erp_logs
            if log.operation == ERPOperation.EXPORT_INVOICE and log.status == ERPSyncStatus.SUCCESS
        )
        export_failure_count = sum(
            1
            for log in erp_logs
            if log.operation == ERPOperation.EXPORT_INVOICE and log.status == ERPSyncStatus.FAILED
        )
        ocr_failures = [
            event
            for event in audit_events
            if str(event.metadata.get("provider_error_code") or "").strip()
            or str(event.metadata.get("provider_error_message") or "").strip()
        ]
        invalid_file_count = sum(
            1
            for event in ocr_failures
            if "invalid" in str(event.metadata.get("provider_error_code") or event.metadata.get("provider_error_message")).casefold()
        )
        validation_blockers = self._count_audit_mentions(audit_events, ("grand total", "validation", "mismatch"))
        missing_po = self._count_audit_mentions(audit_events, ("missing_po", "missing po"))
        duplicate_flags = sum(1 for event in audit_events if event.action == "invoice.duplicate_scored") + sum(
            1 for event in self.repository.list_notification_events(tenant_id) if str(event.notification_type) == "duplicate_detected"
        )
        blocked_invoices = approval_counter.get(str(ApprovalTaskStatus.BLOCKED), 0) + sum(
            1 for event in self.repository.list_notification_events(tenant_id) if str(event.notification_type) == "invoice_blocked"
        )
        payment_counter = Counter(str(status.status) for status in payment_statuses)
        active_access = sum(1 for access in vendor_accesses if access.status == "active")
        used_access = sum(1 for access in vendor_accesses if access.last_used_at is not None)
        vendor_chat_answered = sum(1 for event in audit_events if event.action == "vendor.chat_question_answered")
        vendor_chat_refused = sum(1 for event in audit_events if event.action == "vendor.chat_question_refused")
        vendor_preview_views = sum(1 for event in audit_events if event.action == "vendor.invoice_preview_viewed")
        notification_counter = Counter(str(delivery.status) for delivery in notification_deliveries)
        placeholder_notifications = sum(
            1
            for delivery in notification_deliveries
            if str(delivery.channel) in {"email", "slack", "teams"}
        )

        review_rate = _percentage(len(review_required_ids), total_invoices)
        export_success_rate = _percentage(exported_count, exported_count + export_failure_count)

        exceptions = [
            _exception("blocked_invoices", "Blocked invoices", blocked_invoices, "high", "Open Approval Inbox and resolve blocked invoices."),
            _exception("review_required", "Review-required invoices", len(review_required_ids), "medium", "Correct required fields and run Process again."),
            _exception("ocr_failures", "OCR/provider failures", len(ocr_failures), "high", "Check OCR provider diagnostics and upload original PDF/PNG/JPG files."),
            _exception("invalid_files", "Invalid invoice files", invalid_file_count, "medium", "Ask users to upload original invoice PDFs/images."),
            _exception("missing_po", "Missing PO flags", missing_po, "medium", "Import/sync purchase orders or approve exceptions manually."),
            _exception("duplicate_flags", "Duplicate/risk flags", duplicate_flags, "medium", "Review duplicate warnings before export."),
            _exception("validation_blockers", "Validation blockers", validation_blockers, "medium", "Review total/component mismatch details."),
        ]
        exceptions = [item for item in exceptions if item.count > 0]

        return AccuracyAnalyticsResponse(
            tenant_id=tenant_id,
            generated_at=datetime.now(UTC),
            date_range=_date_range(invoices),
            invoice_volume=[
                _metric("total_invoices", "Total invoices", total_invoices, "neutral", "Invoices captured for this tenant."),
                _metric("processed_invoices", "Processed invoices", total_invoices, "neutral", "Invoices with normalized APFlow records."),
                _metric("approved_invoices", "Approved invoices", approval_counter.get(str(ApprovalTaskStatus.APPROVED), 0) + approval_counter.get(str(ApprovalTaskStatus.AUTO_APPROVED), 0), "good"),
                _metric("rejected_invoices", "Rejected invoices", approval_counter.get(str(ApprovalTaskStatus.REJECTED), 0), "warning"),
                _metric("held_invoices", "On-hold invoices", approval_counter.get(str(ApprovalTaskStatus.ON_HOLD), 0), "warning"),
                _metric("exported_invoices", "ERP exports", exported_count, "good", "Successful mock ERP exports."),
            ],
            ocr_accuracy=[
                _metric("ocr_attempts", "OCR/audit extraction attempts", sum(1 for event in audit_events if event.action == "invoice.extracted"), "neutral"),
                _metric("ocr_failures", "OCR failures", len(ocr_failures), "critical" if ocr_failures else "good"),
                _metric("invalid_files", "Invalid files", invalid_file_count, "warning" if invalid_file_count else "good"),
                _metric("review_required_rate", "Review-required rate", review_rate, _rate_status(review_rate, 30, 60), unit="%"),
            ],
            review_workload=[
                _metric("review_required", "Review required", len(review_required_ids), "warning" if review_required_ids else "good"),
                _metric("corrections_submitted", "Corrections submitted", corrected_count, "neutral"),
                _metric("open_review_tasks", "Open review tasks", sum(1 for task in review_tasks if str(task.status) in {"review_required", "in_review"}), "warning"),
            ],
            approval_health=[
                _metric("pending_approvals", "Pending approvals", approval_counter.get(str(ApprovalTaskStatus.PENDING), 0), "warning"),
                _metric("approved", "Approved", approval_counter.get(str(ApprovalTaskStatus.APPROVED), 0), "good"),
                _metric("rejected", "Rejected", approval_counter.get(str(ApprovalTaskStatus.REJECTED), 0), "warning"),
                _metric("on_hold", "On hold", approval_counter.get(str(ApprovalTaskStatus.ON_HOLD), 0), "warning"),
            ],
            exception_breakdown=exceptions,
            erp_export_health=[
                _metric("mock_export_success", "Mock ERP export success", exported_count, "good" if exported_count else "neutral"),
                _metric("export_failures", "ERP export failures", export_failure_count, "critical" if export_failure_count else "good"),
                _metric("export_success_rate", "Export success rate", export_success_rate, _rate_status(100 - export_success_rate, 10, 30), unit="%"),
                _metric("priority_writes", "Priority writes", 0, "good", "Real Priority writes remain disabled."),
            ],
            payment_status_health=_payment_breakdown(payment_counter, len(payment_statuses)),
            vendor_self_service=[
                _metric("active_vendor_access", "Active vendor links", active_access, "neutral"),
                _metric("used_vendor_access", "Used vendor links", used_access, "good" if used_access else "neutral"),
                _metric("vendor_preview_views", "Vendor preview views", vendor_preview_views, "neutral"),
                _metric("chatbot_answered", "Chatbot answers", vendor_chat_answered, "good" if vendor_chat_answered else "neutral"),
                _metric("chatbot_refused", "Chatbot refusals", vendor_chat_refused, "warning" if vendor_chat_refused else "good"),
            ],
            notification_health=[
                _metric("notification_deliveries", "Notification deliveries", len(notification_deliveries), "neutral"),
                _metric("mock_notifications_sent", "Mock notifications sent", notification_counter.get(str(NotificationDeliveryStatus.SENT), 0), "good"),
                _metric("failed_notifications", "Failed notifications", notification_counter.get(str(NotificationDeliveryStatus.FAILED), 0), "critical"),
                _metric("disabled_notifications", "Disabled/placeholders", notification_counter.get(str(NotificationDeliveryStatus.DISABLED), 0), "warning"),
                _metric("placeholder_channels", "Email/Slack/Teams placeholders", placeholder_notifications, "warning" if placeholder_notifications else "neutral"),
            ],
            top_blockers=sorted(exceptions, key=lambda item: (-item.count, item.severity))[:5],
            recommendations=self._recommendations(
                review_rate=review_rate,
                invalid_file_count=invalid_file_count,
                missing_payments=len(payment_statuses) == 0 and total_invoices > 0,
                unused_vendor_access=active_access > 0 and used_access == 0,
                real_notifications_missing=True,
                blocked_invoices=blocked_invoices,
            ),
        )

    def _count_audit_mentions(self, events, terms: tuple[str, ...]) -> int:
        count = 0
        for event in events:
            haystack = f"{event.action} {event.metadata}".casefold()
            if any(term in haystack for term in terms):
                count += 1
        return count

    def _recommendations(
        self,
        *,
        review_rate: float,
        invalid_file_count: int,
        missing_payments: bool,
        unused_vendor_access: bool,
        real_notifications_missing: bool,
        blocked_invoices: int,
    ) -> list[str]:
        recommendations: list[str] = []
        if review_rate >= 30:
            recommendations.append("Review OCR mappings and recurring supplier templates to reduce manual review.")
        if invalid_file_count:
            recommendations.append("Ask users to upload original PDFs/images instead of renamed text files or screenshots.")
        if blocked_invoices:
            recommendations.append("Open Approval Inbox and resolve blocked invoices before ERP export.")
        if missing_payments:
            recommendations.append("Run mock payment sync now; connect read-only ERP payment sync before pilot use.")
        if unused_vendor_access:
            recommendations.append("Share vendor links only after domain/HTTPS and support ownership are ready.")
        if real_notifications_missing:
            recommendations.append("Configure real notification providers before pilot approval chasing or supplier invitations.")
        if not recommendations:
            recommendations.append("Keep processing invoices and reviewing Audit Trail to build operational history.")
        return recommendations


def _metric(
    key: str,
    label: str,
    value: float | int,
    status: str,
    description: str | None = None,
    unit: str | None = None,
) -> AnalyticsMetric:
    return AnalyticsMetric(key=key, label=label, value=value, status=status, description=description, unit=unit)


def _exception(key: str, label: str, count: int, severity: str, next_step: str) -> AnalyticsExceptionItem:
    return AnalyticsExceptionItem(key=key, label=label, count=count, severity=severity, next_step=next_step)


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0
    return round((numerator / denominator) * 100, 1)


def _rate_status(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return "good"


def _payment_breakdown(counter: Counter, total: int) -> list[AnalyticsBreakdownItem]:
    statuses = [
        PaymentStatusValue.NOT_STARTED,
        PaymentStatusValue.PENDING,
        PaymentStatusValue.SCHEDULED,
        PaymentStatusValue.PARTIALLY_PAID,
        PaymentStatusValue.PAID,
        PaymentStatusValue.FAILED,
        PaymentStatusValue.DISPUTED,
        PaymentStatusValue.CANCELLED,
        PaymentStatusValue.UNKNOWN,
    ]
    return [
        AnalyticsBreakdownItem(
            key=str(status),
            label=str(status).replace("_", " ").title(),
            count=counter.get(str(status), 0),
            percentage=_percentage(counter.get(str(status), 0), total),
        )
        for status in statuses
        if counter.get(str(status), 0) > 0 or total == 0
    ]


def _date_range(invoices) -> dict[str, str | None]:
    dates = sorted(invoice.canonical_invoice.invoice_date for invoice in invoices if invoice.canonical_invoice.invoice_date)
    return {"start": dates[0] if dates else None, "end": dates[-1] if dates else None}
