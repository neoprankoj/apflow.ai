# Pilot Readiness Review

This review is the post-PR #62 checkpoint for APFlow's demo, pilot, and production posture.

## A. Executive Summary

APFlow is now demo-ready and pilot-shaped. The private staging app can demonstrate the end-to-end AP manager workflow, vendor-safe self-service, payment-status visibility, analytics, usage metering, compliance validation, Priority connector safety gates, deterministic seed profiles, and audit proof.

APFlow is not production-ready yet. Pilot readiness still requires public access hardening, operational checks, real provider gates, customer-specific ERP validation, and counsel-reviewed legal/privacy preparation.

Domain + HTTPS remain intentionally deferred. They should be connected only after final access/public exposure hardening confirms the app is safe to place behind a real customer-facing URL.

## B. Gap Closure Table

| Gap / Area | Status | Closing PR(s) | Notes | Remaining risk |
| --- | --- | --- | --- | --- |
| Product readiness boundary | Closed | PR #51 | Demo Ready, Pilot Ready, and Production Ready are separated in the Product Readiness Gate. | Readiness must stay conservative as new integrations are added. |
| Production security guardrails | Foundation closed | PR #52 | Production rejects unsafe demo mode/reset/auth settings; RBAC, tenant isolation, and vendor-safe tests were added. | Final public access review, monitoring, incident process, and customer data policies remain. |
| Payment status foundation | Foundation closed | PR #53 | Tenant-scoped manual/mock payment status model, API, UI, vendor-safe projection, and audit events exist. | Real ERP/bank/payment status sync is not connected. |
| Real-world invoice validation | Closed | PR #54 | Discount-aware total validation now treats discounts, credits, and rebates as deductions. | More country/vendor-specific validation rules may be needed for real customer invoice variants. |
| Vendor access lifecycle | Foundation closed | PR #55 | Admin-created vendor access, hashed tokens, one-time raw token display, expiration, revocation, rotation, and audit events exist. | Real invitation delivery and support lifecycle are not connected. |
| Vendor access UX and supplier matching | Closed | PR #56 | Browser-friendly `/vendor` links and safer supplier matching make vendor access usable in QA. | Customer supplier master matching still needs validation against real tenant data. |
| Vendor payment-status chatbot | MVP closed | PR #57 | Deterministic rules-based chatbot answers vendor-safe invoice/payment questions and refuses unsafe topics. | No external LLM is used; escalation, rate limits, and support handoff still need pilot review. |
| Notification delivery abstraction | Foundation closed | PR #58 | Mock provider records delivery; Email, Slack, and Teams placeholders are safe and not configured. | Real notification providers and invitation delivery are not connected. |
| Accuracy and exception analytics | Foundation closed | PR #59 | Dashboard summarizes workflow volume, OCR/review health, blockers, approvals, payment, vendor, chatbot, and notification activity. | SLA trends, alerting, and advanced per-customer analytics are not production-grade yet. |
| Usage metering and billing foundation | Foundation closed | PR #60 | Usage events, tenant usage summary, plan placeholders, and warn-only UI exist. | Stripe/billing provider, subscription management, invoices, and enforcement are not connected. |
| E-invoicing compliance validation | Foundation closed | PR #61 | Validation-only profiles check required/recommended invoice fields and tax/VAT warnings. | No certified submission, PEPPOL, tax-authority, or government integration exists. |
| Demo and pilot seed profiles | Closed | PR #62 | Deterministic data packs support clean, AP manager, vendor, Priority, compliance, and analytics-rich demos. | Seed/reset must remain disabled after use and blocked in production. |

## C. Current Demo-Ready Definition

APFlow can safely demo:

- AP manager workflow: upload, OCR, review/corrections, process, approval, export, and audit.
- OCR extraction with clear diagnostics and fallback support.
- Approval decisions with readable status messages.
- Mock ERP export only.
- Audit Trail proof for major workflow actions.
- Manual/mock payment status.
- Vendor access lifecycle with one-time token handling, revoke, rotate, and browser vendor page.
- Rules-based vendor payment-status chatbot with safe refusals.
- Mock notification delivery and Email/Slack/Teams placeholders.
- Accuracy and exception analytics.
- Usage metering with warn-only plan placeholders.
- Validation-only e-invoicing compliance checks.
- Priority connector safety ladder: readiness, mapping, validation, dry-run, import plan, controlled APFlow-only import, imported records, and audit proof.
- Demo seed profiles for repeatable demo states.

