# Customer Data Handling Summary

This is a draft customer-facing summary for pilot conversations. It is not legal advice, not a contract, and not a production compliance claim. Qualified counsel must review it before it is used with real customer agreements.

## What APFlow Processes

APFlow helps accounts payable teams upload invoices, extract invoice fields with OCR, review/correct extracted data, route approvals, track payment status, show vendor-safe invoice status, and keep an audit trail.

APFlow may process:

- Invoice PDFs and images.
- Extracted invoice text and invoice fields.
- Supplier/vendor names and tax IDs.
- Buyer/customer company names.
- Invoice numbers, dates, currency, totals, tax amounts, and line items.
- Purchase order references.
- AP user names, emails, roles, and approval actions.
- Vendor access metadata.
- Vendor chatbot questions and answers.
- Audit events, usage events, and operational analytics.

## What APFlow Does Not Do Yet

APFlow currently does not provide:

- Production-ready hosted service status.
- Production Domain + HTTPS on staging.
- Certified e-invoicing or tax authority submission.
- Real billing or payment card processing.
- Real Email, Slack, or Teams delivery.
- Real ERP writeback to Priority unless separately approved, configured, and tested.
- Lawyer-approved legal terms, DPA, SLA, or production privacy documentation.

## Vendor-Safe Access

APFlow includes a vendor portal foundation that shows vendors only a limited, vendor-safe subset of invoice and payment-status data. Vendor views are designed not to expose internal fraud scoring, approval-policy internals, audit logs, ERP sync logs, other vendors' invoices, token details, or internal payment notes.

Vendor access links and tokens must be treated as sensitive. Real external vendor links should use HTTPS and should not be shared through insecure channels.

## Payment-Status Chatbot Safety

The vendor chatbot is rules-based and answers from vendor-safe invoice and payment-status data. It refuses unsupported or internal questions and does not expose fraud/risk reasons, internal notes, raw provider payloads, or unrelated vendor data.

## Where Data Is Stored In Staging

Current staging uses APFlow's VPS-based Docker runtime with PostgreSQL persistence and document storage configured for the staging environment. Internal Docker service ports have been hardened behind localhost/internal networking, and public Domain + HTTPS remains deferred.

Staging is not production. Real customer data should not be uploaded until pilot terms, data handling responsibilities, access rules, and support contacts are agreed in writing.

## Backup / Restore Status

APFlow has a documented staging backup/restore drill and helper scripts. A restore drill has been proven for staging. Production-grade scheduled offsite encrypted backups, retention periods, deletion workflows, and customer-specific restoration expectations still need to be finalized before production.

## Current Limitations

- APFlow is demo-ready and pilot-shaped, but not production-ready.
- Counsel review is still required.
- No final DPA, customer contract, production privacy policy, or SLA exists yet.
- Domain + HTTPS are not connected yet.
- Automated retention and deletion are not fully implemented yet.
- Production monitoring and alerting are not finalized.
- Real notification providers, billing, certified tax submission, and real Priority writes are not enabled.

## Pilot Restrictions

- Use synthetic/demo data unless written pilot approval exists.
- Do not upload sensitive customer documents until pilot terms are agreed.
- Document authorized pilot users and tenant admins.
- Run a backup before importing pilot data.
- Use vendor links only over HTTPS after domain deployment.
- Rotate or revoke any access token that appears in screenshots, logs, support notes, chat, or email.

## Contact / Next Steps Placeholder

Before a real pilot, confirm:

- Pilot sponsor:
- Customer legal/privacy contact:
- APFlow operator contact:
- Support/incident contact:
- Approved data categories:
- Pilot start/end dates:
- Exit and cleanup expectations:
