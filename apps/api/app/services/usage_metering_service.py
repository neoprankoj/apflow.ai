from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    TenantUsageSummary,
    UsageEventRead,
    UsageEventSource,
    UsageEventType,
    UsageMetricRead,
    UsageMetricStatus,
    UsageOveragePolicy,
    UsagePlanRead,
)


MAX_METADATA_VALUE_LENGTH = 120


PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "demo": {
        "monthly_invoice_limit": 50,
        "monthly_ocr_limit": 100,
        "monthly_vendor_access_limit": 25,
        "monthly_chatbot_question_limit": 100,
        "monthly_notification_limit": 250,
    },
    "starter": {
        "monthly_invoice_limit": 500,
        "monthly_ocr_limit": 1000,
        "monthly_vendor_access_limit": 100,
        "monthly_chatbot_question_limit": 1000,
        "monthly_notification_limit": 2500,
    },
    "growth": {
        "monthly_invoice_limit": 2500,
        "monthly_ocr_limit": 5000,
        "monthly_vendor_access_limit": 500,
        "monthly_chatbot_question_limit": 5000,
        "monthly_notification_limit": 12500,
    },
    "enterprise": {
        "monthly_invoice_limit": None,
        "monthly_ocr_limit": None,
        "monthly_vendor_access_limit": None,
        "monthly_chatbot_question_limit": None,
        "monthly_notification_limit": None,
    },
}


PLAN_LABELS = {
    "demo": ("Demo", "Private staging/demo plan. Warn-only limits; no real billing provider is connected."),
    "starter": ("Starter", "Future small-team commercial plan placeholder."),
    "growth": ("Growth", "Future higher-volume AP operations plan placeholder."),
    "enterprise": ("Enterprise", "Future custom limits and support plan placeholder."),
}


EVENT_CATEGORIES: dict[UsageEventType, str] = {
    UsageEventType.INVOICE_UPLOADED: "invoices",
    UsageEventType.INVOICE_PROCESSED: "invoices",
    UsageEventType.OCR_EXTRACTION_ATTEMPTED: "ocr",
    UsageEventType.OCR_EXTRACTION_SUCCEEDED: "ocr",
    UsageEventType.OCR_EXTRACTION_FAILED: "ocr",
    UsageEventType.REVIEW_CORRECTION_SUBMITTED: "review",
    UsageEventType.INVOICE_APPROVED: "approvals",
    UsageEventType.INVOICE_REJECTED: "approvals",
    UsageEventType.INVOICE_HELD: "approvals",
    UsageEventType.ERP_EXPORT_MOCKED: "erp",
    UsageEventType.PAYMENT_STATUS_UPDATED: "payments",
    UsageEventType.PAYMENT_MOCK_SYNC_RUN: "payments",
    UsageEventType.VENDOR_ACCESS_CREATED: "vendor",
    UsageEventType.VENDOR_ACCESS_USED: "vendor",
    UsageEventType.VENDOR_CHATBOT_QUESTION_ANSWERED: "chatbot",
    UsageEventType.VENDOR_CHATBOT_QUESTION_REFUSED: "chatbot",
    UsageEventType.NOTIFICATION_MOCK_SENT: "notifications",
    UsageEventType.ANALYTICS_VIEWED: "analytics",
    UsageEventType.MANUAL_TEST: "manual",
}


