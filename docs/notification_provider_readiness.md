# Notification Provider Readiness

## Purpose

This document defines the configuration gate for future real notification providers in APFlow.

- Mock notifications remain the default safe provider.
- Real Email, Slack, and Microsoft Teams delivery is not enabled by default.
- This is a readiness/configuration gate only; it does not connect a real provider or send external messages.
- Domain + HTTPS, sender-domain identity, provider secrets, and test recipients must be reviewed before real delivery.
- APFlow is not production-ready from this document alone.

## Current Behavior

APFlow records mock notification deliveries inside the application. Email, Slack, and Teams remain placeholders until a later provider implementation and operations approval.

The safe readiness endpoint is:

```bash
curl -H "Authorization: Bearer <token>" "http://127.0.0.1:8000/notifications/readiness?tenant_id=<tenant-id>"
```

The response reports configured/not configured state, missing requirements, and global warnings. It must never return SMTP passwords, API keys, webhook URLs, raw secrets, or provider payloads.

## Real Delivery Gate

Real external delivery requires explicit server-side configuration:

```env
NOTIFICATION_DEFAULT_PROVIDER=mock
NOTIFICATION_REAL_DELIVERY_ENABLED=false
```

Keep `NOTIFICATION_REAL_DELIVERY_ENABLED=false` until:

- Provider secrets are stored server-side only.
- A sender domain and sender email have been selected.
- SPF, DKIM, and DMARC are planned and verified for email.
- Domain + HTTPS are configured for public vendor/customer links.
- Test recipients are approved.
- Support and incident handling ownership is clear.

## Environment Placeholders

Use `.env.example` or `.env.staging.example` as the shape reference only. Do not commit real values.

```env
NOTIFICATION_DEFAULT_PROVIDER=mock
NOTIFICATION_REAL_DELIVERY_ENABLED=false
EMAIL_PROVIDER=smtp
EMAIL_FROM_ADDRESS=
EMAIL_FROM_NAME=APFlow AI
SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
SLACK_WEBHOOK_URL=
TEAMS_WEBHOOK_URL=
```

## Email Setup Checklist

- Choose the sender domain.
- Choose the sender email address.
- Configure SPF for the selected sender provider.
- Configure DKIM for the selected sender provider.
- Configure DMARC policy and reporting.
- Store SMTP credentials server-side only.
- Approve a limited test recipient list.
- Verify no vendor links are sent over plain HTTP.
- Confirm bounced or failed email handling before customer use.

## Slack Setup Checklist

- Create an approved workspace/channel webhook.
- Store the webhook URL server-side only.
- Confirm the channel owner and support process.
- Send only test messages to an approved test channel after the real-delivery gate is enabled.
- Rotate the webhook if it is exposed.

## Microsoft Teams Setup Checklist

- Create an approved Teams incoming webhook.
- Store the webhook URL server-side only.
- Confirm the team/channel owner and support process.
- Send only test messages to an approved test channel after the real-delivery gate is enabled.
- Rotate the webhook if it is exposed.

## Test Procedure

1. Keep `NOTIFICATION_DEFAULT_PROVIDER=mock`.
2. Keep `NOTIFICATION_REAL_DELIVERY_ENABLED=false`.
3. Open Admin -> Notification Settings.
4. Confirm Real Provider Readiness shows Mock as safe and Email/Slack/Teams as blocked or not configured.
5. Send a mock test notification only.
6. Confirm the delivery history records the mock delivery.
7. Confirm no provider secret, webhook URL, or SMTP password appears in API responses, UI, audit metadata, or logs.
8. After a future approved real-provider rollout, enable delivery only in a controlled test environment with approved recipients.

## Rollback Procedure

If a real-provider rollout is attempted later and behaves unexpectedly:

1. Set `NOTIFICATION_REAL_DELIVERY_ENABLED=false`.
2. Set `NOTIFICATION_DEFAULT_PROVIDER=mock`.
3. Rotate exposed SMTP/API/webhook credentials if needed.
4. Re-run `/notifications/readiness`.
5. Send only mock tests until the issue is fixed.
6. Preserve delivery history and logs for incident review.

## What Not To Claim

- Do not claim real Email, Slack, or Teams delivery is live by default.
- Do not claim production readiness.
- Do not claim GDPR, SOC 2, ISO, or legal compliance from this gate.
- Do not claim sender-domain authentication is complete until SPF, DKIM, and DMARC are verified.
- Do not claim certified e-invoicing/tax authority submission.
- Do not use real customer/vendor notifications before Domain + HTTPS and pilot terms are approved.
