# Runbook

For repeatable VPS staging deploy, backup, restore, rollback, and verification procedures, use [operations_staging.md](operations_staging.md).

## Failed Workflow Event

1. Check the workflow correlation ID in audit events.
2. Review `ErrorHandlerAgent` classification.
3. Retry transient and integration failures until `max_retries`.
4. Move persistent failures to dead-letter handling and notify AP admins.

## Missing Provider Credentials

Use mock adapters until credentials are configured through environment variables. Never hardcode credentials in source, tests, logs, or audit metadata.

## PO Match Exceptions

1. Check `po_match_result.match_status`.
2. `missing_po`, `partial_match`, `amount_variance`, and `quantity_variance` route to AP review.
3. `vendor_mismatch` is treated as a blocking risk signal.
4. Receipts are represented by a mock 3-way-ready structure; real receipt integration is deferred until ERP adapters are implemented.

## Risk And Approval Outcomes

1. Review `fraud_risk_result.reasons` before overriding an approval route.
2. `critical` risk blocks payment.
3. `high` risk blocks under the default mock policy.
4. High amount invoices route to controller approval when they exceed the manager approval limit.

## Mock Notifications

Notification events are stored locally for:

- approval required
- invoice blocked
- duplicate detected
- validation failed

No real email, Slack, Teams, or webhook delivery happens in the current phase.

## Database Migrations

1. Start PostgreSQL with Docker Compose when Docker is available.
2. Set `USE_IN_MEMORY_REPOSITORIES=false`.
3. Run `alembic -c alembic.ini upgrade head` from `apps/api`.
4. Start FastAPI and run `POST /invoices/full-mock-pipeline`.
5. Confirm invoices, approval tasks, notification events, and audit events are visible through the tenant-scoped list endpoints.

For fast local tests, keep `USE_IN_MEMORY_REPOSITORIES=true`; repository unit tests cover the SQLAlchemy path with SQLite.

## Docker Compose Runtime

1. Copy `.env.example` to `.env` if local overrides are needed.
2. Run `docker compose up --build`.
3. Confirm PostgreSQL and Redis health checks pass.
4. Confirm `GET http://127.0.0.1:8000/ready` returns `status=ready`.
5. Open `http://127.0.0.1:3000` for the dashboard.
6. Run `python scripts/verify_runtime.py`.
7. Restart services with `docker compose restart api web`.
8. Run `python scripts/verify_runtime.py` again to confirm records remain in the persistent PostgreSQL volume.

The API container applies Alembic migrations at startup. If migrations fail, inspect API logs before retrying.

## Staging Deployment Checklist

1. Point DNS records at the VPS:
   - `PUBLIC_APP_HOST` for the dashboard.
   - `API_PUBLIC_HOST` for the API.
2. Copy `.env.staging.example` to `.env.staging`.
3. Replace every `replace-with-*` value.
4. Set `PUBLIC_APP_URL`, `API_PUBLIC_URL`, and `CORS_ALLOWED_ORIGINS` to the real HTTPS URLs.
5. Set `AUTH_ENABLED=true`.
6. Keep `DEMO_MODE=true` only for private demos; set it false for broader testing.
7. Run `docker compose -f docker-compose.yml -f docker-compose.staging.yml up --build -d`.
8. Optional HTTPS proxy: add `--profile proxy` to start Caddy.
9. Run `python scripts/seed_demo_data.py --api-base-url https://api.example.com`.
10. Run `APFLOW_API_BASE_URL=https://api.example.com APFLOW_WEB_BASE_URL=https://app.example.com python scripts/verify_runtime.py --auth-enabled`.
11. On a real VPS, prefer `PROXY=true scripts/deploy_staging.sh` and `scripts/check_staging.sh https://api.example.com https://app.example.com`.

PowerShell equivalent:

```powershell
$env:APFLOW_API_BASE_URL="https://api.example.com"
$env:APFLOW_WEB_BASE_URL="https://app.example.com"
python scripts/verify_runtime.py
```

## Environment Variable Checklist

Required for staging and production:

