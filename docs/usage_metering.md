# Usage Metering / Billing Foundation

APFlow now records tenant-scoped usage events for commercial readiness and operator visibility.

This is not billing. No Stripe, PayPal, Paddle, Chargebee, card storage, customer subscription lifecycle, invoices, or payment collection is connected.

## What Is Metered

- Invoice uploads.
- OCR extraction attempts, successes, and failures.
- Invoice processing.
- Review corrections.
- Approval decisions.
- Mock ERP exports.
- Payment status updates and mock payment sync.
- Vendor access creation and use.
- Vendor chatbot answered/refused questions.
- Mock notification deliveries.
- Accuracy analytics views.

Usage events are stored with safe metadata only. Raw vendor tokens, token hashes, provider secrets, auth headers, webhook URLs, OCR payloads, and sensitive message bodies must never be stored in usage metadata.

## Plans

Current plan data is static and code-defined:

- Demo
- Starter
- Growth
- Enterprise

The current tenant plan defaults to Demo. Limits are warn-only and visibility-only. APFlow does not block invoice processing, OCR, approvals, exports, vendor access, chatbot use, or notifications based on usage limits in this foundation.

## API

- `GET /usage/summary?tenant_id={uuid}&period=current_month`
- `GET /usage/events?tenant_id={uuid}`
- `GET /usage/plans?tenant_id={uuid}`
- `POST /usage/events/manual-test`

The summary endpoint returns usage by event type, usage by category, warn-only plan limits, warnings, recommendations, and recent events.

## Admin UI

The dashboard includes `Usage & Plan`.

It shows:

- Current Demo plan and warn-only policy.
- Usage cards for invoices, OCR, vendor access, chatbot questions, and notifications.
- Usage categories.
- Recent usage events.
- Static plan placeholders.
- Billing readiness notes.

The UI explicitly states that no real billing provider is connected.

## Future Path

- Add Stripe or another billing provider.
- Add customer subscription lifecycle.
- Add customer-facing invoices and payment collection.
- Add contractual plan limits and overage policy.
- Add exportable usage reports.
- Add per-tenant commercial packaging and billing contacts.

Do not connect billing until production access, domain/HTTPS, secret handling, support ownership, and customer contract terms are ready.
