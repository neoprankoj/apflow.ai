# PLAN.md — Development Execution Plan

## Project Goal
Build APFlow AI, a multi-tenant SaaS platform for AI Accounts Payable and E-Invoicing Automation. The platform will automate invoice ingestion, OCR/document extraction, validation, duplicate detection, PO matching, approval routing, vendor communication, ERP synchronization, payment-status support, monitoring, and audit logging for mid-market companies processing 500–50,000 invoices per month.

## Tech Stack

### Frontend
- Next.js 15+
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query
- Zod for frontend schema validation

### Backend
- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy or SQLModel
- Celery or Dramatiq for background jobs
- Redis for queues/cache
- PostgreSQL for primary relational data
- pgvector optional for fuzzy/vendor/invoice similarity

### AI / Document Processing
- OpenAI API or Azure OpenAI for LLM workflows
- Azure Document Intelligence, Google Document AI, AWS Textract, or Tesseract fallback for OCR
- PDF/XML parsers
- Deterministic validation rules before LLM reasoning

### Infrastructure
- Docker and Docker Compose for local development
- Kubernetes or managed container platform for production
- Object storage: S3-compatible storage
- Secrets manager: AWS Secrets Manager, Doppler, Infisical, or equivalent
- Monitoring: OpenTelemetry, Prometheus-compatible metrics, Grafana-compatible dashboards
- Logging: structured JSON logs

### Integrations
- Email ingestion: SendGrid Inbound Parse, Postmark Inbound, Mailgun Routes, or Microsoft Graph/Gmail API
- ERP target v1: Priority ERP or Odoo
- Future ERP adapters: Zoho Books, QuickBooks, NetSuite, Xero, SAP Business One
- Notifications: Email, in-app, Slack, Microsoft Teams, webhooks

## Folder Structure

```text
apflow-ai/
├── AGENT.md
├── PLAN.md
├── README.md
├── docker-compose.yml
├── .env.example
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── hooks/
│   │   └── package.json
│   └── api/
│       ├── main.py
│       ├── app/
│       │   ├── api/
│       │   │   ├── routes/
│       │   │   └── dependencies.py
│       │   ├── agents/
│       │   │   ├── orchestration/
│       │   │   │   └── ap_workflow_orchestrator_agent.py
│       │   │   ├── data/
│       │   │   │   ├── invoice_ingestion_agent.py
│       │   │   │   ├── invoice_extraction_agent.py
│       │   │   │   ├── invoice_normalization_agent.py
│       │   │   │   └── erp_connector_agent.py
│       │   │   ├── logic/
│       │   │   │   ├── supplier_identity_agent.py
│       │   │   │   ├── invoice_validation_agent.py
│       │   │   │   ├── purchase_order_matching_agent.py
│       │   │   │   ├── duplicate_detection_agent.py
│       │   │   │   ├── fraud_risk_scoring_agent.py
│       │   │   │   ├── approval_routing_agent.py
│       │   │   │   ├── einvoicing_compliance_agent.py
│       │   │   │   └── tenant_security_agent.py
│       │   │   ├── interface/
│       │   │   │   ├── vendor_communication_agent.py
│       │   │   │   ├── payment_status_chatbot_agent.py
│       │   │   │   ├── notification_agent.py
│       │   │   │   └── reporting_analytics_agent.py
│       │   │   └── observability/
│       │   │       ├── audit_logging_agent.py
│       │   │       ├── monitoring_agent.py
│       │   │       └── error_handler_agent.py
│       │   ├── core/
│       │   │   ├── config.py
│       │   │   ├── security.py
│       │   │   ├── events.py
│       │   │   ├── schemas.py
│       │   │   └── exceptions.py
│       │   ├── db/
│       │   │   ├── models.py
│       │   │   ├── session.py
│       │   │   └── migrations/
│       │   ├── integrations/
│       │   │   ├── ocr/
│       │   │   ├── email/
│       │   │   ├── erp/
│       │   │   │   ├── base.py
│       │   │   │   ├── priority.py
│       │   │   │   ├── odoo.py
│       │   │   │   └── mock.py
│       │   │   ├── notifications/
│       │   │   └── storage/
│       │   ├── workers/
│       │   │   ├── celery_app.py
│       │   │   └── tasks.py
│       │   └── tests/
│       └── pyproject.toml
├── packages/
│   └── shared-schemas/
└── docs/
    ├── architecture.md
    ├── security.md
    ├── api.md
    └── runbook.md
```

