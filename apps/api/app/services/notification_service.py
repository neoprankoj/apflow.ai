from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.agents.observability.audit_logging_agent import AuditLoggingAgent
from app.core.repositories import InMemoryAPRepository
from app.core.schemas import (
    ActorType,
    AuditEventInput,
    CurrentUserContext,
    NotificationChannel,
    NotificationDeliveryRead,
    NotificationDeliveryStatus,
    NotificationProviderRead,
    NotificationRecipientType,
    NotificationSummary,
    NotificationTestRequest,
)


MAX_PREVIEW_LENGTH = 280


@dataclass(frozen=True)
class NotificationSendPayload:
    event_type: str
    channel: NotificationChannel
    recipient_type: NotificationRecipientType
    recipient_label: str
    recipient_address: str | None = None
    subject: str | None = None
    message: str | None = None
    related_invoice_id: UUID | None = None
    related_payment_status_id: UUID | None = None
    related_vendor_access_id: UUID | None = None
    metadata: dict | None = None


class BaseNotificationProvider:
    channel: NotificationChannel
    provider: str

    def readiness(self) -> NotificationProviderRead:
        raise NotImplementedError

    def send(self, payload: NotificationSendPayload) -> tuple[NotificationDeliveryStatus, str | None, datetime | None]:
        raise NotImplementedError


class MockNotificationProvider(BaseNotificationProvider):
    channel = NotificationChannel.MOCK
    provider = "mock"

    def readiness(self) -> NotificationProviderRead:
        return NotificationProviderRead(
            provider=self.provider,
            channel=self.channel,
            configured=True,
            enabled=True,
            mode="mock",
            safe_message="Mock notifications are recorded inside APFlow only. No external message is sent.",
        )

    def send(self, payload: NotificationSendPayload) -> tuple[NotificationDeliveryStatus, str | None, datetime | None]:
        return NotificationDeliveryStatus.SENT, "Mock delivery recorded inside APFlow.", datetime.now(UTC)


class PlaceholderNotificationProvider(BaseNotificationProvider):
    def __init__(self, channel: NotificationChannel, provider: str, label: str) -> None:
        self.channel = channel
        self.provider = provider
        self.label = label

    def readiness(self) -> NotificationProviderRead:
        return NotificationProviderRead(
            provider=self.provider,
            channel=self.channel,
            configured=False,
            enabled=False,
            mode="placeholder",
            safe_message=f"{self.label} provider is not configured.",
        )

    def send(self, payload: NotificationSendPayload) -> tuple[NotificationDeliveryStatus, str | None, datetime | None]:
        return NotificationDeliveryStatus.DISABLED, f"{self.label} provider is not configured.", None


