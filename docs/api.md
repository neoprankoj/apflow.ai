# API

Initial endpoints:

- `GET /health`
- `GET /ready`
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

`GET /ocr/providers` returns provider status objects by default, including `configured`, `status`, and `selected`. Use `GET /ocr/providers?include_status=false` for the legacy provider-name list.

When `AUTH_ENABLED=true`, protected endpoints require `Authorization: Bearer {token}`. Missing or invalid auth returns `401`; valid users without the required permission receive `403`. Demo/local mode keeps existing unauthenticated requests available when `AUTH_ENABLED=false`.

Phase 7 permissions gate sensitive routes:

- ERP config requires `erp:configure`.
- ERP sync requires `erp:sync`.
- ERP invoice export requires `invoice:export_erp`.
- Review correction/approve/reject requires `review:correct`.
- Audit event reads require `audit:read`.
- Tenant admin routes require `tenant:admin`.

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

`POST /documents/invoices/{document_id}/extract?tenant_id={uuid}` retrieves the stored document bytes, runs the selected OCR provider, and returns OCR extraction, confidence summary, and review status. OCR.space extraction results include safe diagnostics under `ocr_result.provider_metadata` and `ocr_result.raw_response`, including `parsed_result_count`, `parsed_text_length`, `ocr_exit_code`, `detected_content_type`, `sent_file_name`, `sent_filetype`, `sent_content_type`, `provider_error_message`, and a truncated `ocr_text_preview`. The response never includes provider credentials.

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
- `POST /erp/priority/sync-preview`
- `POST /erp/priority/sync-preview/vendors`
- `POST /erp/priority/sync-preview/purchase-orders`
- `POST /erp/priority/import-plan`
- `POST /erp/priority/import-plan/vendors`
- `POST /erp/priority/import-plan/purchase-orders`
- `POST /erp/priority/import`
- `POST /erp/priority/import/vendors`
- `POST /erp/priority/import/purchase-orders`

Validation is structural unless live Priority metadata is available. Priority sync preview is read-only and imports no records; mock mode uses deterministic sample Priority-like rows by default. Real mode can run an explicitly requested, GET-only Priority OData preview only when `PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=true`, credentials are configured, and tenant mapping exists. Vendor and PO sync return `mapping_required` until the relevant tenant mapping exists. Real invoice export builds a payload preview and returns `write_disabled` while `PRIORITY_ERP_ENABLE_WRITES=false`. A minimal ERP request is:

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