- `APP_ENV`
- `PUBLIC_APP_URL`
- `API_PUBLIC_URL`
- `CORS_ALLOWED_ORIGINS`
- `DATABASE_URL`
- `POSTGRES_PASSWORD`
- `AUTH_SECRET_KEY`
- `AUTH_ENABLED`
- `DEMO_MODE`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`
- `NEXT_PUBLIC_API_BASE_URL`

Production additionally requires `AUTH_ENABLED=true` and rejects `DEMO_MODE=true` unless `ALLOW_DEMO_MODE_IN_PRODUCTION=true` is deliberately set.

## Staging Demo Reset

`POST /admin/demo/reset` is intentionally disabled unless `APP_ENV=staging` and `ALLOW_DEMO_RESET=true`. To use it for a private demo cleanup:

1. Set `ALLOW_DEMO_RESET=true` in the staging environment file.
2. Restart the API container.
3. Sign in as an owner/admin and use the dashboard Demo Reset button, or call `POST /admin/demo/reset`.
4. Set `ALLOW_DEMO_RESET=false` again after the reset.
5. Restart the API container again.

Never enable demo reset in production. Production settings reject `ALLOW_DEMO_RESET=true` during startup.

## Demo Operations

1. Check readiness before a demo:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/ready
python scripts/verify_runtime.py --auth-enabled
```

2. Enable `ALLOW_DEMO_RESET=true` temporarily only when you need to change demo state.
3. Seed an explicit deterministic mode without calling live OCR:

```powershell
python scripts/seed_demo_data.py --api-base-url http://127.0.0.1:8000 --mode clean
python scripts/seed_demo_data.py --api-base-url http://127.0.0.1:8000 --mode approval-ready
python scripts/seed_demo_data.py --api-base-url http://127.0.0.1:8000 --mode review-required
python scripts/seed_demo_data.py --api-base-url http://127.0.0.1:8000 --mode vendor-preview
```

4. Use `approval-ready` for the stable presenter path and `review-required` for the human-review path.
5. Set `ALLOW_DEMO_RESET=false` again after cleanup and restart the API service.
6. Use `docs/demo_script.md` and `docs/demo_qa_checklist.md` before live demos.

## Safe Stop, Start, And Backups

Start or update:

```powershell
docker compose up --build -d
```

Stop without deleting data:

```powershell
docker compose stop
```

Restart:

```powershell
docker compose restart api web
```

Avoid this on staging unless data loss is intentional:

```powershell
docker compose down -v
```

`down -v` deletes named volumes, including PostgreSQL data, MinIO data, and uploaded document storage.

Back up PostgreSQL before upgrades:

```powershell
docker compose exec postgres pg_dump -U apflow -d apflow > apflow-backup.sql
```

Also back up named Docker volumes or the host volume directory used for document storage.

For staging, use the checked helper:

```powershell
bash scripts/backup_postgres.sh
bash scripts/restore_postgres.sh backups/apflow-20260507T120000Z.sql
# destructive restore only after reviewing the dry run
bash scripts/restore_postgres.sh backups/apflow-20260507T120000Z.sql --yes
```

## Runtime Modes

- Python/dev: `USE_IN_MEMORY_REPOSITORIES=true`, `AUTH_ENABLED=false`, `DEMO_MODE=true`.
- PostgreSQL local: set `USE_IN_MEMORY_REPOSITORIES=false` and point `DATABASE_URL` at PostgreSQL.
- Docker Compose: Compose wires `DATABASE_URL` to the `postgres` service and runs SQL repositories.
- Auth-enabled: set `AUTH_ENABLED=true`, rotate `AUTH_SECRET_KEY`, register a tenant owner, and use bearer tokens.

## ERP Sync

1. Call `GET /erp/adapters` to confirm supported adapters.
2. Optionally set tenant config with `POST /erp/config`.
3. Run `POST /erp/test-connection` before sync jobs.
4. Run `POST /erp/sync-vendors` before `POST /erp/sync-purchase-orders` when onboarding a tenant.
5. Export invoices explicitly with `POST /erp/export-invoice`; the invoice pipeline only reports `erp_export_ready`.
6. Inspect `GET /erp/sync-logs?tenant_id={uuid}` for success, partial, or failed sync attempts.

Mock mode remains the default. To probe the experimental real Priority connector, set:

```text
PRIORITY_ERP_MODE=real
PRIORITY_ERP_BASE_URL=https://your-priority-host/odata/...
PRIORITY_ERP_USERNAME=...
PRIORITY_ERP_PASSWORD=...  # or PRIORITY_ERP_API_KEY for a token secret
```

Optional future mapping keys are `PRIORITY_ERP_VENDORS_ENTITY_NAME`, `PRIORITY_ERP_PURCHASE_ORDERS_ENTITY_NAME`, and `PRIORITY_ERP_INVOICES_ENTITY_NAME`.

Run `POST /erp/test-connection` first. Real Priority vendor sync, PO sync, and invoice export intentionally return `mapping_required` until tenant-specific Priority entity/procedure mappings are configured. Failures are routed through `ErrorHandlerAgent` and recorded in ERP sync logs.

## OCR And Human Review

1. Check `GET /ocr/providers` for available providers.
2. Check `GET /ocr/test-provider?provider_name=mock` or another provider name for configuration status.
3. Use mock OCR locally unless real cloud credentials are configured.
4. If the pipeline returns `workflow_status=review_required`, inspect `review_tasks`.
5. Submit corrections with `POST /review/tasks/{task_id}/corrections`.
6. Approve or reject the task with the matching review endpoint.

Cloud OCR adapters fail safely when credentials are missing. They do not log raw secrets and route extraction failures to review.

OCR.space setup:

1. Set `OCR_PROVIDER=ocr_space`.
2. Set `OCR_SPACE_API_KEY` in `.env` or `.env.staging`; never commit the key.
3. Optional overrides: `OCR_SPACE_API_URL`, `OCR_SPACE_LANGUAGE`, `OCR_SPACE_ENGINE`, and `OCR_SPACE_TIMEOUT_SECONDS`.
4. Restart FastAPI or the API container.
5. Check `GET /ocr/test-provider?provider_name=ocr_space`.
6. Upload a PDF/image and run `POST /documents/invoices/{document_id}/extract?tenant_id={uuid}`.

OCR.space returns generic parsed text rather than a finance-specific invoice schema. APFlow uses conservative label-based parsing; unclear or missing totals, currency, invoice number, vendor, or dates are marked for human review instead of being invented. `review_required` is a valid safe outcome, not a failed extraction. The dashboard OCR Review section shows parsed result count, parsed text length, OCR exit code, sent filename/filetype/content type, required fields, and a truncated OCR text preview to help tune real sample invoices. To fall back to deterministic local extraction, set `OCR_PROVIDER=mock` and restart.

If OCR.space returns E216 or says it cannot detect file type, confirm the dashboard shows `Sent filetype` as `PDF`, `PNG`, or `JPG` and that `Sent file` has a matching extension. Some synthetic PDFs may not be accepted by OCR.space even with correct metadata; test a real exported PDF or scanned invoice image before treating that as an integration failure.

When OCR.space extraction reaches review:

1. Expand the OCR text preview in the dashboard.
2. Check missing or low-confidence required fields.
3. Enter corrected values in Human review corrections.
4. Submit corrections.
5. Click Process again. The uploaded-document process endpoint applies corrected fields before validation, PO matching, risk scoring, and approval routing.

Live OCR.space file test:

```powershell
python scripts/test_ocr_space.py samples/invoices/invoice.pdf --out samples/ocr-results/ocr-space.json
```

## Invoice Document Uploads

1. Keep `DOCUMENT_STORAGE_PROVIDER=memory` for fast local tests and demos.
2. Use `DOCUMENT_STORAGE_PROVIDER=filesystem` with `DOCUMENT_STORAGE_PATH=/app/.storage/documents` in Docker Compose.
3. Confirm `GET /ready` includes `checks.document_storage.status=ok`.
4. Upload a PDF or image with `POST /documents/invoices/upload`.
5. Run OCR-only extraction with `POST /documents/invoices/{document_id}/extract?tenant_id={uuid}`.
6. Run the full workflow with `POST /documents/invoices/{document_id}/process`.
7. If the result is `workflow_status=review_required`, inspect review tasks before retrying validation or approval.

Unsupported file types return `415`, and oversized uploads return `413`. Do not log raw document bytes or paste invoice contents into support tickets.

## Dashboard Demo Walkthrough

1. Open `http://127.0.0.1:3000`.
2. Confirm the Demo Walkthrough shows the tenant/session step as completed.
3. Upload a PDF or image from the Invoice Upload section.
4. Run Extract to populate OCR confidence and extracted fields.
5. Run Process to populate the workflow timeline and invoice result summary.
6. If `ERP ready` is yes, click Export to Mock ERP and confirm the external invoice ID appears.
7. Click Preview in Vendor-Safe Status Preview to confirm the public status excludes internal risk and approval details.

If the dashboard reports API unavailable, check `GET http://127.0.0.1:8000/ready`, then inspect API logs. If it reports unauthorized, either keep demo mode enabled or sign in with a role that has `invoice:process`, `invoice:export_erp`, and vendor/demo access.

## Azure Document Intelligence OCR

1. Create an Azure AI Document Intelligence resource in the Azure portal. Microsoft’s setup guide is at `https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/how-to-guides/create-document-intelligence-resource?view=doc-intel-4.0.0`.
2. Set `OCR_PROVIDER=azure`.
3. Set `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` to the resource endpoint.
4. Set `AZURE_DOCUMENT_INTELLIGENCE_KEY` to the resource key.
5. Restart FastAPI or the API container.
6. Check `GET /ocr/test-provider?provider_name=azure`.
7. Run `POST /ocr/extract` or `/invoices/full-mock-pipeline` with invoice bytes/content.

If Azure returns low-confidence required fields, the workflow creates human review tasks. To fall back, set `OCR_PROVIDER=mock` and restart.

Live local file test:

```powershell
python scripts/test_azure_ocr.py samples/invoices/invoice.pdf --out samples/ocr-results/invoice.json
```

Optional expected-field comparison:

```powershell
python scripts/compare_ocr_expected.py samples/ocr-results/invoice.json samples/ocr-results/expected.json
```

The expected JSON can include fields such as `invoice_number`, `vendor_name`, `total_amount`, `currency`, and `purchase_order_number`.

Keep real invoice files under `samples/invoices` and generated OCR JSON under `samples/ocr-results`; both folders are gitignored except `.gitkeep`.

## Auth And RBAC

1. Keep `AUTH_ENABLED=false` and `DEMO_MODE=true` for local demo flows and existing mock pipeline checks.
2. Set `AUTH_ENABLED=true` and configure `AUTH_SECRET_KEY` before testing protected access.
3. Create a local tenant owner with `POST /auth/register-demo-tenant`.
4. Login with `POST /auth/login` and send `Authorization: Bearer {token}` to protected endpoints.
5. Use `/admin/users` to add tenant users and `/admin/users/{user_id}/role` to change roles.
6. Expect `401` for missing or invalid tokens and `403` for tenant violations or missing permissions.

Never log passwords or bearer tokens. Rotate `AUTH_SECRET_KEY` before using anything beyond local development.

## Vendor Portal

1. Create demo access with `POST /vendor/access` for a tenant, vendor, and email.
2. Send the returned token in `X-Vendor-Access-Token` for vendor invoice, message, and chat calls.
3. Use `GET /vendor/invoices` to confirm only the linked vendor invoices are visible.
4. Use `POST /vendor/messages` for invoice/payment questions that should create an AP notification event.
5. Use `POST /vendor/chat` for deterministic status answers.
6. If the chatbot returns `escalated=true`, route the request to AP review or vendor communication follow-up.

Do not paste vendor tokens into logs or support tickets. Revoke or expire portal access records when a supplier contact changes.
