# Architecture

APFlow AI uses agent boundaries from `AGENT.md` and the phased build order from `PLAN.md`.

The current foundation implements typed events, in-memory audit and metric stores, deterministic security authorization, retry classification, and workflow dispatch. These interfaces are intentionally persistence-agnostic so PostgreSQL, Redis, queue workers, and provider adapters can replace the in-memory stores without changing agent responsibilities.

## Phase 3 Mock Workflow

The full mock invoice workflow now covers:

```text
InvoiceIngestionAgent
-> InvoiceExtractionAgent
-> InvoiceNormalizationAgent
-> SupplierIdentityAgent
-> InvoiceValidationAgent
-> DuplicateDetectionAgent
-> PurchaseOrderMatchingAgent
-> FraudRiskScoringAgent
-> ApprovalRoutingAgent
-> NotificationAgent
```

The repository remains tenant-scoped and in-memory for local development. It stores raw invoices, canonical invoices, vendors, purchase orders, approval policies, approval tasks, and notification events. Mock fixtures create a default Northstar vendor, `PO-100`, and a deterministic approval policy when a tenant first runs the Phase 3 endpoint.

No real ERP, email, Slack, or Teams calls are made in Phase 3. The notification adapter records mock delivery events for dashboard and test consumption.

## Phase 4 Persistence

Phase 4 adds repository protocols and two implementations:

- `InMemoryAPRepository` for fast unit tests and mock development.
- `SQLAlchemyAPRepository` for PostgreSQL-backed runtime persistence.

Runtime selection is controlled by `USE_IN_MEMORY_REPOSITORIES`. The SQLAlchemy repository preserves the same agent-facing methods used by the in-memory repository so agents remain persistence-agnostic.

Persistent tables cover tenants, vendors, invoices, invoice lines, purchase orders, purchase order lines, approval policies, approval tasks, notification events, audit events, workflow states, and workflow events. Alembic owns schema creation from `apps/api/migrations`.

The Next.js dashboard fetches FastAPI list endpoints directly using `NEXT_PUBLIC_API_BASE_URL` and a demo tenant ID. Authentication and user-specific tenant selection are intentionally deferred.

## Phase 5 ERP Adapter Layer

`ERPConnectorAgent` selects a tenant ERP adapter from `ERPConnectionConfig` or an explicit request override. The agent owns sync orchestration, audit logging, monitoring metrics, error routing, and sync-log persistence. Adapter implementations remain stateless and mock-first.

Current adapters:

- `MockPriorityERPAdapter` with Israeli/local-market-style vendors and POs.
- `MockOdooERPAdapter` with distributor/manufacturer-style vendors and POs.
- `MockZohoBooksAdapter` with SMB-style vendors and POs.

Supported operations:

```text
test_connection
sync_vendors
sync_purchase_orders
export_invoice
update_invoice_status
sync_payment_status
```

ERP sync logs and external references are tenant-scoped. Real ERP adapters can be added by implementing `ERPAdapterProtocol` without changing `ERPConnectorAgent`.

## Phase 6 OCR And Review

`InvoiceExtractionAgent` now calls `OCRProviderFactory`, which selects an adapter from `OCR_PROVIDER`.

Supported providers:

- `mock`, default and fully deterministic.
- `ocr_space`, real OCR.space adapter for PDF/image OCR when `OCR_SPACE_API_KEY` is configured.
- `azure`, real Azure Document Intelligence adapter using `prebuilt-invoice` when endpoint/key are configured.
- `google`, safe Google Document AI placeholder until credentials are configured.
- `aws`, safe AWS Textract placeholder until credentials are configured.

Every OCR result includes field-level confidence, confidence bands, required-field gaps, and provider metadata. `HumanReviewAgent` inspects OCR output and creates tenant-scoped review tasks for low-confidence required fields, missing required fields, suspicious totals, and provider failures.

