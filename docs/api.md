# API

Initial endpoints:

- `GET /health`
- `GET /ready`
- `GET /ready/product`
- `POST /auth/register-demo-tenant`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `GET /admin/tenants/current`
- `GET /admin/users`
- `POST /admin/users`
- `PATCH /admin/users/{user_id}/role`
- `DELETE /admin/users/{user_id}`
- `GET /admin/permissions`
- `POST /workflow/events`
- `POST /invoices/mock-pipeline`
- `POST /invoices/full-mock-pipeline`
- `GET /invoices?tenant_id={uuid}`
- `GET /invoices/approval-tasks?tenant_id={uuid}`
- `GET /invoices/notification-events?tenant_id={uuid}`
- `GET /invoices/purchase-orders?tenant_id={uuid}`
- `GET /invoices/workflows?tenant_id={uuid}`
- `GET /invoices/audit-events?tenant_id={uuid}`
- `GET /invoices/{invoice_id}?tenant_id={uuid}`
- `POST /invoices/{invoice_id}/approval-decision`
- `POST /documents/invoices/upload`
- `GET /documents/invoices?tenant_id={uuid}`
- `GET /documents/invoices/{document_id}?tenant_id={uuid}`
- `POST /documents/invoices/{document_id}/extract?tenant_id={uuid}`
- `POST /documents/invoices/{document_id}/process`
- `GET /erp/adapters`
- `POST /erp/config`
- `POST /erp/test-connection`
- `POST /erp/sync-vendors`
- `POST /erp/sync-purchase-orders`
- `POST /erp/export-invoice`
- `POST /erp/update-invoice-status`
- `POST /erp/sync-payment-status`
- `GET /erp/sync-logs?tenant_id={uuid}`
- `GET /payments/statuses?tenant_id={uuid}`
- `GET /payments/statuses/{payment_status_id}?tenant_id={uuid}`
- `PATCH /payments/statuses/{payment_status_id}?tenant_id={uuid}`
- `POST /payments/sync/mock`
- `GET /payments/summary?tenant_id={uuid}`
- `GET /ocr/providers`
- `GET /ocr/test-provider?provider_name=mock`
- `POST /ocr/test-provider?provider_name=mock`
- `POST /ocr/extract`
- `GET /review/tasks?tenant_id={uuid}`
- `GET /review/tasks/{task_id}?tenant_id={uuid}`
- `POST /review/tasks/{task_id}/corrections`
- `POST /review/tasks/{task_id}/approve?tenant_id={uuid}`
- `POST /review/tasks/{task_id}/reject?tenant_id={uuid}`
- `POST /vendor/access`
- `GET /vendor/invoices?tenant_id={uuid}`
- `GET /vendor/invoices/{invoice_id}?tenant_id={uuid}`
- `GET /vendor/preview/invoices/{invoice_id}?tenant_id={uuid}`
- `POST /vendor/messages`
- `POST /vendor/chat`
- `GET /vendor/messages?tenant_id={uuid}`

`POST /workflow/events` accepts the `WorkflowEventInput` schema and returns an `OrchestratorOutput` with the next agent task.

`GET /ready` returns database, OCR provider, document storage, ERP adapter registry, repository mode, auth mode, demo mode, and environment checks. It is intended for container readiness checks.

`GET /ready/product` requires tenant-admin access and returns safe Demo/Pilot/Production readiness levels, categorized checks, blockers, warnings, and next steps. It is a read-only operator endpoint; it does not change runtime behavior, call external services, or expose secrets/raw environment values.

`GET /ocr/providers` returns provider status objects by default, including `configured`, `status`, and `selected`. Use `GET /ocr/providers?include_status=false` for the legacy provider-name list.

When `AUTH_ENABLED=true`, protected endpoints require `Authorization: Bearer {token}`. Missing or invalid auth returns `401`; valid users without the required permission receive `403`. Demo/local mode keeps existing unauthenticated requests available when `AUTH_ENABLED=false`.

Phase 7 permissions gate sensitive routes:

- ERP config requires `erp:configure`.
- ERP sync requires `erp:sync`.
- ERP invoice export requires `invoice:export_erp`.
- Review correction/approve/reject requires `review:correct`.
- Audit event reads require `audit:read`.
- Tenant admin routes require `tenant:admin`.
- Payment status reads require `invoice:read`.
- Payment status updates and mock payment sync require `invoice:process`.

`POST /invoices/mock-pipeline` runs the Phase 2 deterministic mock flow:
ingest, extract, normalize, supplier match, validate, and duplicate score.

`POST /invoices/full-mock-pipeline` runs the Phase 3 deterministic mock flow:
ingest, extract, normalize, supplier match, validate, duplicate score, PO match, fraud risk score, approval route, and mock notifications.

The full mock pipeline response contains:

- `invoice`
- `validation_result`
- `duplicate_result`
- `po_match_result`
- `fraud_risk_result`
- `approval_result`
- `notifications`
- `workflow_status`
- `erp_export_ready`
- `ocr_result`
- `confidence_summary`
- `review_status`
- `review_tasks`

The list endpoints return tenant-scoped repository records and are used by the Next.js dashboard shell.

If OCR confidence requires review, the full pipeline returns `workflow_status=review_required` before validation, approval, or ERP export.

Azure OCR can be checked with `GET /ocr/test-provider?provider_name=azure`. Missing endpoint/key returns `status=missing_credentials` without logging secrets or calling Azure.

OCR.space can be checked with `GET /ocr/test-provider?provider_name=ocr_space`. Missing `OCR_SPACE_API_KEY` returns `status=missing_credentials`. The test-provider endpoint only checks configuration and does not submit documents to OCR.space.

When `OCR_PROVIDER=azure` or `OCR_PROVIDER=ocr_space` is selected but credentials are missing, `/ready` reports the OCR check as degraded/not ready. Mock mode remains ready when cloud OCR providers are unconfigured.

## Invoice Document Uploads

`POST /documents/invoices/upload` accepts multipart form data:

- `tenant_id`: tenant UUID
- `uploaded_by`: optional uploader label
- `file`: PDF, PNG, or JPEG invoice document

Unsupported file types return `415`. Files larger than `MAX_INVOICE_UPLOAD_BYTES` return `413`. When `AUTH_ENABLED=true`, upload, extraction, and processing require `invoice:process`; list and detail reads require `invoice:read`.

Upload returns tenant-scoped document metadata plus a storage reference:

```json
{
  "document": {
    "document_id": "00000000-0000-0000-0000-000000000000",
    "tenant_id": "11111111-1111-1111-1111-111111111111",
    "original_file_name": "invoice.pdf",
    "content_type": "application/pdf",
    "size_bytes": 12345,
    "storage_provider": "memory",
    "storage_key": "11111111-1111-1111-1111-111111111111/...",
    "uploaded_by": "ap@example.com",
    "created_at": "2026-05-06T00:00:00Z"
  },
  "document_reference": {
    "document_id": "00000000-0000-0000-0000-000000000000",
    "tenant_id": "11111111-1111-1111-1111-111111111111",
    "storage_provider": "memory",
    "storage_key": "11111111-1111-1111-1111-111111111111/...",
    "content_type": "application/pdf"
  }
}
```

`POST /documents/invoices/{document_id}/extract?tenant_id={uuid}` retrieves the stored document bytes, runs the selected OCR provider, and returns OCR extraction, confidence summary, and review status. OCR.space extraction results include safe diagnostics under `ocr_result.provider_metadata` and `ocr_result.raw_response`, including `parsed_result_count`, `parsed_text_length`, `ocr_exit_code`, `detected_content_type`, `sent_file_name`, `sent_filetype`, `sent_content_type`, `provider_error_code`, `provider_error_message`, `engine_used`, `fallback_engine`, `fallback_used`, and a truncated `ocr_text_preview`. Invalid file signatures are caught before OCR.space calls and returned as controlled OCR review/error results. The response never includes provider credentials.

`POST /documents/invoices/{document_id}/process` accepts:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111"
}
```

It runs OCR extraction and then continues through the existing full pipeline. If a corrected human review task exists for the uploaded document, corrected fields are applied before validation and approval routing. The response contains the uploaded document, extraction result, full pipeline result, review status, and workflow status.

ERP endpoints default to mock adapters. Priority also exposes an experimental real-connector foundation when `PRIORITY_ERP_MODE=real`. In that mode, `POST /erp/test-connection` returns safe diagnostics in `details`, while tenant-specific mappings can be managed with:

- `GET /erp/priority/mapping?tenant_id={uuid}`
- `PUT /erp/priority/mapping`
- `POST /erp/priority/validate-mapping`
- `GET /erp/priority/readiness?tenant_id={uuid}&check_remote=false`
- `POST /erp/priority/sync-preview`
- `POST /erp/priority/sync-preview/vendors`
- `POST /erp/priority/sync-preview/purchase-orders`
- `POST /erp/priority/import-plan`
- `POST /erp/priority/import-plan/vendors`
- `POST /erp/priority/import-plan/purchase-orders`
- `POST /erp/priority/import`
- `POST /erp/priority/import/vendors`
- `POST /erp/priority/import/purchase-orders`

Validation is structural unless live Priority metadata is available. `GET /erp/priority/readiness` returns a safe real-credentials checklist without secrets. With `check_remote=true`, it performs GET-only service-root and `$metadata` checks only when Priority real mode, credentials, base URL, and `PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=true` are present. Priority sync preview is read-only and imports no records; mock mode uses deterministic sample Priority-like rows by default. Real mode can run an explicitly requested, GET-only Priority OData preview only when `PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=true`, credentials are configured, and tenant mapping exists. Vendor and PO sync return `mapping_required` until the relevant tenant mapping exists. Real invoice export builds a payload preview and returns `write_disabled` while `PRIORITY_ERP_ENABLE_WRITES=false`. A minimal ERP request is:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "adapter_type": "priority"
}
```

