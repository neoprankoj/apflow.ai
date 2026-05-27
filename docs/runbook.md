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

## Payment Status

Payment status tracking is currently APFlow-internal and manual/mock only.

1. Use the dashboard `Payment Status` section to run mock payment sync.
2. Use manual updates for demo payment states.
3. Confirm vendor-safe preview shows only safe payment language.
4. Confirm Audit Trail records payment status events.

No bank, payment processor, or real ERP payment status sync runs in this phase. See [payment_status.md](payment_status.md) for the model and vendor-safe boundary.

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

Production additionally requires `AUTH_ENABLED=true` and rejects `DEMO_MODE=true`. Demo behavior is private-staging only.

## Staging Demo Reset

`POST /admin/demo/reset` is intentionally disabled unless `APP_ENV=staging` and `ALLOW_DEMO_RESET=true`. To use it for a private demo cleanup:

1. Set `ALLOW_DEMO_RESET=true` in the staging environment file.
2. Restart the API container.
3. Sign in as an owner/admin and use the dashboard Demo Reset button, or call `POST /admin/demo/reset`.
4. Set `ALLOW_DEMO_RESET=false` again after the reset.
5. Restart the API container again.

Never enable demo reset in production. Production settings reject `ALLOW_DEMO_RESET=true` during startup.

## Demo Seed Profiles

Admin -> Demo Seed Profiles provides deterministic tenant data packs for repeatable demos:

- `clean_minimal`
- `ap_manager_demo`
- `vendor_self_service_demo`
- `priority_connector_demo`
- `compliance_demo`
- `analytics_rich_demo`

The API endpoints are `GET /admin/demo/seed-profiles` and `POST /admin/demo/seed-profile`. Running a profile requires owner/admin access, `ALLOW_DEMO_RESET=true`, and confirmation text `SEED_DEMO_PROFILE`. The operation is tenant-scoped and blocked in production.

Recommended flow:

1. Set `ALLOW_DEMO_RESET=true` in `.env.staging` on the VPS only.
2. Recreate the API container.
3. Run the desired profile from Admin -> Demo Seed Profiles.
4. Copy any one-time vendor token only if needed for the demo.
5. Set `ALLOW_DEMO_RESET=false`.
6. Recreate the API container again.
7. Run the browser smoke checklist.

Details are in [demo_seed_profiles.md](demo_seed_profiles.md).

## Demo Operations

For the complete demo readiness flow, use [demo_readiness_pack.md](demo_readiness_pack.md).
For Demo/Pilot/Production readiness definitions and current blockers, use [production_readiness_checklist.md](production_readiness_checklist.md). For the production access guardrails behind that gate, use [production_security.md](production_security.md).

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
7. For notification demos, use Admin -> Notification Settings. Mock delivery records events inside APFlow only; Email, Slack, and Teams placeholders must remain not configured unless a real provider rollout has been approved.

## Before Demo

Run these checks on the staging VPS before a live walkthrough:

```bash
git log --oneline --max-count=5
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl -s "http://127.0.0.1:8000/ocr/test-provider?provider_name=ocr_space"
python3 scripts/verify_runtime.py --api-url http://46.101.97.231/api --web-url http://46.101.97.231 --auth-enabled
```

Confirm before presenting:

- `ALLOW_DEMO_RESET=false` unless you are intentionally resetting.
- If you need known data, use Admin -> Demo Seed Profiles and the explicit `SEED_DEMO_PROFILE` confirmation.
- OCR provider is `ocr_space`.
- OCR.space engine 2 is the recommended staging engine.
- Priority mode is mock.
- Priority writes are disabled.
- Mock ERP export still works.
- Payment Status mock sync works and does not contact real payment systems.
- No `.env.staging` or secret changes are committed.

If staging environment values were changed, recreate the API container so the new values load:

```bash
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging up -d --force-recreate api
```

## Pilot Readiness Checkpoint Commands

Run these before any pilot go/no-go review or public access planning session:

```bash
git log --oneline --max-count=5
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
python3 scripts/verify_runtime.py --api-url http://46.101.97.231/api --web-url http://46.101.97.231 --auth-enabled
docker inspect apflowai-api-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep ALLOW_DEMO_RESET
```

Expected `ALLOW_DEMO_RESET` result:

```text
ALLOW_DEMO_RESET=false
```

If the Compose project name changes the API container name, inspect the current API container from `docker compose ps` and run the same environment check against that container. Do not continue a pilot readiness review until `ALLOW_DEMO_RESET=false`, `/health` passes, `/ready` is ready, and the runtime verifier passes.

## Legal / Privacy / Data Handling Preflight

Before any real customer pilot or real customer document upload:

- Review [legal_privacy_data_pack.md](legal_privacy_data_pack.md).
- Share or adapt [customer_data_handling_summary.md](customer_data_handling_summary.md) only after counsel review.
- Use [pilot_terms_outline.md](pilot_terms_outline.md) as a non-binding outline for counsel, not as a contract.
- Confirm the customer-approved data categories and authorized users.
- Confirm support and incident contacts.
- Confirm data retention, deletion, export, and backup expectations.
- Run a backup before importing pilot data.
- Keep `ALLOW_DEMO_RESET=false`.
- Keep Priority writes disabled unless a separate customer-specific write rollout is approved.

Do not claim production readiness, GDPR/SOC 2/ISO compliance, certified e-invoicing, tax authority submission, real billing, or real notification delivery from these draft documents.

## Public Exposure Preflight Commands

Run these before changing DNS, proxy config, firewall rules, or HTTPS settings:

```bash
git log --oneline --max-count=5
docker compose ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
sudo ss -tulpn
sudo ufw status verbose
docker inspect apflowai-api-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep ALLOW_DEMO_RESET
```

Expected `ALLOW_DEMO_RESET` result:

```text
ALLOW_DEMO_RESET=false
```

Future HTTPS verifier template:

```bash
python3 scripts/verify_runtime.py --api-url https://DOMAIN/api --web-url https://DOMAIN --auth-enabled
```

Use [public_access_https_readiness.md](public_access_https_readiness.md) before applying any domain, TLS, or public proxy change.
Use [reverse_proxy_security_hardening.md](reverse_proxy_security_hardening.md) before applying any live Nginx/Caddy route, timeout, upload limit, or security-header change.

## Public Port Inspection

Use the read-only helper before any firewall, proxy, or Domain + HTTPS change:

```bash
bash scripts/check_public_ports.sh
sudo ss -tulpn
sudo ufw status verbose
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

The helper prints Docker services, published ports, listening sockets, UFW status when available, warnings for internal service ports bound on all interfaces, and OK lines for localhost-only bindings. After PR #68, ports `3000` and `8000` should be `127.0.0.1` only, while `5432`, `6379`, `9000`, and `9001` should not be host-published. It does not run `ufw enable`, change firewall rules, or modify iptables.

Full checklist: [public_port_firewall_hardening.md](public_port_firewall_hardening.md).

## Reverse Proxy Inspection

Use the read-only helper before changing live Nginx/Caddy config, Domain + HTTPS, or security headers:

```bash
bash scripts/check_reverse_proxy.sh
bash scripts/check_reverse_proxy.sh http://46.101.97.231
```

The helper prints Nginx installation/version status, attempts `sudo nginx -t` only when passwordless sudo is available, reports listeners on `80` and `443`, checks localhost web/API health when services are reachable, and checks public `/api/health` when `APFLOW_PUBLIC_BASE_URL` or an argument is provided. It does not modify proxy config, reload services, restart services, issue certificates, or print secrets.

Full checklist: [reverse_proxy_security_hardening.md](reverse_proxy_security_hardening.md).

## After Demo

Run these checks after the demo:

- Confirm `ALLOW_DEMO_RESET=false`.
- Revoke or rotate any vendor token that appeared in screenshots, chat, logs, or docs.
- Confirm Priority writes are disabled.
- Confirm no secrets, bearer tokens, OCR keys, or real invoice PII were exposed in screenshots, logs, docs, or chat.
- Confirm `/health` and `/ready` still pass.
- Confirm Audit Trail contains the expected approval/export/import events.
- Check recent API logs if any browser request showed an error:

```bash
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging logs api --tail=80
```

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
bash scripts/backup_staging.sh
```

Also back up named Docker volumes or the host volume directory used for document storage.

For the complete non-destructive staging backup and restore drill, use [backup_restore_drill.md](backup_restore_drill.md).

For staging, use the checked helper:

```powershell
bash scripts/backup_postgres.sh
bash scripts/restore_postgres.sh backups/apflow-20260507T120000Z.sql
# destructive restore only after reviewing the dry run
bash scripts/restore_postgres.sh backups/apflow-20260507T120000Z.sql --yes
```

For the custom-format backup and temporary restore drill helpers:

```powershell
bash scripts/backup_staging.sh
bash scripts/restore_drill_staging.sh backups/apflow-postgres-YYYYMMDDTHHMMSSZ.dump
```

Staging drill note:

- A manual drill after PR #65 verified that `psql -U app_user -d apflow` is the working database identity even when the container environment reports `POSTGRES_USER=apflow`.
- A custom-format backup with `pg_dump -U app_user -d apflow -Fc` produced a valid non-empty dump.
- A temporary restore database `apflow_restore_drill_*` restored successfully, listed 25 tables, and was dropped.
- `/health` and `/ready` remained OK after the drill.

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
PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=false
PRIORITY_ERP_MAX_PREVIEW_RECORDS=10
```

Keep `PRIORITY_ERP_ENABLE_WRITES=false` while validating a tenant mapping. Use `POST /erp/test-connection` first, then save and validate tenant-scoped mapping JSON with `/erp/priority/mapping` and `/erp/priority/validate-mapping`.

Priority entity/form names vary by customer environment. Confirm the tenant's actual forms and fields before enabling real sync or export. Vendor and PO sync return `mapping_required` until their mappings exist; real invoice export returns a payload preview with `write_disabled` while writes remain disabled. Failures are routed through `ErrorHandlerAgent` and recorded in ERP sync logs.

For safe staging edits, use the dashboard `Admin` section:

1. Open `Priority ERP Mapping`.
2. Review `Priority Real Connection Readiness`; staging should show mock mode, read-only fetch disabled, and writes disabled.
3. Use `Reload readiness` for local config checks. Use `Run remote connection drill` only after real mode, read-only fetch, base URL, and credentials are configured.
4. Load the current tenant mapping or start from the sample JSON.
5. Validate before saving.
6. Treat the sample as a template only; verify every entity and field against the customer's Priority environment.
7. Confirm the UI still shows mock mode and writes disabled unless operations explicitly changes those runtime settings.
8. Keep preview source set to `Sample records` for deterministic staging demos.
9. Use `Preview Vendor Sync` and `Preview Purchase Orders` to inspect mapped sample rows before enabling any real import path.
10. If real Priority credentials are configured later, switch source to `Real Priority read-only fetch` and confirm the gate is enabled. This path performs GET-only OData reads and does not import or write data.
11. Use `Generate Vendor Import Plan` and `Generate Purchase Order Import Plan` to compare mapped rows with existing APFlow records before any import is enabled.
12. Select only the rows you intend to import, type `IMPORT_SELECTED`, and import into APFlow only when the plan is understood.
13. After import, reload `Imported Records` to verify APFlow vendor/PO IDs, Priority external IDs, source, and last import result.

Priority real-readiness drill:

1. Confirm a database backup exists before changing staging ERP configuration.
2. Edit `.env.staging` only on the server; never commit real Priority credentials.
3. Set `PRIORITY_ERP_MODE=real`.
4. Set `PRIORITY_ERP_BASE_URL`, `PRIORITY_ERP_USERNAME`, and `PRIORITY_ERP_PASSWORD` or `PRIORITY_ERP_API_KEY`.
5. Set `PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=true`.
6. Keep `PRIORITY_ERP_ENABLE_WRITES=false`.
7. Restart the API.
8. Run `/ready`.
9. Open `Priority Real Connection Readiness`.
10. Run the remote connection drill. It performs GET-only service-root and `$metadata` checks; it does not fetch entity data.
11. Validate and save tenant mapping.
12. Run vendor/PO read-only preview with source `Real Priority read-only fetch`.
13. Set `PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=false` again when testing is complete, then restart the API.

Priority sync preview is dry-run only. It does not import vendors or purchase orders into APFlow and does not write to Priority. In mock mode, the preview uses deterministic synthetic Priority-like records. In real mode, configured credentials can be used for an explicitly requested, GET-only limited OData fetch when `PRIORITY_ERP_READ_ONLY_FETCH_ENABLED=true`. If the gate is disabled or credentials are missing, the dashboard shows a safe status and operators should use sample records.

Priority import plans are also preview-only. They reuse the saved mapping and dry-run records, then classify each row as `would_create`, `would_update`, `would_skip`, or `would_conflict` against existing tenant vendors and purchase orders. A conflict means matching was ambiguous and should be resolved before enabling a future import. The import-plan endpoints do not create vendors, purchase orders, ERP records, or audit events.

Controlled Priority import writes only to APFlow. It regenerates the plan server-side, accepts only selected external IDs, requires the `IMPORT_SELECTED` confirmation phrase, blocks conflicts, skips unchanged rows, and requires `allow_updates=true` before updating existing APFlow records. Import vendors before purchase orders so PO rows can resolve `vendor_external_id`. Priority writes remain disabled and are not used by controlled import.

Imported-record visibility is read-only. The dashboard uses `/erp/priority/imported/vendors` and `/erp/priority/imported/purchase-orders` to show what now exists in APFlow after controlled import. These views never call Priority, never import data, and are useful for confirming that audit events and external references line up with the operator action.

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
3. Optional overrides: `OCR_SPACE_API_URL`, `OCR_SPACE_LANGUAGE`, `OCR_SPACE_ENGINE`, `OCR_SPACE_FALLBACK_ENGINE`, `OCR_SPACE_ENABLE_ENGINE_FALLBACK`, and `OCR_SPACE_TIMEOUT_SECONDS`.
4. Restart FastAPI or the API container.
5. Check `GET /ocr/test-provider?provider_name=ocr_space`.
6. Upload a PDF/image and run `POST /documents/invoices/{document_id}/extract?tenant_id={uuid}`.

OCR.space returns generic parsed text rather than a finance-specific invoice schema. APFlow uses conservative label-based parsing; unclear or missing totals, currency, invoice number, vendor, or dates are marked for human review instead of being invented. `review_required` is a valid safe outcome, not a failed extraction. The dashboard OCR Review section shows parsed result count, parsed text length, OCR exit code, sent filename/filetype/content type, required fields, and a truncated OCR text preview to help tune real sample invoices. To fall back to deterministic local extraction, set `OCR_PROVIDER=mock` and restart.

If OCR.space returns E216 or says it cannot detect file type, confirm the dashboard shows `Sent filetype` as `PDF`, `PNG`, or `JPG` and that `Sent file` has a matching extension. If APFlow reports `invalid_file_signature` or OCR.space returns E501, the uploaded bytes are not a real PDF/image invoice; re-download or re-export the source invoice. Some synthetic PDFs may not be accepted by OCR.space even with correct metadata; test a real exported PDF or scanned invoice image before treating that as an integration failure.

If OCR.space returns E580, the selected OCR engine failed while reading the file. Configure `OCR_SPACE_ENABLE_ENGINE_FALLBACK=true` and `OCR_SPACE_FALLBACK_ENGINE=2` to retry a different engine once. Docker environment changes require recreating the API container, not only restarting it:

```powershell
docker compose ... up -d --force-recreate api
```

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

1. Use Vendor Access Management or `POST /vendor/accesses` to create access for a tenant vendor/supplier.
2. Copy the returned token immediately. APFlow will not show it again.
3. Send the token in `X-Vendor-Access-Token` for vendor invoice, message, and chat calls.
4. Use `GET /vendor/invoices` to confirm only the linked vendor invoices are visible.
5. Use `POST /vendor/accesses/{access_id}/rotate` when a supplier contact changes.
6. Use `POST /vendor/accesses/{access_id}/revoke` when access should stop.
7. Use Audit Trail to confirm create, use, rotate, revoke, and vendor-safe preview events.

Do not paste vendor tokens into logs or support tickets. Raw tokens are shown once, token hashes are never returned, and revoked/expired tokens should fail.