## Development Phases

### Phase 1 — Foundation [Week 1–2]
- [ ] Create monorepo structure.
- [ ] Configure Docker Compose with API, web, PostgreSQL, Redis, and object-storage emulator.
- [ ] Set up FastAPI backend with health checks.
- [ ] Set up Next.js dashboard shell.
- [ ] Create multi-tenant database models: Tenant, User, Vendor, Invoice, InvoiceLine, PurchaseOrder, GoodsReceipt, ApprovalFlow, AuditEvent, WorkflowState, Notification, IntegrationCredential.
- [ ] Implement environment configuration and secrets abstraction.
- [ ] Implement TenantSecurityAgent foundation with tenant-scoped authorization helpers.
- [ ] Implement AuditLoggingAgent.
- [ ] Implement MonitoringAgent base metrics.
- [ ] Implement ErrorHandlerAgent with retry classification.
- [ ] Create event schema registry and workflow state machine primitives.

### Phase 2 — Core Agents [Week 3–4]
- [ ] Build APWorkflowOrchestratorAgent.
- [ ] Build InvoiceIngestionAgent with upload and email-source mock support.
- [ ] Build InvoiceExtractionAgent with OCR provider abstraction and mock extractor.
- [ ] Build InvoiceNormalizationAgent.
- [ ] Build SupplierIdentityAgent.
- [ ] Build InvoiceValidationAgent.
- [ ] Build DuplicateDetectionAgent.
- [ ] Add unit tests for each agent.
- [ ] Add workflow integration test: upload invoice → extract → normalize → validate → duplicate check.

### Phase 3 — Matching, Approval & ERP Integration [Week 5–6]
- [ ] Build ERPConnectorAgent with one real target adapter and one mock adapter.
- [ ] Build PurchaseOrderMatchingAgent.
- [ ] Build FraudRiskScoringAgent.
- [ ] Build ApprovalRoutingAgent.
- [ ] Build EInvoicingComplianceAgent with configurable country rule modules.
- [ ] Implement approval dashboard views.
- [ ] Add integration tests for PO matching and approval routing.

### Phase 4 — Interface, Vendor Automation & Deployment [Week 7–8]
- [ ] Build NotificationAgent.
- [ ] Build VendorCommunicationAgent.
- [ ] Build PaymentStatusChatbotAgent.
- [ ] Build ReportingAnalyticsAgent.
- [ ] Complete AP dashboard UI: inbox, invoice detail, approval queue, exceptions, vendors, reports.
- [ ] Add audit log viewer.
- [ ] Add admin settings for approval rules, ERP connection, notification preferences, and OCR provider.
- [ ] Add end-to-end tests.
- [ ] Prepare production deployment manifests.
- [ ] Create runbook for support, retries, ERP sync issues, and failed invoices.

## Agent Build Order

