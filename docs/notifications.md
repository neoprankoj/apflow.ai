# Notification Delivery Abstraction

APFlow has a notification delivery foundation for demo and future pilot work.

Current behavior:

- `mock` provider records delivery attempts inside APFlow only.
- `email`, `slack`, and `teams` providers are placeholders.
- Placeholder providers do not send external messages.
- Delivery history is tenant-scoped and visible from Admin Notification Settings.
- Provider readiness responses expose only safe configured/enabled status.
- Real provider readiness is documented in [Notification Provider Readiness](notification_provider_readiness.md) and does not expose SMTP passwords, API keys, or webhook URLs.
- Real external delivery remains blocked by `NOTIFICATION_REAL_DELIVERY_ENABLED=false` unless a later provider rollout explicitly changes it.

No SendGrid, SMTP, Slack, Teams, webhook, or customer messaging secrets are configured in this PR.

## Admin Flow

1. Open Admin -> Notification Settings.
2. Confirm Mock is configured and enabled.
3. Confirm Email, Slack, and Teams are not configured.
4. Send a mock test notification.
5. Confirm the delivery appears in Delivery History.
6. Try Email, Slack, or Teams and confirm APFlow records a safe not-configured result.
7. Review Real Provider Readiness and confirm Email, Slack, and Teams are blocked or not configured.
8. Open Audit Trail and confirm notification activity is readable.

## Safety Rules

- Mock notifications never leave APFlow.
- Placeholder providers never call external APIs.
- Recipient addresses are redacted in delivery responses.
- Body previews are truncated.
- Delivery metadata must not contain API keys, webhook URLs, auth headers, or tokens.
- Notification failures must not block the AP workflow.
- Sender-domain SPF, DKIM, and DMARC must be reviewed before real email delivery.
- Domain + HTTPS must be in place before external vendor/customer links are sent.

## Future Provider Path

Future real providers should implement the same service interface:

- Provider readiness with safe configured/enabled status.
- Send result mapped to `sent`, `queued`, `failed`, `skipped`, or `disabled`.
- Redacted recipient data.
- Safe delivery metadata only.
- Audit Trail event for delivery attempts.

Real provider rollout should wait for server-only secrets, sender-domain SPF/DKIM/DMARC review, provider-specific retry policy, support ownership, Domain + HTTPS, and pilot security review. Use [notification_provider_readiness.md](notification_provider_readiness.md) before changing runtime delivery behavior.
