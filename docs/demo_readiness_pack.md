# Demo Readiness Pack

Use this pack before a private APFlow AI staging demo. It consolidates the operator checklist, AP manager walkthrough, Priority connector walkthrough, and common recovery notes.
Use [production_readiness_checklist.md](production_readiness_checklist.md) and the Admin Product Readiness Gate when you need to explain why APFlow is demo ready but not yet pilot or production ready.

## A. Demo Purpose

APFlow demonstrates a complete AP manager workflow:

- Upload a supplier invoice.
- Extract invoice fields with OCR.space.
- Review and correct missing or weak fields.
- Process the invoice through validation, duplicate checks, PO/risk/approval routing.
- Approve, reject, or hold invoices in Approval Inbox.
- Show a vendor-safe preview without internal risk or audit details.
- Show secure vendor access creation, rotation, revocation, and one-time token handling.
- Show the rules-based vendor payment-status chatbot and safe refusal behavior.
- Export approved invoices to mock ERP.
- Show manual/mock payment status tracking and vendor-safe payment messages.
- Prove activity in Audit Trail.
- Preview Priority ERP mapping, dry-run sync, import plans, controlled APFlow-side imports, and imported records.

What is real today:

- FastAPI backend, Next.js dashboard, PostgreSQL persistence, auth/RBAC, document upload, OCR.space extraction, review/corrections, approvals, audit events, vendor-safe preview, manual/mock payment status tracking, vendor payment-status chatbot, controlled APFlow-side Priority imports, and runtime verification.
- Vendor access lifecycle foundation: hashed tokens, one-time raw token display, expiration, revocation, rotation, last-used tracking, and audit events.

What is mock or safe by design:

- ERP export writes to mock ERP only.
- Priority mode is mock on staging unless explicitly changed by operations.
- Priority sample preview and import plan are deterministic and safe.
- Controlled Priority import writes selected vendor/PO records into APFlow only.

Intentionally disabled or deferred:

- Real Priority writes.
- Real ERP/bank payment status sync.
- Real vendor invitation email delivery.
- Domain and HTTPS.
- Public production access.
- Demo reset unless explicitly enabled for controlled cleanup.

## B. Demo Environment

- Staging currently uses the public IP URL; domain and HTTPS are intentionally deferred.
- Auth is enabled; use Demo Login for the demo tenant.
- Demo mode is enabled for private staging convenience.
- OCR provider is `ocr_space`.
- OCR.space engine `2` is currently recommended on staging.
- OCR fallback support exists after PR #49.
- Priority mode should remain `mock`.
- Priority real read-only fetch is disabled unless an operator intentionally enables it.
- Priority writes must remain disabled.
- `.env.staging` exists only on the VPS and must never be committed.

## C. Pre-Demo Checklist

- [ ] Confirm the latest intended staging commit is deployed.
- [ ] Confirm Docker services are healthy.
- [ ] Confirm `/health` returns OK.
- [ ] Confirm `/ready` returns ready.
- [ ] Confirm `/ocr/test-provider?provider_name=ocr_space` reports configured and OK.
- [ ] Confirm Demo Login succeeds.
- [ ] Confirm Tenant Session shows Demo Owner / owner / API ready.
- [ ] Confirm `ALLOW_DEMO_RESET=false` unless a reset is intentionally being performed.
- [ ] Confirm mock ERP export works on an approval-ready invoice.
- [ ] Confirm Priority mode is mock.
- [ ] Confirm Priority writes are disabled.
- [ ] Confirm no secrets, OCR keys, or `.env.staging` changes are committed.
- [ ] Keep one known working real PDF available for the upload/OCR path.

## D. AP Manager Walkthrough

1. Open the staging dashboard.
2. Click Demo Login.
3. Show Tenant Session: Demo Owner, owner role, API ready.
4. Show AP Workflow Guide and explain Upload -> OCR -> Review -> Process -> Approve -> Export -> Audit.
5. Show Next Recommended Action and explain it points to the current safest next step.
6. Upload a known working invoice PDF.
7. Click Extract OCR.
8. Show extracted invoice fields, confidence, parsed text preview, provider status, and any engine/fallback diagnostics.
9. If review is required, correct highlighted fields and click Submit Corrections.
10. Click Run Process.
11. Show the workflow timeline and explain validation, duplicate checks, PO matching, risk, approval, and ERP readiness.
12. Open Approval Inbox.
13. Select the processed invoice and show readable invoice details.
14. Approve the invoice.
15. Confirm the approval message explains the next action.
16. Open Vendor-safe preview and confirm internal fraud/risk details are hidden.
17. Open Vendor Access Management and show that supplier access tokens are one-time, revocable, and rotatable.
18. Open the generated `/vendor` link and confirm it shows only that supplier's vendor-safe invoice/payment status, or a safe empty state if no invoices match.
19. Ask the vendor chatbot a safe payment-status question and an unsafe fraud/risk question.
20. Export to mock ERP.
21. Confirm the export success message and external mock ERP ID.
22. Open Payment Status.
23. Run Mock Payment Sync and explain it updates APFlow only.
24. Open Vendor-safe preview and show the safe payment message.
25. Open Audit Trail.
26. Show approval/export/payment/vendor access/chatbot events as proof of what happened.