Example Priority sync preview request:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "kind": "vendors",
  "source": "sample",
  "limit": 10
}
```

Preview responses include status, source (`sample` or `priority`), mapping status, limited raw records, mapped records, warnings, and the message `No data was imported.` Use `source=priority` only for the explicit real read-only path. If the gate is disabled or config is missing, the response returns safe statuses such as `read_only_fetch_disabled`, `real_mode_required`, `missing_credentials`, `unauthorized`, `entity_not_found`, or `invalid_response`. Viewers cannot run previews when auth is enabled.

Example Priority readiness request:

```http
GET /erp/priority/readiness?tenant_id=11111111-1111-1111-1111-111111111111&check_remote=true
```

Readiness responses include mode, read-only fetch state, write state, local config booleans, service-root/metadata availability, checklist rows, warnings, and errors. They never include username, password, API key, auth headers, raw metadata, or entity data.

Example Priority import plan request:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "kind": "purchase_orders",
  "source": "sample",
  "limit": 10
}
```

Import plan responses compare the mapped preview rows against existing APFlow vendors or purchase orders and return `would_create`, `would_update`, `would_skip`, and `would_conflict` counts and items. This is planning only: no APFlow records are imported, no Priority records are changed, and no sync/audit events are created for the preview. Import plans default to `source=sample`; `source=priority` uses the same read-only fetch gate and never silently falls back to sample records. Viewers cannot generate import plans when auth is enabled.

Example controlled Priority import request:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "kind": "vendors",
  "selected_external_ids": ["SUP-1001"],
  "confirmation": "IMPORT_SELECTED",
  "allow_creates": true,
  "allow_updates": false
}
```

Controlled import regenerates the server-side plan, imports only selected `would_create` or `would_update` rows into APFlow, and never writes to Priority. Conflicts are blocked, unchanged rows are skipped, and updates require `allow_updates=true`. Purchase-order imports require the referenced vendor external ID to already be linked in APFlow, so vendor import should usually run first. Successful and blocked imports create tenant-scoped audit events.

Imported Priority records can be inspected without calling Priority or mutating APFlow:

- `GET /erp/priority/imported/vendors?tenant_id={uuid}`
- `GET /erp/priority/imported/purchase-orders?tenant_id={uuid}`

These read-only endpoints require `erp:read`, enforce tenant scope, and return APFlow IDs, Priority external IDs, source adapter, import flag, and best-effort last import action/timestamp derived from external references and audit events. Records without Priority external references are returned safely with `imported_from_priority=false`.

## Payment Status

Payment status endpoints are internal APFlow APIs for manual/mock invoice payment lifecycle tracking. They do not call banks, payment processors, or real ERP payment APIs.

`GET /payments/statuses?tenant_id={uuid}` lists tenant-scoped payment statuses. Optional filters are `invoice_id` and `status`.

`GET /payments/summary?tenant_id={uuid}` returns totals by status plus latest updates.

`PATCH /payments/statuses/{payment_status_id}?tenant_id={uuid}` updates a status manually:

```json
{
  "status": "paid",
  "amount_paid": 1170.0,
  "safe_vendor_message": "Payment has been marked as paid.",
  "internal_note": "Internal AP note"
}
```

`internal_note` is returned only through internal APIs and must never appear in vendor-safe responses.

`POST /payments/sync/mock` creates or updates deterministic demo payment statuses:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "mode": "mock",
  "invoice_id": "00000000-0000-0000-0000-000000000000"
}
```

Mock sync records audit events and changes APFlow payment-status records only. It does not contact Priority, a bank, or any payment provider.

## Vendor Access

Vendor access endpoints create and manage tokenized supplier self-service access. Raw tokens are shown only in create/rotate responses and are never returned by list/read endpoints.

- `POST /vendor/accesses` creates access for a vendor/supplier. Requires an AP manager/admin-style ERP sync permission.
- `GET /vendor/accesses?tenant_id={uuid}` lists access records without raw tokens or token hashes.
- `GET /vendor/accesses/{access_id}?tenant_id={uuid}` reads one access record without raw token or token hash.
- `POST /vendor/accesses/{access_id}/revoke?tenant_id={uuid}` revokes an access token.
- `POST /vendor/accesses/{access_id}/rotate?tenant_id={uuid}` revokes the old token and returns one replacement token.
- Created/rotated responses include an `access_url` when `PUBLIC_APP_URL` is configured. The browser route is `/vendor?tenant_id={uuid}&access_token={token}`.

