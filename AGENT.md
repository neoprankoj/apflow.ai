# AGENT.md — AI Agents Registry

## Overview
APFlow AI is a production-grade AI Accounts Payable and E-Invoicing Automation SaaS for mid-market firms processing 500–50,000 invoices per month. The agent ecosystem automates invoice intake, OCR/document extraction, e-invoice validation, PO/receipt matching, duplicate and fraud detection, approval routing, vendor communication, ERP sync, payment-status responses, notifications, logging, and error recovery.

The system follows a layered architecture:

- **Orchestration Layer:** Coordinates workflows, state transitions, retries, and agent communication.
- **Data Layer:** Handles ingestion, extraction, normalization, storage, and ERP connectivity.
- **Logic Layer:** Performs business validation, matching, duplicate checks, fraud scoring, approval routing, and compliance checks.
- **Interface Layer:** Provides user-facing dashboards, vendor chatbot interactions, alerts, and reporting.
- **Observability Layer:** Monitors workflows, system health, audit trails, and error handling.

Agents follow SRP. Each agent has a single responsibility and communicates through typed events, durable queues, and database-backed workflow states.

---

## Agent Registry

| Agent Name | Role | Layer | Type | Status |
|------------|------|-------|------|--------|
| APWorkflowOrchestratorAgent | Coordinates the full AP workflow from invoice intake to ERP/payment state | Orchestration | Hybrid | Planned |
| InvoiceIngestionAgent | Receives invoices from email, upload, API, and e-invoicing channels | Data | Autonomous | Planned |
| InvoiceExtractionAgent | Extracts structured invoice fields from PDFs, scans, images, and XML/e-invoice formats | Data | Autonomous | Planned |
| InvoiceNormalizationAgent | Converts extracted invoice data into the internal canonical invoice schema | Data | Autonomous | Planned |
| SupplierIdentityAgent | Matches invoices to known vendors and flags unknown supplier records | Logic | Autonomous | Planned |
| InvoiceValidationAgent | Validates invoice completeness, tax fields, totals, currency, and business rules | Logic | Autonomous | Planned |
| PurchaseOrderMatchingAgent | Performs 2-way and 3-way PO, receipt, and invoice matching | Logic | Autonomous | Planned |
| DuplicateDetectionAgent | Detects possible duplicate invoices, duplicate payments, and suspicious re-submissions | Logic | Autonomous | Planned |
| FraudRiskScoringAgent | Scores invoices and supplier changes for fraud/anomaly risk | Logic | Autonomous | Planned |
| ApprovalRoutingAgent | Routes invoices to the correct approvers based on policy, amount, entity, department, and exception state | Logic | Hybrid | Planned |
| VendorCommunicationAgent | Handles supplier questions and sends missing-information requests | Interface | Hybrid | Planned |
| PaymentStatusChatbotAgent | Answers vendor and internal user questions about invoice/payment status | Interface | Interactive | Planned |
| ERPConnectorAgent | Syncs vendors, POs, invoices, approvals, GL codes, and payment statuses with ERP/accounting systems | Data | Autonomous | Planned |
| EInvoicingComplianceAgent | Validates country-specific e-invoicing rules and structured invoice requirements | Logic | Autonomous | Planned |
| NotificationAgent | Sends notifications to approvers, AP staff, vendors, and admins | Interface | Autonomous | Planned |
| ReportingAnalyticsAgent | Produces operational dashboards, AP KPIs, aging reports, and exception analytics | Interface | Interactive | Planned |
| AuditLoggingAgent | Records immutable workflow events, user actions, agent decisions, and system changes | Observability | Autonomous | Planned |
| MonitoringAgent | Tracks service health, queues, latency, extraction accuracy, ERP sync health, and agent failures | Observability | Autonomous | Planned |
| ErrorHandlerAgent | Centralized workflow failure handling, retry policies, dead-letter queues, and escalation | Observability | Autonomous | Planned |
| TenantSecurityAgent | Enforces tenant isolation, RBAC, permissions, secrets access, and security policies | Logic | Autonomous | Planned |

---

## Agent Specifications