class NotificationService:
    def __init__(self, repository: InMemoryAPRepository, audit_agent: AuditLoggingAgent) -> None:
        self.repository = repository
        self.audit_agent = audit_agent
        self.providers: dict[NotificationChannel, BaseNotificationProvider] = {
            NotificationChannel.MOCK: MockNotificationProvider(),
            NotificationChannel.EMAIL: PlaceholderNotificationProvider(
                NotificationChannel.EMAIL,
                "email_placeholder",
                "Email",
            ),
            NotificationChannel.SLACK: PlaceholderNotificationProvider(
                NotificationChannel.SLACK,
                "slack_placeholder",
                "Slack",
            ),
            NotificationChannel.TEAMS: PlaceholderNotificationProvider(
                NotificationChannel.TEAMS,
                "teams_placeholder",
                "Teams",
            ),
        }

    def list_providers(self) -> list[NotificationProviderRead]:
        return [provider.readiness() for provider in self.providers.values()]

    def test_provider(self, request: NotificationTestRequest, context: CurrentUserContext) -> NotificationDeliveryRead:
        payload = NotificationSendPayload(
            event_type="notification.test",
            channel=request.channel,
            recipient_type=NotificationRecipientType.ADMIN,
            recipient_label=(request.recipient_label or context.user.full_name or context.user.email),
            recipient_address=request.recipient_address,
            subject=request.subject or "APFlow notification test",
            message=request.message or "This is a safe APFlow notification provider test.",
            metadata={"test": True},
        )
        delivery = self.send_notification(request.tenant_id, payload, context)
        self.audit_agent.record(
            AuditEventInput(
                tenant_id=request.tenant_id,
                actor_type=ActorType.USER,
                actor_id=str(context.user.id),
                action="notification.test_sent"
                if delivery.status == NotificationDeliveryStatus.SENT
                else "notification.test_not_delivered",
                entity_type="notification_delivery",
                entity_id=delivery.id,
                metadata={
                    "channel": str(delivery.channel),
                    "provider": delivery.provider,
                    "status": str(delivery.status),
                    "reason": delivery.reason,
                },
            )
        )
        return delivery

    def send_notification(
        self,
        tenant_id: UUID,
        payload: NotificationSendPayload,
        context: CurrentUserContext | None = None,
    ) -> NotificationDeliveryRead:
        provider = self.providers.get(payload.channel)
        if provider is None:
            provider = PlaceholderNotificationProvider(payload.channel, f"{payload.channel}_placeholder", str(payload.channel).title())
        status, reason, delivered_at = provider.send(payload)
        delivery = self.repository.store_notification_delivery(
            tenant_id=tenant_id,
            event_type=payload.event_type,
            channel=payload.channel,
            provider=provider.provider,
            recipient_type=payload.recipient_type,
            recipient_label=_safe_label(payload.recipient_label),
            recipient_address_redacted=_redact_address(payload.recipient_address),
            subject=_truncate(payload.subject),
            body_preview=_truncate(payload.message),
            status=status,
            reason=reason,
            related_invoice_id=payload.related_invoice_id,
            related_payment_status_id=payload.related_payment_status_id,
            related_vendor_access_id=payload.related_vendor_access_id,
            delivery_metadata=_safe_metadata(payload.metadata),
            created_by_user_id=context.user.id if context else None,
            delivered_at=delivered_at,
        )
        if context is not None:
            self.audit_agent.record(
                AuditEventInput(
                    tenant_id=tenant_id,
                    actor_type=ActorType.USER,
                    actor_id=str(context.user.id),
                    action="notification.delivery_recorded",
                    entity_type="notification_delivery",
                    entity_id=delivery.id,
                    metadata={
                        "channel": str(delivery.channel),
                        "provider": delivery.provider,
                        "status": str(delivery.status),
                        "event_type": delivery.event_type,
                    },
                )
            )
        return delivery

    def list_deliveries(
        self,
        tenant_id: UUID,
        *,
        status: str | None = None,
        channel: str | None = None,
        event_type: str | None = None,
        related_invoice_id: UUID | None = None,
    ) -> list[NotificationDeliveryRead]:
        return self.repository.list_notification_deliveries(
            tenant_id,
            status=status,
            channel=channel,
            event_type=event_type,
            related_invoice_id=related_invoice_id,
        )

    def summary(self, tenant_id: UUID) -> NotificationSummary:
        deliveries = self.list_deliveries(tenant_id)
        by_channel: dict[str, int] = {}
        for delivery in deliveries:
            by_channel[str(delivery.channel)] = by_channel.get(str(delivery.channel), 0) + 1
        return NotificationSummary(
            total=len(deliveries),
            sent=sum(delivery.status == NotificationDeliveryStatus.SENT for delivery in deliveries),
            queued=sum(delivery.status == NotificationDeliveryStatus.QUEUED for delivery in deliveries),
            failed=sum(delivery.status == NotificationDeliveryStatus.FAILED for delivery in deliveries),
            skipped=sum(delivery.status == NotificationDeliveryStatus.SKIPPED for delivery in deliveries),
            disabled=sum(delivery.status == NotificationDeliveryStatus.DISABLED for delivery in deliveries),
            by_channel=by_channel,
            latest_deliveries=list(reversed(deliveries[-5:])),
        )


def _safe_label(value: str | None) -> str:
    label = (value or "APFlow operator").strip()
    return _truncate(label, limit=120) or "APFlow operator"


def _redact_address(value: str | None) -> str | None:
    if not value:
        return None
    address = value.strip()
    if "@" in address:
        local, domain = address.split("@", 1)
        return f"{local[:2]}***@{domain}"
    if len(address) <= 6:
        return "***"
    return f"{address[:3]}***{address[-3:]}"


def _truncate(value: str | None, limit: int = MAX_PREVIEW_LENGTH) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "..."


def _safe_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    blocked = {"token", "secret", "password", "api_key", "webhook_url", "authorization"}
    return {
        str(key): value
        for key, value in metadata.items()
        if all(term not in str(key).casefold() for term in blocked)
    }
