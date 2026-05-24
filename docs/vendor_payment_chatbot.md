# Vendor Payment-Status Chatbot

APFlow includes a deterministic vendor payment-status chatbot MVP. It is rules-based and retrieval-only; it does not call OpenAI, Anthropic, or any external LLM provider.

## What It Answers

The chatbot can answer vendor-safe questions about invoices visible through the current vendor access token:

- Current invoice status.
- Payment status for a specific invoice.
- Whether an invoice is marked as paid.
- Scheduled payment date when available.
- Pending invoices.
- Paid invoices.
- Disputed invoices.
- Help and example questions.

Example safe questions:

- `What is the status of invoice 40100?`
- `Has invoice 40100 been paid?`
- `When is payment scheduled?`
- `Which invoices are pending?`
- `Do I have any disputed invoices?`

## Safety Rules

- A valid vendor access token is required.
- Expired, revoked, rotated, or invalid tokens are denied.
- The chatbot can only use invoices visible to that vendor access.
- Cross-vendor invoice lookups return a safe not-found answer.
- Answers are generated only from vendor-safe invoice and payment-status projections.
- Raw tokens and token hashes are never returned.

The chatbot refuses unsafe/internal questions, including fraud score, risk score, duplicate internals, audit logs, approval policy, internal approver names, ERP config/logs, tenant internals, internal payment notes, raw payment references, or token details.

Safe refusal:

`I can only answer vendor-safe invoice and payment-status questions. For anything else, please contact AP team.`

## Audit Events

APFlow records safe audit events for:

- `vendor.chat_question_answered`
- `vendor.chat_question_refused`

Audit metadata includes intent, matched invoice count, refusal state, and refusal reason. It does not include raw tokens or token hashes.

## Current Limits

- No external LLM.
- No real email, Slack, or Teams delivery.
- No real ERP payment-status sync yet.
- No legal or financial certainty beyond the payment status available in APFlow.

Future work should add production escalation ownership, abuse controls, and real notification handoff before broad supplier rollout.