### APWorkflowOrchestratorAgent
- **Responsibility:** Coordinate invoice lifecycle workflows across all AP automation agents.
- **Trigger:** New invoice received, manual user action, scheduled retry, ERP sync event, approval update, or exception event.
- **Input Schema:**
```json
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "workflow_id": "uuid",
  "event_type": "invoice.received | invoice.extracted | invoice.validated | invoice.exception | approval.updated | erp.synced",
  "entity_id": "uuid",
  "payload": {}
}
```
- **Output Schema:**
```json
{
  "workflow_id": "uuid",
  "next_agent": "string",
  "state": "string",
  "status": "queued | running | completed | failed | waiting_for_human",
  "context": {}
}
```
- **Dependencies:** Message queue, workflow state database, AuditLoggingAgent, ErrorHandlerAgent, NotificationAgent.
- **Codex Instructions:** Build this as the central durable workflow coordinator. Use idempotent event handling, explicit workflow states, retry counters, dead-letter routing, and agent dispatch through typed events. Do not embed extraction, validation, matching, or notification logic inside this agent.

### InvoiceIngestionAgent
- **Responsibility:** Receive invoices from supported channels and create raw invoice records.
- **Trigger:** Email webhook, file upload, API request, SFTP file drop, e-invoice network webhook, or manual admin import.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "source": "email | upload | api | sftp | einvoice_network",
  "file_url": "string",
  "metadata": {
    "sender_email": "string",
    "received_at": "datetime",
    "original_filename": "string"
  }
}
```
- **Output Schema:**
```json
{
  "raw_invoice_id": "uuid",
  "tenant_id": "uuid",
  "storage_url": "string",
  "mime_type": "string",
  "source": "string",
  "status": "stored"
}
```
- **Dependencies:** Object storage, database, email/API/SFTP adapters, virus scanning service, AuditLoggingAgent.
- **Codex Instructions:** Implement source adapters separately. Store raw files immutably. Generate checksum hashes for duplicate file detection. Reject unsupported file types. Emit `invoice.received` event after successful storage.

### InvoiceExtractionAgent
- **Responsibility:** Extract invoice fields and line items from raw invoice files.
- **Trigger:** `invoice.received` event.
- **Input Schema:**
```json
{
  "raw_invoice_id": "uuid",
  "tenant_id": "uuid",
  "storage_url": "string",
  "mime_type": "string"
}
```
- **Output Schema:**
```json
{
  "extraction_id": "uuid",
  "raw_invoice_id": "uuid",
  "fields": {
    "invoice_number": "string",
    "supplier_name": "string",
    "supplier_tax_id": "string",
    "invoice_date": "date",
    "due_date": "date",
    "currency": "string",
    "subtotal": "decimal",
    "tax_total": "decimal",
    "grand_total": "decimal"
  },
  "line_items": [],
  "confidence": {},
  "needs_review": "boolean"
}
```
- **Dependencies:** OCR/document AI provider, XML parser, PDF parser, object storage, AuditLoggingAgent.
- **Codex Instructions:** Support PDF, image, XML, UBL, Factur-X/ZUGFeRD-style structured files where possible. Store field-level confidence. Never overwrite raw invoice data. Emit `invoice.extracted`.

### InvoiceNormalizationAgent
- **Responsibility:** Convert extracted data into the canonical APFlow invoice schema.
- **Trigger:** `invoice.extracted` event.
- **Input Schema:**
```json
{
  "extraction_id": "uuid",
  "tenant_id": "uuid",
  "fields": {},
  "line_items": [],
  "confidence": {}
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "tenant_id": "uuid",
  "canonical_invoice": {},
  "normalization_warnings": []
}
```
- **Dependencies:** Database, currency/date/tax normalization utilities, tenant settings.
- **Codex Instructions:** Normalize dates, decimals, currencies, tax IDs, vendor names, payment terms, and line-item fields. Do not perform business approvals or fraud checks here.

### SupplierIdentityAgent
- **Responsibility:** Match an invoice to a known vendor or create an exception for unknown supplier review.
- **Trigger:** `invoice.normalized` event or vendor master sync update.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "invoice_id": "uuid",
  "supplier_name": "string",
  "supplier_tax_id": "string",
  "bank_account_hash": "string"
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "vendor_id": "uuid | null",
  "match_confidence": "decimal",
  "status": "matched | possible_match | unknown_vendor"
}
```
- **Dependencies:** Vendor master database, ERPConnectorAgent, fuzzy matching utilities, AuditLoggingAgent.
- **Codex Instructions:** Implement exact, fuzzy, and tax-ID-based matching. Flag bank-account changes as separate risk signals for FraudRiskScoringAgent.

