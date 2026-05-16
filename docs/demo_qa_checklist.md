# Demo QA Checklist

## Pre-Demo

- [ ] `/health` returns `ok`.
- [ ] `/ready` returns `ready`.
- [ ] Expected `OCR_PROVIDER` is selected.
- [ ] Demo reset is disabled unless intentionally enabled for cleanup.
- [ ] Runtime verifier passes for the target environment.
- [ ] No real invoices, keys, tokens, or `.env` files are staged for commit.

## Auth

- [ ] Demo login succeeds.
- [ ] Tenant Session shows `Demo Owner`.
- [ ] Tenant Session shows the expected tenant.
- [ ] Tenant Session shows `owner` role.
- [ ] Unauthenticated protected calls return `401`.
- [ ] Unauthorized role actions return `403`.

## Upload

- [ ] Synthetic PDF upload succeeds.
- [ ] Unsupported upload type is rejected safely.
- [ ] Uploaded document metadata appears in the dashboard.
- [ ] Upload controls stay disabled before sign-in.

## OCR

- [ ] Extract does not return `500`.
- [ ] OCR provider status appears.
- [ ] OCR diagnostics appear.
- [ ] Extracted fields render when available.
- [ ] OCR text preview appears for review/debug scenarios.
- [ ] `review_required` displays as a safe state, not a failure.

## Review And Correction

- [ ] Missing or weak required fields are visible.
- [ ] Correction fields prefill extracted values where available.
- [ ] Corrections can be submitted.
- [ ] Success copy says corrections were saved.
- [ ] Process uses corrected fields.

## Process

- [ ] Workflow timeline advances after processing.
- [ ] Approval-ready scenario reaches `approval_ready`.
- [ ] Review-required scenario remains safely blocked before approval.
- [ ] Invoice summary shows invoice, vendor, total, OCR confidence, workflow, PO match, risk, and approval route.

## ERP Export

- [ ] ERP export is disabled until `erp_export_ready=true`.
- [ ] Approval-ready invoice exports to mock ERP.
- [ ] External invoice ID appears.
- [ ] Recent ERP sync result appears.

## Approval Inbox

- [ ] Approval Inbox shows blocked, held, rejected, and approval-ready invoices.
- [ ] `inbox-demo` seed mode creates ready, blocked, on-hold, rejected, duplicate-like, and review-required examples without OCR.
- [ ] Duplicate invoice numbers remain distinguishable by invoice ID suffix.
- [ ] Needs action, blocked, on hold, rejected, approval ready, high risk, and missing PO filters work.
- [ ] Blocked invoice detail shows blocker reason, PO state, risk, and vendor-safe preview.
- [ ] Owner/admin/approver can approve, reject, and hold an eligible invoice from the inbox.
- [ ] Approval-ready invoice can be exported from the inbox.
- [ ] Rejected invoices do not expose invalid approval actions.

## Vendor Portal

- [ ] Vendor preview is available for a linked invoice.
- [ ] Vendor-safe status is shown.
- [ ] Internal risk reasons are hidden.
- [ ] Audit events are hidden.
- [ ] ERP sync internals are hidden.
- [ ] Vendor chatbot answers only allowed invoice/payment questions.

## Reset

- [ ] Reset disabled message is clear when `ALLOW_DEMO_RESET=false`.
- [ ] Reset requires owner/admin.
- [ ] Reset clears invoices, review tasks, workflow states, approval tasks, notifications, uploaded documents, ERP logs, vendor messages, and vendor access artifacts when enabled.
- [ ] Reset preserves tenant, users, memberships, base vendor fixtures, PO fixtures, and approval policy.
- [ ] Clean reset returns `Demo data reset successfully.`

## Failure Modes

- [ ] API unavailable state is visible.
- [ ] Unauthorized/session-expired state is visible.
- [ ] Upload failure state is visible.
- [ ] OCR failure state is visible.
- [ ] ERP export failure state is visible.
- [ ] Vendor access failure state is visible.

## Restart And Backup

- [ ] API/web restart preserves persisted data.
- [ ] PostgreSQL backup file is non-empty.
- [ ] Destructive restore is not run during a demo unless explicitly intended.

## Security

- [ ] `.env.staging` is not modified or committed.
- [ ] Synthetic demo assets contain no real vendor, tax, bank, customer, or payment data.
- [ ] Logs and screenshots do not expose secrets.
- [ ] Internal service ports remain firewalled on staging.