Avoid saying that mock ERP export is a real ERP write. Say: "This proves the export handoff path using the mock adapter; real ERP write enablement is intentionally gated."

## E. Priority Connector Walkthrough

1. Open Admin -> Priority ERP Mapping.
2. Show Priority Real Connection Readiness.
3. Explain staging is in mock mode, read-only fetch is disabled, and writes are disabled.
4. Load or reset to the sample mapping if needed.
5. Click Validate.
6. Explain that sample Priority entity and field names must be verified for each customer.
7. Keep source set to Sample records.
8. Click Preview Vendor Sync and show mapped vendor rows.
9. Click Generate Vendor Import Plan and show would_create / would_update / would_skip / would_conflict.
10. Select one importable vendor, type `IMPORT_SELECTED`, and import selected vendor.
11. Confirm Imported Vendors shows Priority source, external ID, APFlow ID, and last import result.
12. Click Preview Purchase Orders and show mapped PO rows.
13. Click Generate Purchase Order Import Plan.
14. Select one importable PO, type `IMPORT_SELECTED`, and import selected PO.
15. Confirm Imported Purchase Orders shows Priority source, external ID or PO number, APFlow ID, and last import result.
16. Open Audit Trail and show Priority import events.
17. Say clearly: "No Priority data was changed. This controlled import wrote selected records into APFlow only."

## F. Safety Explanations

- Mock ERP export does not write to a real ERP.
- Mock payment sync does not call a bank, payment provider, or real ERP payment API.
- Controlled Priority import writes only selected records into APFlow's database.
- Priority writes remain disabled by default.
- Priority real read-only fetch is gated and GET-only when enabled.
- Demo reset should be disabled after use.
- Domain and HTTPS are deferred until real AP-user access and final security hardening are ready.
- Do not paste credentials, API keys, bearer tokens, or invoice PII into public tickets, docs, or chat.

## G. OCR Troubleshooting

- `OCR_SPACE_ENGINE=2` is currently recommended on staging.
- Engine 3 previously returned OCR.space `E580` for at least one valid PDF.
- PR #49 added engine fallback support.
- `E501` or `invalid_file_signature` means the uploaded bytes are not a real PDF/image.
- A fake PDF may be plain text saved with a `.pdf` extension.
- A real PDF should begin with `%PDF-`.
- Valid PNG and JPG files are checked by file signature before OCR.space is called.
- Docker environment changes require recreating the API container, not only a normal restart:

```powershell
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging up -d --force-recreate api
```

- Do not paste OCR.space keys into docs, logs, chat, or screenshots.

## H. Common Demo Issues And Fixes

Demo reset fails with disabled message:

- Cause: `ALLOW_DEMO_RESET=false`.
- Fix: Enable it only for controlled staging cleanup, recreate/restart API, reset, set it back to false, and recreate/restart API again.

OCR shows invalid file signature:

- Cause: The file bytes are not a real PDF, PNG, or JPG.
- Fix: Re-download the original invoice or export it as a real PDF/image.

OCR engine failure:

- Cause: OCR.space engine returned `E580`.
- Fix: Use engine 2 on staging or keep fallback engine enabled.

API is ready but frontend looks stale:

- Cause: Browser cache or stale frontend container.
- Fix: Hard refresh the browser; if needed, rebuild/recreate web.

MinIO container conflict:

- Cause: Old local container or volume state.
- Fix: Check `docker compose ps`, logs, and volume names before deleting anything.

Docker env change not reloaded:

- Cause: Container was restarted without recreation.
- Fix: Use `up -d --force-recreate api` after `.env.staging` edits.

Runtime verifier returns `review_required`:

- Context: This can be a safe outcome when OCR data is incomplete or an invalid synthetic file is used. Check `provider_error_code`, `provider_error_message`, and `review_required_fields`.

Browser cache or stale UI:

- Fix: Hard refresh, sign out/in, and confirm the deployed commit in the runbook checks.

## I. Post-Demo Checklist

- [ ] Confirm `ALLOW_DEMO_RESET=false`.
- [ ] Confirm Priority writes are disabled.
- [ ] Confirm Priority mode is still mock unless deliberately changed.
- [ ] Confirm no secrets were exposed in screenshots, logs, chat, or docs.
- [ ] Confirm `/health` and `/ready` are OK.
- [ ] Confirm Audit Trail has expected demo events.
- [ ] Confirm no unexpected 500 errors occurred.
- [ ] Keep the known working invoice sample private if it contains real data.