class UsageMeteringService:
    def __init__(self, repository: InMemoryAPRepository) -> None:
        self.repository = repository

    def record_usage_event(
        self,
        tenant_id: UUID,
        event_type: UsageEventType,
        *,
        source: UsageEventSource = UsageEventSource.SYSTEM,
        quantity: int = 1,
        unit: str = "event",
        related_invoice_id: UUID | None = None,
        related_document_id: UUID | None = None,
        related_vendor_access_id: UUID | None = None,
        related_payment_status_id: UUID | None = None,
        related_notification_delivery_id: UUID | None = None,
        metadata: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> UsageEventRead | None:
        try:
            return self.repository.create_usage_event(
                tenant_id,
                event_type,
                source=source,
                quantity=quantity,
                unit=unit,
                related_invoice_id=related_invoice_id,
                related_document_id=related_document_id,
                related_vendor_access_id=related_vendor_access_id,
                related_payment_status_id=related_payment_status_id,
                related_notification_delivery_id=related_notification_delivery_id,
                metadata=_safe_metadata(metadata),
                occurred_at=occurred_at,
            )
        except Exception:
            return None

    def list_events(
        self,
        tenant_id: UUID,
        *,
        event_type: str | None = None,
        source: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        related_invoice_id: UUID | None = None,
    ) -> list[UsageEventRead]:
        return self.repository.list_usage_events(
            tenant_id,
            event_type=event_type,
            source=source,
            date_from=date_from,
            date_to=date_to,
            related_invoice_id=related_invoice_id,
        )

    def available_plans(self, *, current_plan_key: str = "demo") -> list[UsagePlanRead]:
        plans: list[UsagePlanRead] = []
        for plan_key, limits in PLAN_LIMITS.items():
            label, description = PLAN_LABELS[plan_key]
            plans.append(
                UsagePlanRead(
                    plan_key=plan_key,
                    label=label,
                    description=description,
                    overage_policy=UsageOveragePolicy.WARN_ONLY if plan_key != "enterprise" else UsageOveragePolicy.FUTURE_BILLING,
                    is_current=plan_key == current_plan_key,
                    **limits,
                )
            )
        return plans

    def current_plan_for_tenant(self, tenant_id: UUID) -> UsagePlanRead:
        tenant = self.repository.get_tenant(tenant_id)
        plan_key = "demo"
        if tenant is not None:
            settings = getattr(tenant, "settings", {}) or {}
            plan_key = str(settings.get("usage_plan") or "demo")
        if plan_key not in PLAN_LIMITS:
            plan_key = "demo"
        return next(plan for plan in self.available_plans(current_plan_key=plan_key) if plan.plan_key == plan_key)

    def summary(self, tenant_id: UUID, period: str = "current_month") -> TenantUsageSummary:
        period_start, period_end = _period_range(period)
        events = self.list_events(tenant_id, date_from=period_start, date_to=period_end)
        usage_by_event_type = Counter()
        usage_by_category = Counter()
        for event in events:
            usage_by_event_type[str(event.event_type)] += event.quantity
            usage_by_category[EVENT_CATEGORIES.get(event.event_type, "other")] += event.quantity
        plan = self.current_plan_for_tenant(tenant_id)
        limits = _limits_for(plan, usage_by_event_type)
        warnings = [
            f"{metric.label} is at {metric.percentage}% of the warn-only {plan.label} limit."
            for metric in limits
            if metric.status == UsageMetricStatus.WARNING
        ]
        warnings.extend(
            f"{metric.label} exceeded the warn-only {plan.label} limit."
            for metric in limits
            if metric.status == UsageMetricStatus.EXCEEDED
        )
        recommendations = _recommendations(usage_by_event_type, warnings)
        return TenantUsageSummary(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            current_plan=plan,
            usage_by_event_type=dict(sorted(usage_by_event_type.items())),
            usage_by_category=dict(sorted(usage_by_category.items())),
            limits=limits,
            warnings=warnings,
            recommendations=recommendations,
            recent_events=list(reversed(events[-10:])),
        )


def _period_range(period: str) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if period != "current_month":
        return datetime(now.year, now.month, 1, tzinfo=UTC), now
    return datetime(now.year, now.month, 1, tzinfo=UTC), now


def _limits_for(plan: UsagePlanRead, event_counts: Counter) -> list[UsageMetricRead]:
    return [
        _metric(
            "invoices",
            "Invoices uploaded/processed",
            event_counts.get(str(UsageEventType.INVOICE_UPLOADED), 0)
            + event_counts.get(str(UsageEventType.INVOICE_PROCESSED), 0),
            plan.monthly_invoice_limit,
            "Uploads and process runs captured by APFlow.",
        ),
        _metric(
            "ocr",
            "OCR attempts",
            event_counts.get(str(UsageEventType.OCR_EXTRACTION_ATTEMPTED), 0),
            plan.monthly_ocr_limit,
            "OCR extraction attempts, including successful and failed attempts.",
        ),
        _metric(
            "vendor_access",
            "Vendor accesses",
            event_counts.get(str(UsageEventType.VENDOR_ACCESS_CREATED), 0),
            plan.monthly_vendor_access_limit,
            "Vendor access records created for supplier self-service.",
        ),
        _metric(
            "chatbot",
            "Chatbot questions",
            event_counts.get(str(UsageEventType.VENDOR_CHATBOT_QUESTION_ANSWERED), 0)
            + event_counts.get(str(UsageEventType.VENDOR_CHATBOT_QUESTION_REFUSED), 0),
            plan.monthly_chatbot_question_limit,
            "Vendor payment-status chatbot questions answered or refused safely.",
        ),
        _metric(
            "notifications",
            "Notifications",
            event_counts.get(str(UsageEventType.NOTIFICATION_MOCK_SENT), 0),
            plan.monthly_notification_limit,
            "Mock notification delivery attempts recorded inside APFlow.",
        ),
    ]


def _metric(key: str, label: str, used: int, limit: int | None, description: str) -> UsageMetricRead:
    if limit is None:
        return UsageMetricRead(key=key, label=label, used=used, limit=None, percentage=None, status=UsageMetricStatus.UNLIMITED, description=description)
    percentage = round((used / limit) * 100, 1) if limit else 0
    if used > limit:
        status = UsageMetricStatus.EXCEEDED
    elif percentage >= 80:
        status = UsageMetricStatus.WARNING
    else:
        status = UsageMetricStatus.OK
    return UsageMetricRead(key=key, label=label, used=used, limit=limit, percentage=percentage, status=status, description=description)


def _recommendations(event_counts: Counter, warnings: list[str]) -> list[str]:
    recommendations: list[str] = []
    if warnings:
        recommendations.append("Review plan limits before enabling real billing or customer pilots.")
    if not event_counts:
        recommendations.append("Run the AP demo flow to populate usage metrics before a pilot conversation.")
    if event_counts.get(str(UsageEventType.NOTIFICATION_MOCK_SENT), 0) == 0:
        recommendations.append("Send a mock notification to verify delivery history before configuring real providers.")
    if event_counts.get(str(UsageEventType.VENDOR_CHATBOT_QUESTION_ANSWERED), 0) == 0:
        recommendations.append("Use the vendor portal chatbot once to verify supplier self-service metering.")
    recommendations.append("Stripe or another billing provider can be connected later using these usage events.")
    return recommendations


def _safe_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    blocked_terms = ("token", "secret", "password", "api_key", "authorization", "webhook", "hash")
    safe: dict[str, str | int | float | bool | None] = {}
    for key, value in metadata.items():
        key_text = str(key)
        if any(term in key_text.casefold() for term in blocked_terms):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key_text] = value if not isinstance(value, str) else value[:MAX_METADATA_VALUE_LENGTH]
    return safe