## D. Current Pilot-Readiness Blockers

The app is pilot-shaped, but real customer pilot use is still blocked by:

- Domain + HTTPS are not connected yet.
- Public access hardening still needs a final review.
- Real notification providers are not configured.
- Real ERP payment status sync is not connected.
- Real Priority writes are not enabled.
- Customer-specific Priority mappings have not been validated with real tenant data.
- Production vendor invitation delivery is not connected to an email provider.
- Billing provider is not connected.
- Certified e-invoicing or tax-authority submission is not implemented.
- Backup/restore drill should be repeated before pilot.
- Operations health script exists, but external uptime/alert provider, log retention, and scheduled/offsite backup monitoring are still future work.
- Legal, privacy, and customer data handling drafts exist, but qualified counsel review and customer-specific terms are still required.

## E. Current Production-Readiness Blockers

APFlow must not be claimed as production-ready while these remain true:

- `APP_ENV` is staging, not production.
- Demo mode exists for staging.
- Domain + HTTPS are not configured.
- No real secrets rotation procedure is finalized.
- No real notification providers are connected.
- No real billing is connected.
- No certified e-invoicing is implemented.
- No production monitoring/alerting is finalized.
- No full incident response process is documented and rehearsed.
- No real customer data processing agreement, privacy policy, or SLA is finalized.
- No production vendor invitation flow is connected.
- No real ERP write approval gate has been tested with a customer tenant.

## F. Recommended Next Sequence

Recommended next work:

1. PR #64 - Public Access / Domain / HTTPS Readiness Plan. This is a planning, checklist, and template PR only.
2. PR #65 - Backup / Restore / Disaster Recovery Drill. This should prove a non-destructive staging restore path before public access work.
3. PR #66 - Backup / Restore Scripts DB Role Detection Fix.
4. PR #67 - Public Port / Firewall Hardening Checklist.
5. PR #68 - Localhost-Only Service Binding / Compose Hardening.
6. PR #69 - Security Headers / Reverse Proxy Hardening Plan.
7. Later - Real Notification Provider Configuration Gate.
8. Later - Customer-Specific Priority Mapping Pilot Checklist.
9. Later - Real ERP Payment Sync Read-Only Foundation.
10. PR #70 - Legal / Privacy / Data Handling Pack.
11. PR #71 - Monitoring / Operations Health Foundation.
12. Later - Domain + HTTPS Deployment.

Domain + HTTPS remains later. PR #64 and PR #67 prepare access and firewall hardening checklists. PR #68 hardens staging Compose bind addresses. PR #69 adds reverse proxy and security-header planning/templates. PR #70 adds legal/privacy/data-handling draft documents. PR #71 adds read-only staging operations health checks, but it does not connect external monitoring, alerting, log aggregation, HTTPS, or live infrastructure changes.

## G. Go / No-Go Checklist For Pilot

- [ ] Demo seed profile selected.
- [ ] `ALLOW_DEMO_RESET=false`.
- [ ] Product Readiness reviewed.
- [ ] Backup completed.
- [ ] Restore tested or documented.
- [ ] Operations health check reviewed.
- [ ] Security guardrails reviewed.
- [ ] Vendor access tested.
- [ ] Vendor chatbot tested.
- [ ] Mock notifications tested.
- [ ] Priority writes disabled unless explicitly approved.
- [ ] Customer data boundaries confirmed.
- [ ] Legal/privacy/data handling pack reviewed with counsel before real customer data.
- [ ] Domain/HTTPS status confirmed.
- [ ] Pilot limitations explained to the customer.

## H. What Not To Claim

Do not claim:

- APFlow is production-ready.
- APFlow legal/privacy documents are lawyer-reviewed.
- APFlow is GDPR/SOC 2/ISO certified.
- APFlow is certified for e-invoicing.
- APFlow performs real ERP writeback until tested and approved for the customer tenant.
- APFlow sends real Email, Slack, or Teams notifications yet.
- Billing is live.
- Tax-authority submission is available.
- AP is fully automated without human review.