OCR.space extraction sends uploaded PDF/image bytes through multipart upload, then maps `ParsedText` with conservative label-based parsing into the shared `OCRExtractionResult` schema. Missing or unclear required fields are routed to human review instead of being guessed.

Azure extraction maps invoice ID, vendor name, vendor tax ID, dates, currency, subtotal, tax, invoice total, purchase order number, and line items into the shared `OCRExtractionResult` schema. Low-confidence Azure fields follow the same human-review path as mock OCR.

When required-field review is needed, `/invoices/full-mock-pipeline` returns `workflow_status=review_required` and stops before validation and approval. High-confidence mock extraction continues through the existing workflow unchanged.

## Phase 7 Auth And RBAC

Phase 7 adds a local JWT auth foundation without external providers. `AuthService` owns PBKDF2 password hashing, JWT issue/verify, demo context creation, and a role-to-permission map. `TenantMembership` connects users to tenants with one of: `owner`, `admin`, `controller`, `ap_manager`, `approver`, or `viewer`.

`AUTH_ENABLED=false` and `DEMO_MODE=true` preserve existing local/demo behavior. With `AUTH_ENABLED=true`, FastAPI dependencies resolve the tenant from the authenticated membership, reject cross-tenant requests, and gate protected ERP, review, audit, invoice processing, and admin routes with explicit permissions.

The dashboard now reads `/auth/me` in demo mode and shows the current tenant, user role, and tenant users when the session has `tenant:admin`.

## Phase 8 Vendor Portal And Chatbot

Phase 8 adds `VendorCommunicationAgent` and `PaymentStatusChatbotAgent`. Vendor access is represented by tenant-scoped portal records with hashed random tokens. The vendor API resolves access before every invoice, message, and chat request and filters invoices by the linked `vendor_id`.

Vendor-safe status mapping converts internal workflow and payment signals into public states: `received`, `under_review`, `needs_information`, `approved`, `scheduled_for_payment`, `paid`, and `rejected`. The mapper uses only invoice records, review task presence, approval task status, and mocked ERP payment status details.

The chatbot is deterministic and retrieval-limited. It classifies questions into invoice receipt, approval status, payment status, public rejection reason, missing information, or unknown. Unknown or internal questions are deflected to AP contact instead of exposing risk, audit, ERP sync, or approval-policy data.

## Phase 9 Runtime

Docker Compose defines PostgreSQL with a persistent volume, Redis, MinIO, FastAPI, and Next.js. The API container runs Alembic migrations before starting Uvicorn, uses SQLAlchemy repositories, and exposes `/health` and `/ready`.

`/ready` checks repository/database mode, OCR provider health, and the ERP adapter registry. Startup logs print environment, repository mode, auth mode, demo mode, OCR provider, and mock ERP adapters.

The Next.js container builds the app and runs `next start`. In Compose, `NEXT_PUBLIC_API_BASE_URL` is set to `http://api:8000` because dashboard data is fetched during server rendering inside the web container.

## Phase 10 Document Upload Flow

The document upload layer adds a provider-neutral `StorageAdapterProtocol` for invoice PDFs and images:

- `InMemoryStorageAdapter` keeps tests and local demo runs fast and isolated.
- `FileSystemStorageAdapter` stores documents on a mounted Docker volume for production-like Compose runs.

Uploaded document metadata is persisted tenant-scoped through both the in-memory repository and SQLAlchemy repository. The schema records document ID, tenant ID, original filename, content type, byte size, storage provider, storage key, uploader, and creation time.

The upload path is intentionally separate from the legacy mock invoice payloads:

```text
POST /documents/invoices/upload
-> storage adapter
-> uploaded document repository
-> POST /documents/invoices/{document_id}/extract
-> InvoiceExtractionAgent
-> HumanReviewAgent
```

Processing an uploaded document reuses the existing full pipeline after extraction:

```text
stored document
-> OCRProviderFactory
-> InvoiceExtractionAgent
-> HumanReviewAgent
-> InvoiceNormalizationAgent
-> SupplierIdentityAgent
-> InvoiceValidationAgent
-> DuplicateDetectionAgent
-> PurchaseOrderMatchingAgent
-> FraudRiskScoringAgent
-> ApprovalRoutingAgent
-> NotificationAgent
```

Low-confidence required fields stop at `workflow_status=review_required` before validation or approval. High-confidence uploads continue through the same deterministic PO/risk/approval workflow as `/invoices/full-mock-pipeline`.

The dashboard upload panel calls the document endpoints directly. It displays upload metadata, extraction confidence, review status, workflow status, and extracted field previews while keeping the existing mock pipeline and vendor portal sections intact.

## Phase 11 Demo Walkthrough

Phase 11 is dashboard-only polish. It does not add a backend timeline endpoint because the existing document, invoice pipeline, ERP export, sync-log, and vendor-safe status APIs already provide the data needed for a guided demo.

The dashboard now presents an end-to-end walkthrough:

```text
demo tenant ready
-> upload invoice
-> extract OCR fields
-> process AP pipeline
-> review workflow result
-> export to mock ERP
-> preview vendor-safe status
```

`WorkflowTimeline` is a reusable frontend component that renders stage status, timestamps, summaries, and warnings. For the current demo, timeline stages are derived from upload, extraction, pipeline, and ERP export responses. Backend audit and workflow events remain unchanged.

The invoice result summary intentionally shows finance-relevant outcomes in one place: invoice identity, vendor, total, OCR confidence, review status, workflow status, PO match, risk level, approval route, and ERP export readiness. The vendor preview calls the existing vendor portal API and keeps fraud scores, risk reasons, approval-policy internals, audit events, and ERP sync internals out of the vendor-facing view.

## Phase 12 Staging Runtime

Phase 12 keeps the product architecture unchanged and hardens runtime configuration around it.

Runtime environments are explicit:

- `local`: permissive defaults for Python dev and localhost Docker.
- `staging`: private VPS/server mode with real public URLs, fixed CORS origins, changed secrets, SQL repositories, and optional demo mode.
- `production`: requires auth, rejects demo mode by default, rejects weak/default secrets, and rejects wildcard CORS.

FastAPI applies CORS from `CORS_ALLOWED_ORIGINS`. Local mode allows localhost. Staging and production require configured origins and reject `*`.

The API settings model validates startup safety before serving traffic. Unsafe staging/production values fail at process startup instead of allowing a partially insecure deployment.

Docker remains practical:

- `docker-compose.yml` keeps local defaults and persistent volumes.
- `docker-compose.staging.yml` layers restart policies, staging env file usage, and an optional Caddy reverse proxy profile.
- `deploy/Caddyfile` routes the frontend and API hosts to the `web` and `api` services and is ready for Let's Encrypt through Caddy.

`scripts/seed_demo_data.py` seeds a demo tenant through the API without printing bearer tokens. `scripts/verify_runtime.py` now checks health, readiness, dashboard reachability, mock pipeline, invoice upload/process, ERP export, vendor messages, chatbot, and vendor-safe invoice status.

## Phase 14 Azure OCR Validation

Phase 14 keeps automated tests credential-free while adding manual live validation tooling for Azure Document Intelligence.

`AzureDocumentIntelligenceOCRAdapter` still uses the shared `OCRExtractionResult` contract, but now handles more real-world Azure response variation:

- alternative invoice field names;
- missing optional fields;
- missing/null confidence scores;
- currency values embedded in total fields;
- object/dict line item shapes;
- safe provider timeout/error responses.

`scripts/test_azure_ocr.py` calls the adapter directly with a local PDF/image and prints field confidence, line items, review-required fields, and average confidence. `scripts/compare_ocr_expected.py` compares the generated OCR JSON against a small expected-field JSON for manual extraction quality checks.

Real invoice files and generated OCR outputs are kept under ignored sample folders so they are not committed by default.
