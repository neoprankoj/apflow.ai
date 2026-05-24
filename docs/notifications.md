# Notification Delivery Abstraction

APFlow has a notification delivery foundation for demo and future pilot work.

Current behavior:

- `mock` provider records delivery attempts inside APFlow only.
- `email`, `slack`, and `teams` providers are placeholders.
- Placeholder providers do not send external messages.
- Delivery history is tenant-scoped and visible from Admin Notification Settings.
- Provider readiness responses expose only safe configured/enabled status.

No SendGrid, SMTP, Slack, Teams, webhook, or customer messaging secrets are configured in this PR.

## Admin Flow

1. Open Admin -> Notification Settings.
2. Confirm Mock is configured and enabled.
3. Confirm Email, Slack, and Teams are not configured.
4. Send a mock test notification.
5. Confirm the delivery appears in Delivery History.
6. Try Email, Slack, or Teams and confirm APFlow records a safe not-configured result.
7. Open Audit Trail and confirm notification activity is readable.

## Safety Rules

- Mock notifications never leave APFlow.
- Placeholder providers never call external APIs.
- Recipient addresses are redacted in delivery responses.
- Body previews are truncated.
- Delivery metadata must not contain API keys, webhook URLs, auth headers, or tokens.
- Notification failures must not block the AP workflow.

## Future Provider Path

Future real providers should implement the same service interface:

- Provider readiness with safe configured/enabled status.
- Send result mapped to `sent`, `queued`, `failed`, `skipped`, or `disabled`.
- Redacted recipient data.
- Safe delivery metadata only.
- Audit Trail event for delivery attempts.

Real provider rollout should wait for server-only secrets, provider-specific retry policy, support ownership, and pilot security review.
