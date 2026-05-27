# Legal / Privacy / Data Handling Pack

## A. Purpose

This pack gives APFlow founder/operators a legal, privacy, and data-handling readiness baseline for demos and future pilots.

Important limits:

- These are draft operational and legal-readiness documents only.
- This is not legal advice.
- Qualified counsel must review these materials before real customer use, production use, or customer contracts.
- APFlow is not production-ready yet.
- Certified e-invoicing, tax authority submission, PEPPOL submission, and government submission are not implemented.

## B. Current Product Status

- APFlow is demo-ready and pilot-shaped.
- APFlow is not production-ready.
- Staging Domain + HTTPS are not connected yet.
- Real billing is not connected.
- Real notification providers are not connected.
- Certified e-invoicing and tax authority submission are not implemented.
- Priority writes are disabled.
- Domain + HTTPS remain deferred until the separate approved rollout.

## C. Data Categories APFlow May Process

APFlow may process or store these data categories during invoice workflows:

- Invoice documents, PDFs, and images.
- OCR extracted invoice text.
- Supplier and vendor names.
- Supplier and vendor tax IDs.
- Buyer, customer, and company names.
- Invoice numbers, dates, currencies, totals, subtotals, and tax amounts.
- Invoice line items.
- Purchase orders and purchase order references.
- Approval workflow metadata.
- User names, emails, roles, and tenant membership.
- Audit events.
- Payment status records.
- Vendor portal access metadata.
- Vendor chatbot questions and answers.
- Notification delivery metadata.
- Usage metering events.
- Compliance validation results.
- ERP mapping and configuration metadata.

## D. Sensitive Data Notes

- Invoice documents can contain personal data, confidential business data, supplier banking references, tax identifiers, addresses, or contract-sensitive line items.
- Tax IDs, payment references, bank details, and supplier identifiers need careful handling.
- Vendor access links and raw vendor tokens must be treated as sensitive access credentials.
- Logs, audit events, support notes, screenshots, and analytics should avoid raw secrets, bearer tokens, vendor raw tokens, token hashes, API keys, webhook URLs, and full sensitive invoice text.
- Real customer data should not be uploaded or processed until pilot terms, data handling responsibilities, and customer approvals are agreed in writing.

## E. Controller / Processor Positioning Draft

Draft operating assumption:

- The customer or APFlow tenant is likely the data controller for its business invoice data.
- APFlow is likely a processor or service provider for hosted invoice processing.
- Final legal roles depend on contract terms, customer location, data subject location, jurisdiction, deployment model, and actual provider configuration.
- Data processing terms, a DPA, subprocessor list, retention commitments, incident notice terms, and deletion terms are needed before a real customer pilot.

Counsel must validate this positioning before it is used in customer-facing legal documents.

## F. Data Flow Summary

1. A user uploads an invoice document.
2. The document is stored in APFlow document storage.
3. An OCR provider extracts text and structured field candidates.
4. APFlow normalizes, validates, and scores invoice fields.
5. Human corrections may be submitted for missing or low-confidence fields.
6. Approval workflow records and audit events are created.
7. Mock or real ERP adapters may exchange data depending on configuration and safety gates.
8. Payment status may be synced from a future provider or updated manually.
9. The vendor portal can expose a vendor-safe subset of invoice and payment data.
10. The vendor chatbot answers from vendor-safe payment and invoice data only.
11. Notifications may be recorded or sent depending on provider configuration.
12. Usage and analytics aggregate operational metrics for tenant-level visibility.

## G. Third-Party / Subprocessor Inventory Draft

| Provider | Purpose | Current status | Data involved | Notes |
| --- | --- | --- | --- | --- |
| OCR.space / OCR provider | Invoice OCR extraction | Active when configured in staging | Invoice documents and extracted text | OCR.space credentials are environment-only; provider diagnostics must not expose keys. |
| Azure Document Intelligence | Future OCR provider if configured | Placeholder / future | Invoice documents and extracted fields | Not active unless credentials and provider selection are configured. |
| Priority ERP | Future/customer ERP integration | Placeholder / future | Vendors, purchase orders, invoice export data, mapping metadata | Priority writes remain disabled unless separately approved, configured, and tested. |
| Notification provider placeholder | Future Email, Slack, or Teams delivery | Placeholder / future | Recipient metadata and message content | No real external delivery is connected today. |
| Hosting provider / VPS | Infrastructure hosting | Active for staging | Application data, logs, database, uploaded documents, backups | Requires operational hardening before production. |
| GitHub | Source control and CI | Active for code/CI | Source code, CI metadata, pull requests | Do not commit secrets, customer data, real invoices, or `.env.staging`. |