Example create request:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "vendor_name": "Northstar Components",
  "email": "ap@northstar.example",
  "label": "Northstar supplier portal access",
  "ttl_days": 30
}
```

Vendor-facing endpoints continue to use `X-Vendor-Access-Token` or `access_token` query parameters. Tokens must be active, unexpired, and scoped to the invoice vendor. Vendor responses include only safe invoice and payment-status fields.

Supplier matching is intentionally conservative: APFlow matches invoices by vendor ID first, then by exact normalized supplier name so values like `SuperStore` and `Super Store` can resolve when OCR/demo data created separate vendor rows. Broad fuzzy matching is not used.

If the token is valid but no invoices match the supplier, `GET /vendor/invoices` returns an empty list and the frontend vendor page explains that no vendor-visible invoices are available yet.

`POST /vendor/chat` is a rules-based vendor payment-status chatbot endpoint. It accepts a vendor token by header, query string, or request body and answers only from vendor-safe invoice/payment data:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "access_token": "shown-once-token",
  "question": "When is payment scheduled?",
  "invoice_number": "40100"
}
```

Responses include `answer`, `intent`, `confidence`, `matched_invoice_ids`, `matched_invoices`, `safe_suggestions`, `refused`, and optional `refusal_reason`. Unsafe questions about fraud/risk, audit, approval policy, ERP config/logs, internal notes, tenant internals, or token details are refused safely.

## Notifications

Notification delivery endpoints are authenticated and tenant-scoped.

- `GET /notifications/providers?tenant_id={uuid}` returns safe provider readiness for mock, email, Slack, and Teams.
- `POST /notifications/test` records a mock test delivery or a safe not-configured placeholder result.
- `GET /notifications/deliveries?tenant_id={uuid}` lists tenant delivery attempts with optional filters for status, channel, event type, and invoice.
- `GET /notifications/summary?tenant_id={uuid}` returns counts by status/channel and recent deliveries.

The mock provider records delivery attempts inside APFlow only. Email, Slack, and Teams are placeholders and do not send externally. Responses redact recipient addresses, truncate body previews, and never include provider secrets, webhook URLs, auth headers, or API keys.

Example Priority mapping payload:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "mapping": {
    "vendors": {
      "entity_name": "SUPPLIERS",
      "external_id_field": "SUPNAME",
      "fields": {
        "name": "SUPDES",
        "tax_id": "VATNUM",
        "email": "EMAIL",
        "payment_terms": "PAYCODE"
      }
    },
    "purchase_orders": {
      "entity_name": "PORDERS",
      "external_id_field": "ORDNAME",
      "fields": {
        "po_number": "ORDNAME",
        "vendor_external_id": "SUPNAME",
        "status": "ORDSTATUSDES",
        "total_amount": "TOTPRICE",
        "currency": "CODE"
      }
    },
    "invoice_export": {
      "entity_name": "APINVOICES",
      "external_id_field": "IVNUM",
      "fields": {
        "invoice_number": "IVNUM",
        "invoice_date": "IVDATE",
        "vendor_external_id": "SUPNAME",
        "total_amount": "TOTPRICE",
        "currency": "CODE"
      }
    }
  }
}
```

Invoice export requires `invoice_id` and should be called only after the invoice is approval-ready or auto-approved:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "adapter_type": "priority",
  "invoice_id": "00000000-0000-0000-0000-000000000000"
}
```

Example payload:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "source": "upload",
  "file_url": "mock://incoming/invoice.pdf",
  "metadata": {
    "sender_email": "ap@example.com",
    "original_filename": "invoice.pdf",
    "mime_type": "application/pdf"
  },
  "content": "invoice_number=INV-1 supplier_name=Northstar Components supplier_tax_id=TAX-12345 subtotal=1000 tax_total=170 grand_total=1170 currency=USD invoice_date=2026-05-05 po_number=PO-100"
}
```

Vendor endpoints require `X-Vendor-Access-Token` or an `access_token` query value except `POST /vendor/access`, which creates a demo/dev portal token. The returned token is shown once; only its hash is stored.

`POST /invoices/{invoice_id}/approval-decision` requires `invoice:approve` and accepts `approve`, `reject`, or `hold`. It updates the latest approval task, records audit and notification events, and returns whether the invoice is now ERP-export-ready.

`GET /vendor/preview/invoices/{invoice_id}?tenant_id={uuid}` is an internal authenticated preview endpoint. It returns the same vendor-safe projection shown in the portal without exposing internal risk, audit, or ERP details.

Vendor invoice responses expose only invoice identifiers, supplier name, dates, currency, total, vendor-safe status, public message, missing-information field names, and mocked payment status when available.

Vendor-safe statuses are `received`, `under_review`, `needs_information`, `approved`, `scheduled_for_payment`, `paid`, and `rejected`.
