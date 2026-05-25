# Production Readiness Checklist

This checklist separates what APFlow can safely claim today from what still blocks pilot and production use.

## Readiness Levels

### Demo Ready

APFlow is demo ready when a founder/operator can run a controlled AP manager walkthrough without real ERP writes or public production access.

Required:

- App health and readiness checks pass.
- Auth/RBAC is enabled for staging.
- Invoice upload and OCR extraction work.
- OCR errors are clear and do not expose secrets.
- Human review and corrections work.
- Approval Inbox works.
- Vendor-safe preview works.
- Mock ERP export works.
- Payment status foundation is available for manual/mock APFlow tracking.
- Vendor payment-status chatbot foundation is available and rules-based, but production escalation and abuse controls are still needed.
- Audit Trail proves the workflow.
- Demo readiness docs and runbook are available.
- Priority writes are disabled.

Current expected staging result: Demo Ready should be ready or mostly ready.

### Pilot Ready

APFlow is pilot ready when a real customer can use a constrained environment with production-grade access, vendor lifecycle, notifications, and ERP posture.

Current expected staging result: Pilot Ready is not ready.

Current pilot blockers:

- Production access hardening is not complete.
- Tenant isolation and vendor-safe guardrail tests must stay in the release gate.
- Domain/HTTPS are intentionally deferred.
- Vendor access lifecycle foundation now exists: token hashing, one-time token display, expiration, revocation, rotation, last-used tracking, and audit events.
- Real vendor invitation delivery and support operations are still missing.
- Payment status and vendor chatbot foundations exist, but real ERP payment status sync is missing.
- Real notification delivery is missing.
- Foundational accuracy and exception analytics exist, but SLA trends and advanced operational reporting are still missing.
- Usage metering foundation exists, but real billing provider, subscriptions, invoices, and overage policy are not connected.
- Real customer Priority mapping/write flow is not live.

### Production Ready

APFlow is production ready when it can support public production access, customer data handling, production secrets, billing/metering, and compliance expectations.

Current expected staging result: Production Ready is not ready.

Current production blockers:

- APP_ENV is staging, not production.
- Domain/HTTPS are not configured.
- Demo mode must be disabled for production.
- Demo reset must be disabled for production.
- Auth must be enabled and JWT secrets must be non-default.
- Production secret rotation and operational controls must be finalized.
- Public DB/Redis/MinIO exposure must be hardened.
- Production vendor access is not ready.
- Notification abstraction and mock delivery exist, but real email/Slack/Teams providers are not configured.
- Real ERP payment status sync is missing.
- Usage metering foundation exists, but billing provider, subscription management, customer invoices, and usage enforcement are missing.
- Foundational accuracy analytics exist, but advanced SLA, trend, and per-supplier analytics are not production-grade yet.
- E-invoicing compliance validation foundation exists, but certified e-invoicing submission, PEPPOL, and tax-authority integrations are not connected.

## Why Domain + HTTPS Is Deferred

Domain + HTTPS should happen after the AP user workflow and access/security posture are ready for real users. Connecting a public domain before pilot/production blockers are resolved can create a false signal that APFlow is production ready.

## Operator Rule

Use the Product Readiness Gate in the Admin area before demos, pilots, or production discussions:

- Demo Ready can be green while Pilot and Production are blocked.
- Pilot Ready must not be claimed until real customer access controls, notifications, vendor lifecycle, and ERP posture are complete.
- Production Ready must not be claimed until production security, HTTPS/domain, billing/metering, compliance, and operational hardening are complete.

## Related Docs

- [Demo Readiness Pack](demo_readiness_pack.md)
- [Runbook](runbook.md)
- [Security](security.md)
- [Production Security Guardrails](production_security.md)
- [Frontend QA Checklist](frontend_qa_checklist.md)
- [Payment Status Foundation](payment_status.md)
- [Vendor Payment-Status Chatbot](vendor_payment_chatbot.md)
- [Notification Delivery Abstraction](notifications.md)
- [Accuracy & Exception Analytics](analytics.md)
- [Usage Metering / Billing Foundation](usage_metering.md)
- [E-Invoicing Compliance Validation](compliance_validation.md)
- [Staging Operations](operations_staging.md)
- [Staging Release Checklist](staging_release_checklist.md)