### InvoiceValidationAgent
- **Responsibility:** Validate invoices against tenant rules, invoice completeness, mathematical totals, tax rules, and required fields.
- **Trigger:** `supplier.matched` event or `invoice.normalized` event.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "invoice_id": "uuid",
  "canonical_invoice": {},
  "vendor_id": "uuid | null"
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "validation_status": "passed | failed | needs_review",
  "errors": [],
  "warnings": []
}
```
- **Dependencies:** Tenant rule engine, EInvoicingComplianceAgent, AuditLoggingAgent.
- **Codex Instructions:** Validate required fields, tax totals, grand totals, currency, supplier identity, invoice date, due date, invoice number, and tenant-specific policies. Emit explicit validation errors.

### PurchaseOrderMatchingAgent
- **Responsibility:** Perform 2-way and 3-way matching between invoice, PO, and goods receipt data.
- **Trigger:** `invoice.validated` event for PO-backed invoices.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "invoice_id": "uuid",
  "vendor_id": "uuid",
  "po_number": "string",
  "invoice_lines": []
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "match_status": "matched | variance | missing_po | missing_receipt | needs_review",
  "variance_details": [],
  "recommended_action": "auto_approve | route_exception | request_review"
}
```
- **Dependencies:** ERPConnectorAgent, PO database/cache, receipt database/cache, tenant tolerance rules.
- **Codex Instructions:** Support configurable tolerances by amount, percentage, quantity, item, department, and supplier. Do not approve invoices directly; send recommendation to ApprovalRoutingAgent.

### DuplicateDetectionAgent
- **Responsibility:** Detect duplicate invoices and duplicate payment risks.
- **Trigger:** `invoice.normalized`, `invoice.validated`, and pre-payment events.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "invoice_id": "uuid",
  "vendor_id": "uuid",
  "invoice_number": "string",
  "invoice_date": "date",
  "grand_total": "decimal",
  "file_checksum": "string"
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "duplicate_score": "decimal",
  "possible_duplicates": [],
  "status": "clear | possible_duplicate | likely_duplicate"
}
```
- **Dependencies:** Invoice database, vector/fuzzy matching utilities, AuditLoggingAgent.
- **Codex Instructions:** Compare exact invoice numbers, normalized invoice numbers, amounts, supplier IDs, dates, bank hashes, file hashes, and near-duplicate OCR text. Return score and evidence.

### FraudRiskScoringAgent
- **Responsibility:** Score invoices and supplier events for fraud/anomaly risk.
- **Trigger:** Supplier match, duplicate scan, vendor master change, bank account change, or pre-payment review.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "invoice_id": "uuid",
  "vendor_id": "uuid",
  "signals": {
    "duplicate_score": "decimal",
    "bank_change_recent": "boolean",
    "new_vendor": "boolean",
    "amount_outlier": "boolean"
  }
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "risk_score": "decimal",
  "risk_level": "low | medium | high | critical",
  "reasons": [],
  "recommended_action": "continue | manager_review | block_payment"
}
```
- **Dependencies:** Invoice history, vendor history, tenant thresholds, anomaly detection service.
- **Codex Instructions:** Build deterministic rules first, then allow optional ML/anomaly scoring. Every risk score must include explainable reasons.

