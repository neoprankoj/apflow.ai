# APFlow AI

APFlow AI is a multi-tenant accounts payable automation SaaS for invoice intake, extraction, validation, duplicate detection, approval routing, ERP sync, vendor communication, audit logging, and workflow monitoring.

The repository follows the source-of-truth documents in `AGENT.md` and `PLAN.md`. The current backend includes the Phase 1 foundation, Phase 2 core invoice pipeline, Phase 3 mock PO/risk/approval workflow, Phase 4 persistence scaffolding, Phase 5 mock ERP adapter architecture, Phase 6 OCR/review workflow, Phase 7 local auth/RBAC foundation, Phase 8 vendor portal/chatbot workflow, Phase 9 production-like Docker runtime, Phase 10 OCR/document upload flow, and Phase 11 dashboard demo polish.

1. `TenantSecurityAgent`
2. `AuditLoggingAgent`
3. `MonitoringAgent`
4. `ErrorHandlerAgent`
5. `APWorkflowOrchestratorAgent`
6. `InvoiceIngestionAgent`
7. `InvoiceExtractionAgent`
8. `InvoiceNormalizationAgent`
9. `SupplierIdentityAgent`
10. `InvoiceValidationAgent`
11. `DuplicateDetectionAgent`
12. `PurchaseOrderMatchingAgent`
13. `FraudRiskScoringAgent`
14. `ApprovalRoutingAgent`
15. `NotificationAgent`
16. `ERPConnectorAgent`
17. `HumanReviewAgent`
18. `AuthService` and RBAC dependencies
19. `VendorCommunicationAgent`
20. `PaymentStatusChatbotAgent`
21. Storage adapter layer for invoice document uploads

External systems are represented by mock or in-memory adapters until real credentials and provider choices are configured.

Persistence can run in two modes:

- `USE_IN_MEMORY_REPOSITORIES=true` keeps the fast mock repository path active.
- `USE_IN_MEMORY_REPOSITORIES=false` uses the SQLAlchemy/PostgreSQL repository path.

## Mock Workflow

`POST /invoices/full-mock-pipeline` runs:

```text
ingestion -> extraction -> normalization -> supplier match -> validation
-> duplicate detection -> PO matching -> fraud risk scoring -> approval routing
-> mock notifications
```

The response is shaped for the future dashboard and includes invoice, validation, duplicate, PO match, risk, approval, notifications, and workflow status.

ERP integration is explicit through `/erp/*` endpoints. Mock adapters are available for Priority, Odoo, and Zoho Books; they do not call real ERP APIs.

OCR defaults to the mock provider. OCR.space and Azure Document Intelligence can be enabled with credentials; Google Document AI and AWS Textract adapters remain safe placeholders until credentials are configured.
OCR.space can be enabled with `OCR_PROVIDER=ocr_space` and `OCR_SPACE_API_KEY`. It sends uploaded PDF/image bytes to OCR.space and maps `ParsedText` into the shared field-confidence and human-review workflow with conservative parsing.
Azure Document Intelligence can be enabled with `OCR_PROVIDER=azure`, `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`, and `AZURE_DOCUMENT_INTELLIGENCE_KEY`. The Azure adapter uses the prebuilt invoice model and maps field-level confidence into the existing human-review workflow.

Real invoice documents can be uploaded through `POST /documents/invoices/upload`. The upload flow stores tenant-scoped document metadata and bytes, then can run OCR-only extraction or continue through the full AP pipeline. Tests and local demo mode use in-memory document storage by default. Docker Compose uses filesystem-backed storage mounted at `/app/.storage/documents`.

Authentication defaults to demo-friendly local development with `AUTH_ENABLED=false` and `DEMO_MODE=true`. Set `AUTH_ENABLED=true` to require local JWT bearer tokens, tenant membership checks, and role permissions for protected ERP, review, audit, invoice processing, and tenant admin routes.

Vendor portal access uses random demo tokens whose hashes are stored tenant-scoped. Vendor APIs only return vendor-safe invoice/payment fields and deterministic chatbot answers; no external LLM or real email is used.

## Local Layout

```text
apps/api    FastAPI backend, agent contracts, tests, workers
apps/web    Next.js dashboard shell
docs        Architecture and operations notes
packages    Shared package placeholders
```

## Backend

Local Python/dev mode:

```powershell
cd apps/api
pip install -e ".[dev]"
pytest
uvicorn main:app --reload
```

Run migrations:

```powershell
cd apps/api
alembic -c alembic.ini upgrade head
```