1. **TenantSecurityAgent** — Required before sensitive AP data is accessed.
2. **AuditLoggingAgent** — Required to track all future agent actions.
3. **MonitoringAgent** — Required to observe workflows from the beginning.
4. **ErrorHandlerAgent** — Required for safe retries and workflow recovery.
5. **APWorkflowOrchestratorAgent** — Coordinates every later agent.
6. **InvoiceIngestionAgent** — First business workflow entry point.
7. **InvoiceExtractionAgent** — Converts files into machine-readable data.
8. **InvoiceNormalizationAgent** — Creates canonical invoices used by all logic agents.
9. **SupplierIdentityAgent** — Needed before validation, fraud checks, and ERP sync.
10. **InvoiceValidationAgent** — Prevents bad data from moving forward.
11. **DuplicateDetectionAgent** — High-value risk reduction early in workflow.
12. **ERPConnectorAgent** — Needed for PO/vendor/payment syncing.
13. **PurchaseOrderMatchingAgent** — Depends on invoice and ERP/PO data.
14. **FraudRiskScoringAgent** — Depends on supplier, duplicate, and invoice history signals.
15. **ApprovalRoutingAgent** — Depends on validation, matching, and risk results.
16. **EInvoicingComplianceAgent** — Can start after canonical invoice schema stabilizes.
17. **NotificationAgent** — Needed for approval and exception communication.
18. **VendorCommunicationAgent** — Depends on validation and notification foundations.
19. **PaymentStatusChatbotAgent** — Depends on security, invoice state, and payment data.
20. **ReportingAnalyticsAgent** — Built after workflow data model stabilizes.

## Dependencies Map

```text
TenantSecurityAgent ─┐
AuditLoggingAgent ───┼──> APWorkflowOrchestratorAgent
MonitoringAgent ─────┤
ErrorHandlerAgent ───┘

APWorkflowOrchestratorAgent ─> InvoiceIngestionAgent
InvoiceIngestionAgent ───────> InvoiceExtractionAgent
InvoiceExtractionAgent ──────> InvoiceNormalizationAgent
InvoiceNormalizationAgent ───> SupplierIdentityAgent
InvoiceNormalizationAgent ───> InvoiceValidationAgent
InvoiceNormalizationAgent ───> DuplicateDetectionAgent
SupplierIdentityAgent ───────> FraudRiskScoringAgent
InvoiceValidationAgent ──────> PurchaseOrderMatchingAgent
ERPConnectorAgent ───────────> PurchaseOrderMatchingAgent
DuplicateDetectionAgent ─────> FraudRiskScoringAgent
PurchaseOrderMatchingAgent ──> ApprovalRoutingAgent
FraudRiskScoringAgent ───────> ApprovalRoutingAgent
ApprovalRoutingAgent ────────> NotificationAgent
InvoiceValidationAgent ──────> VendorCommunicationAgent
ERPConnectorAgent ───────────> PaymentStatusChatbotAgent
Invoice database ────────────> ReportingAnalyticsAgent
```

## Definition of Done

### Global Definition of Done
- [ ] Agent has a single responsibility.
- [ ] Agent has typed input/output schemas.
- [ ] Agent has unit tests.
- [ ] Agent emits audit events.
- [ ] Agent emits monitoring metrics.
- [ ] Agent handles errors through ErrorHandlerAgent.
- [ ] Agent is tenant-safe.
- [ ] Agent is idempotent where applicable.
- [ ] Agent has documentation and example payloads.

### Business Workflow Definition of Done
- [ ] A tenant can upload or ingest an invoice.
- [ ] Raw invoice file is stored securely.
- [ ] Invoice fields are extracted with confidence scores.
- [ ] Invoice is normalized into canonical schema.
- [ ] Supplier is matched or flagged.
- [ ] Invoice validation runs.
- [ ] Duplicate detection runs.
- [ ] PO matching runs where applicable.
- [ ] Fraud/anomaly risk is scored.
- [ ] Approval routing creates a valid approval flow.
- [ ] Notifications are sent to approvers.
- [ ] ERP sync can push approved invoices.
- [ ] Vendor can ask for invoice/payment status with permission controls.
- [ ] AP manager can view dashboard metrics and exceptions.
- [ ] Audit trail records every critical action.

## Codex Operating Rules

- Build one agent at a time.
- Do not mix responsibilities across agents.
- When missing external credentials, implement mock adapters and clearly mark them.
- Prefer deterministic business rules over LLM decisions for finance-critical logic.
- LLM-generated messages must be reviewed or constrained by templates for vendor communication.
- Every database query must be tenant-scoped.
- Every workflow operation must include correlation IDs.
- Every integration must have retry and timeout handling.
- Never store raw secrets in logs or audit events.