### ApprovalRoutingAgent
- **Responsibility:** Route invoices to approvers based on rules and exception state.
- **Trigger:** Matching result, validation result, fraud result, manual AP action.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "invoice_id": "uuid",
  "amount": "decimal",
  "department": "string",
  "cost_center": "string",
  "match_status": "string",
  "risk_level": "string"
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "approval_flow_id": "uuid",
  "assigned_approvers": [],
  "status": "pending_approval | auto_approved | escalated | rejected"
}
```
- **Dependencies:** Tenant approval policies, user directory, NotificationAgent, AuditLoggingAgent.
- **Codex Instructions:** Implement policy-based routing. Support sequential and parallel approvals, escalation timers, delegation, and approval limits. Do not send notifications directly; call NotificationAgent.

### VendorCommunicationAgent
- **Responsibility:** Communicate with suppliers for missing information, invoice rejections, clarification, and document requests.
- **Trigger:** Validation failure, AP user action, missing data event, vendor portal message.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "vendor_id": "uuid",
  "invoice_id": "uuid",
  "communication_type": "missing_info | rejection | clarification | status_update",
  "context": {}
}
```
- **Output Schema:**
```json
{
  "message_id": "uuid",
  "vendor_id": "uuid",
  "invoice_id": "uuid",
  "status": "drafted | sent | failed | waiting_for_vendor"
}
```
- **Dependencies:** Email service, vendor portal, LLM provider, NotificationAgent, AuditLoggingAgent.
- **Codex Instructions:** Generate concise vendor-safe messages. Never reveal internal fraud scores or private approval notes. Use templates and tenant branding.

### PaymentStatusChatbotAgent
- **Responsibility:** Answer payment-status questions for vendors and internal users.
- **Trigger:** Vendor portal chat, internal dashboard chat, API call.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "user_id": "uuid | null",
  "vendor_id": "uuid | null",
  "message": "string",
  "auth_context": {}
}
```
- **Output Schema:**
```json
{
  "response": "string",
  "related_invoice_ids": [],
  "confidence": "decimal",
  "requires_human": "boolean"
}
```
- **Dependencies:** Invoice database, payment status records, TenantSecurityAgent, LLM provider.
- **Codex Instructions:** Enforce permissions before returning invoice/payment details. Only provide status, due date, missing information, and next action. Escalate ambiguous cases.

### ERPConnectorAgent
- **Responsibility:** Sync APFlow data with ERP/accounting systems.
- **Trigger:** Scheduled sync, manual sync, invoice approved, vendor update, PO cache refresh.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "connector_type": "priority | odoo | zoho_books | netsuite | quickbooks | generic_api",
  "operation": "sync_vendors | sync_pos | push_invoice | update_payment_status",
  "payload": {}
}
```
- **Output Schema:**
```json
{
  "sync_id": "uuid",
  "operation": "string",
  "status": "success | partial | failed",
  "records_processed": "integer",
  "errors": []
}
```
- **Dependencies:** ERP APIs, secrets manager, queue, retry manager, AuditLoggingAgent, ErrorHandlerAgent.
- **Codex Instructions:** Start with one connector adapter, preferably Priority ERP or Odoo. Use an adapter interface so future ERPs can be added without changing core workflow logic.

### EInvoicingComplianceAgent
- **Responsibility:** Validate structured invoice compliance by country, tenant, and format.
- **Trigger:** Invoice extraction, normalization, or country-specific validation event.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "invoice_id": "uuid",
  "country_code": "string",
  "invoice_format": "pdf | xml | ubl | facturx | other",
  "canonical_invoice": {}
}
```
- **Output Schema:**
```json
{
  "invoice_id": "uuid",
  "compliance_status": "passed | failed | not_applicable | needs_review",
  "violations": [],
  "country_code": "string"
}
```
- **Dependencies:** Compliance rule registry, XML validators, tenant country settings.
- **Codex Instructions:** Implement rules as configuration modules by country. Do not hardcode all countries in core logic. Return actionable violations.

### NotificationAgent
- **Responsibility:** Send user, vendor, and admin notifications across channels.
- **Trigger:** Approval request, exception event, escalation, vendor message, system alert.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "recipient_type": "user | vendor | admin",
  "recipient_id": "uuid",
  "channel": "email | in_app | slack | teams | webhook",
  "template_key": "string",
  "payload": {}
}
```
- **Output Schema:**
```json
{
  "notification_id": "uuid",
  "status": "sent | failed | skipped",
  "channel": "string"
}
```
- **Dependencies:** Email provider, in-app notification service, Slack/Teams/webhook adapters, AuditLoggingAgent.
- **Codex Instructions:** Centralize all outbound notifications here. Implement templating, rate limits, tenant preferences, and delivery logs.