Useful local checks:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
Invoke-WebRequest http://127.0.0.1:8000/ready
```

PostgreSQL runtime mode:

```powershell
$env:USE_IN_MEMORY_REPOSITORIES="false"
$env:DATABASE_URL="postgresql+psycopg://apflow:apflow@localhost:5432/apflow"
cd apps/api
alembic -c alembic.ini upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000
```

Docker Compose mode:

```powershell
docker compose up --build
python scripts/verify_runtime.py
docker compose restart api web
python scripts/verify_runtime.py
```

Compose starts PostgreSQL, Redis, MinIO, FastAPI, and Next.js. The API container runs Alembic migrations before Uvicorn and uses `USE_IN_MEMORY_REPOSITORIES=false`.

Staging mode:

```powershell
copy .env.staging.example .env.staging
# edit every replace-with-* value before starting
docker compose -f docker-compose.yml -f docker-compose.staging.yml up --build -d
python scripts/seed_demo_data.py --api-base-url https://api.apflow-staging.example.com
$env:APFLOW_API_BASE_URL="https://api.apflow-staging.example.com"
$env:APFLOW_WEB_BASE_URL="https://apflow-staging.example.com"
python scripts/verify_runtime.py
```

To use the optional Caddy HTTPS reverse proxy, include the proxy profile:

```powershell
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile proxy up --build -d
```

Never use `docker compose down -v` on staging unless you intentionally want to delete PostgreSQL, MinIO, and document storage volumes.

Detailed VPS deployment instructions are in `docs/deployment.md`. Staging security checks are in `docs/security_staging_checklist.md`.

Real VPS deployment shortcut:

```powershell
# On Ubuntu VPS, first review the dry run:
bash scripts/bootstrap_vps.sh --dry-run
bash scripts/bootstrap_vps.sh --execute

copy .env.staging.example .env.staging
# edit domains and secrets, then:
$env:PROXY="true"
bash scripts/deploy_staging.sh
bash scripts/check_staging.sh https://api.example.com https://app.example.com
```

The default staging topology is `https://app.example.com` for the dashboard and `https://api.example.com` for FastAPI through Caddy/Let's Encrypt.

Demo mode keeps `AUTH_ENABLED=false` and `DEMO_MODE=true`. For auth-enabled local checks, set `AUTH_ENABLED=true`, change `AUTH_SECRET_KEY`, create a demo tenant through `/auth/register-demo-tenant`, and send bearer tokens to protected endpoints.

Azure OCR mode:

```powershell
$env:OCR_PROVIDER="azure"
$env:AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://<resource>.cognitiveservices.azure.com/"
$env:AZURE_DOCUMENT_INTELLIGENCE_KEY="<key>"
Invoke-WebRequest "http://127.0.0.1:8000/ocr/test-provider?provider_name=azure"
```

Remove the Azure variables or set `OCR_PROVIDER=mock` to return to deterministic local OCR.

OCR.space mode:

```powershell
$env:OCR_PROVIDER="ocr_space"
$env:OCR_SPACE_API_KEY="<key>"
Invoke-WebRequest "http://127.0.0.1:8000/ocr/test-provider?provider_name=ocr_space"
```

Live OCR.space local file test:

```powershell
python scripts/test_ocr_space.py samples/invoices/invoice.pdf --out samples/ocr-results/ocr-space.json
```

OCR.space health checks only report configured/missing credentials and do not consume OCR quota. Set `OCR_PROVIDER=mock` and restart to return to deterministic local OCR.

Live Azure OCR test pack:

```powershell
# Put private samples under samples/invoices; this folder is gitignored.
python scripts/test_azure_ocr.py samples/invoices/invoice.pdf --out samples/ocr-results/invoice.json
python scripts/compare_ocr_expected.py samples/ocr-results/invoice.json samples/ocr-results/expected.json
```

Do not commit real invoices, OCR result JSON, or Azure credentials. `samples/invoices/*` and `samples/ocr-results/*` are ignored except `.gitkeep` placeholders.

## Frontend

```powershell
cd apps/web
npm install
npm run dev
```

The dashboard reads `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`, displays the demo/current tenant session, and shows tenant admin users when the current role has `tenant:admin`.

The dashboard also includes a guided demo walkthrough for PDF/image upload, extract-only OCR checks, full-pipeline processing, workflow timeline, result summary, mock ERP export, and vendor-safe status preview. It renders a separated vendor portal demo section with vendor-visible invoices, a message box, and status chat shell.

Use `.env.example` as the starting point for local configuration. Do not commit real provider credentials.

Use `.env.staging.example` as the starting point for private VPS deployments. Staging and production reject wildcard CORS, default MinIO credentials, weak auth secrets, and missing database/public URL settings.
