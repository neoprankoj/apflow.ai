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

When `OCR_PROVIDER=azure` is selected but credentials are missing, `/ready` reports the OCR check as degraded/not ready. Mock mode remains ready when Azure is unconfigured.

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

`POST /documents/invoices/{document_id}/extract?tenant_id={uuid}` retrieves the stored document bytes, runs the selected OCR provider, and returns OCR extraction, confidence summary, and review status.

`POST /documents/invoices/{document_id}/process` accepts:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111"
}
```

It runs OCR extraction and then continues through the existing full pipeline. The response contains the uploaded document, extraction result, full pipeline result, review status, and workflow status.

ERP endpoints use mock adapters only. A minimal ERP request is:

```json
{
  "tenant_id": "11111111-1111-1111-1111-111111111111",
  "adapter_type": "priority"
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

Vendor invoice responses expose only invoice identifiers, supplier name, dates, currency, total, vendor-safe status, public message, missing-information field names, and mocked payment status when available.

Vendor-safe statuses are `received`, `under_review`, `needs_information`, `approved`, `scheduled_for_payment`, `paid`, and `rejected`.