### ReportingAnalyticsAgent
- **Responsibility:** Produce AP dashboards, exception reports, cycle-time metrics, vendor aging, and automation KPIs.
- **Trigger:** Dashboard request, scheduled report, CFO/controller export request.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "report_type": "ap_dashboard | aging | exceptions | automation_roi | approval_cycle_time",
  "filters": {}
}
```
- **Output Schema:**
```json
{
  "report_id": "uuid",
  "metrics": {},
  "rows": [],
  "generated_at": "datetime"
}
```
- **Dependencies:** Analytics database, invoice database, approval records, export service.
- **Codex Instructions:** Use read-optimized queries. Support CSV export and dashboard API responses. Never mutate workflow state.

### AuditLoggingAgent
- **Responsibility:** Record immutable audit events for every workflow, user action, agent decision, and data mutation.
- **Trigger:** Any significant workflow event, user action, integration event, or security event.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "actor_type": "user | agent | system | vendor",
  "actor_id": "string",
  "action": "string",
  "entity_type": "string",
  "entity_id": "uuid",
  "metadata": {}
}
```
- **Output Schema:**
```json
{
  "audit_event_id": "uuid",
  "status": "recorded"
}
```
- **Dependencies:** Append-only audit database/table, timestamp service.
- **Codex Instructions:** Make audit logging append-only. Do not allow updates or deletes through normal application code. Include correlation IDs.

### MonitoringAgent
- **Responsibility:** Monitor system health, queues, workflow latency, extraction confidence, ERP sync health, and agent failure rates.
- **Trigger:** Scheduled checks, metrics event, health endpoint call, error event.
- **Input Schema:**
```json
{
  "tenant_id": "uuid | null",
  "metric_event": "string",
  "value": "number",
  "metadata": {}
}
```
- **Output Schema:**
```json
{
  "metric_id": "uuid",
  "status": "recorded | alert_triggered",
  "alerts": []
}
```
- **Dependencies:** Metrics backend, logs backend, NotificationAgent, ErrorHandlerAgent.
- **Codex Instructions:** Implement structured metrics and alert thresholds. Track per-agent success/failure rates, queue depth, OCR confidence, ERP sync failures, and approval bottlenecks.

### ErrorHandlerAgent
- **Responsibility:** Handle workflow errors, retries, dead-letter queues, manual escalation, and failure classification.
- **Trigger:** Agent failure event, timeout, queue failure, integration error, validation exception.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "workflow_id": "uuid",
  "agent_name": "string",
  "error_type": "string",
  "error_message": "string",
  "retry_count": "integer",
  "context": {}
}
```
- **Output Schema:**
```json
{
  "resolution": "retry | escalate | dead_letter | ignore | manual_review",
  "next_attempt_at": "datetime | null",
  "notification_required": "boolean"
}
```
- **Dependencies:** Workflow database, queue, NotificationAgent, AuditLoggingAgent, MonitoringAgent.
- **Codex Instructions:** Use error categories: transient, validation, integration, security, unknown. Implement exponential backoff and max retry policies. Escalate persistent failures.

### TenantSecurityAgent
- **Responsibility:** Enforce tenant isolation, RBAC, permissions, authentication context, and sensitive data access.
- **Trigger:** API request, agent data access request, chatbot request, admin action, integration call.
- **Input Schema:**
```json
{
  "tenant_id": "uuid",
  "actor_id": "uuid",
  "actor_type": "user | vendor | agent | system",
  "resource": "string",
  "action": "read | write | approve | export | admin",
  "context": {}
}
```
- **Output Schema:**
```json
{
  "allowed": "boolean",
  "reason": "string",
  "policy_id": "string"
}
```
- **Dependencies:** Auth provider, RBAC database, secrets manager, AuditLoggingAgent.
- **Codex Instructions:** Enforce permissions before database reads/writes and chatbot responses. Implement tenant-scoped queries and deny-by-default policies.
