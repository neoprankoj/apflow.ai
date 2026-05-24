# Payment Status Foundation

APFlow now has an internal, tenant-scoped payment status foundation for invoices. It is designed for AP manager visibility and future vendor payment-status answers.

## What Exists

- Manual/mock payment statuses for APFlow invoices.
- Payment status list, summary, manual update, and mock sync APIs.
- Dashboard Payment Status section.
- Vendor-safe payment status projection in Vendor Preview and vendor portal responses.
- Rules-based vendor payment-status chatbot using vendor-safe data only.
- Audit events for payment status creation, updates, and mock sync runs.
- Product Readiness check for the payment status foundation.

## What Is Not Connected Yet

- No bank payment provider integration.
- No real ERP payment-status polling.
- No real Priority writes.
- No vendor payment chatbot production escalation/abuse-control hardening.

## Status Values

- `not_started`
- `pending`
- `scheduled`
- `partially_paid`
- `paid`
- `failed`
- `disputed`
- `cancelled`
- `unknown`

Sources are `manual`, `mock`, `erp`, `imported`, and `system`. Current demo flows use `manual` and `mock`.

## Vendor-Safe Rules

Vendor-facing responses may show safe labels, safe messages, amount due/paid, currency, scheduled payment date, and paid date.

Vendor-facing responses must not show:

- `internal_note`
- raw ERP/payment provider payloads
- internal audit metadata
- internal user details
- internal external-payment references unless explicitly approved later

The vendor chatbot follows the same allowlist. It can answer questions about status, paid/scheduled dates, pending invoices, paid invoices, and disputed invoices. It refuses fraud, risk, audit, approval-policy, ERP, internal-note, token, and tenant questions.

## Demo Path

1. Approve or export an invoice.
2. Open `Payment Status`.
3. Run `Mock Payment Sync`.
4. Confirm payment statuses appear.
5. Update a status manually if permitted.
6. Open Vendor Preview and confirm the safe payment message appears.
7. Open the vendor link and ask `What is the status of invoice [number]?`.
8. Ask `What is my fraud score?` and confirm the chatbot refuses safely.
9. Open Audit Trail and confirm payment and vendor chatbot events are recorded.

## Future Work

The next production-facing step is real ERP payment status sync. That should remain read-only first, tenant-scoped, audited, and vendor-safe before any chatbot or vendor self-service workflow depends on it.