This inventory is a draft. It must be reviewed and updated before customer contracts or production use.

## H. Data Retention Draft

Draft retention placeholders:

- Uploaded documents retention: configurable/future policy; automated lifecycle deletion is not fully implemented yet.
- Audit events retention: configurable/future policy; currently retained for operational traceability.
- Vendor access token metadata retention: retain until revoked or expired plus an agreed retention period.
- Usage events retention: retain for an operational analytics period to be defined before production.
- Backups retention: staging/manual for now; scheduled offsite encrypted backup retention is not fully implemented yet.
- Deletion requests: manual process for now; automated tenant-wide deletion workflow is not fully implemented yet.

Before a real customer pilot, define retention periods, backup retention, deletion SLAs, restoration constraints, and audit retention exceptions with counsel and the customer.

## I. Vendor Access And Token Handling Policy

- Raw vendor tokens are shown once on create or rotate.
- Token hashes are stored; raw tokens are not returned by list/read APIs.
- Revoked or expired tokens fail.
- Vendor views must remain vendor-safe and scoped to that vendor's allowed data.
- Vendor links must use HTTPS before real external sharing.
- Rotate or revoke tokens if exposed in screenshots, browser history, logs, support notes, chat, or documentation.
- Do not email raw tokens until notification provider security, delivery ownership, and customer-approved invitation flows are reviewed.

## J. Security Controls Already Implemented

- Auth/RBAC foundation.
- Tenant isolation tests and tenant-scoped repositories.
- Product Readiness checks.
- Production startup guardrails.
- Vendor-safe data boundaries.
- Vendor token hashing.
- Audit trail.
- Local-only staging port binding after PR #68.
- Backup/restore drill documentation and helper scripts.
- Mock notification provider.
- Public access, firewall, reverse proxy, and readiness documents.

These controls are readiness foundations. They are not a claim of GDPR, SOC 2, ISO, or production compliance.

## K. Current Known Limitations

- No production domain or HTTPS yet.
- No real legal review yet.
- No real DPA or customer contract yet.
- No automated retention/deletion workflow.
- No production monitoring/alerting yet.
- No scheduled offsite backups yet.
- No certified e-invoicing submission.
- No tax authority submission.
- No real billing.
- No real notification provider.
- No real Priority writes.

## L. Pilot Data Handling Rules

- Use synthetic/demo data unless written pilot approval exists.
- Do not upload sensitive customer documents until terms are agreed.
- Keep `ALLOW_DEMO_RESET=false` after setup or seeding.
- Use vendor access only over HTTPS after the domain deployment.
- Avoid sharing raw access tokens in insecure channels.
- Document the pilot tenant owner and admins.
- Document who can access pilot data.
- Run a backup before importing pilot data.
- Keep Priority writes disabled unless a separate customer-specific approval, mapping validation, backup, rollback plan, and operational signoff exist.

## M. Incident Response Basics

First-response checklist:

1. Identify affected tenant, users, records, systems, and time window.
2. Disable affected access or revoke/rotate exposed vendor tokens if needed.
3. Rotate exposed credentials, API keys, webhook secrets, bearer tokens, or vendor tokens.
4. Preserve logs, audit events, database state, and relevant deployment metadata.
5. Notify stakeholders according to contract terms and legal advice.
6. Restore from backup if data corruption occurred.
7. Document the incident timeline, root cause, fix, validation, and prevention steps.

Do not delete evidence before counsel and operations decide what must be preserved.

## N. What Not To Claim

Do not claim:

- APFlow is production-ready.
- These documents are lawyer-reviewed.
- APFlow is GDPR compliant.
- APFlow is SOC 2 certified.
- APFlow is ISO certified.
- APFlow is a certified e-invoicing provider.
- APFlow submits invoices to tax authorities.
- APFlow has real billing connected.
- APFlow sends real Email, Slack, or Teams notifications unless configured later.
- APFlow performs real ERP writeback unless specifically enabled, tested, approved, and documented for that customer.
