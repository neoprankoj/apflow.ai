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
- Deterministic demo seed profiles are available for repeatable AP manager, vendor, Priority, compliance, analytics-rich, and clean demos.

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
- Pilot data packs exist for repeatable demos and QA, but real customer onboarding data governance is still needed.
- Draft legal/privacy/data-handling docs exist, but qualified counsel review and customer-specific terms are still required.
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
- Public DB/Redis/MinIO exposure must remain hardened and verified before any production launch.
- Public port/firewall hardening checklist exists, and staging Compose is expected to bind app/internal service ports to localhost. External verification is still required before production.
- Backup/restore drill foundation and scheduled backup policy are documented, but live schedule installation, offsite backups, backup failure alerts, retention automation, and recent production restore evidence are still required for production.
- Operations health script and backup age check exist for staging, but external monitoring, alerting, log retention, and production incident operations are still missing.
- Production vendor access is not ready.
- Notification abstraction, mock delivery, and a real-provider configuration gate exist, but real email/Slack/Teams providers are not connected for external delivery.
- Real ERP payment status sync is missing.
- Usage metering foundation exists, but billing provider, subscription management, customer invoices, and usage enforcement are missing.
- Foundational accuracy analytics exist, but advanced SLA, trend, and per-supplier analytics are not production-grade yet.
- E-invoicing compliance validation foundation exists, but certified e-invoicing submission, PEPPOL, and tax-authority integrations are not connected.

## Status After PR #62

- Demo Ready: yes. The AP manager workflow, Priority safety ladder, payment status, vendor access, chatbot, notifications foundation, analytics, usage metering, compliance validation, seed profiles, and audit proof are available for controlled staging demos.
- Pilot Ready: partially ready, but not fully ready. The product is pilot-shaped, but real customer use still needs public access hardening, real notification provider configuration, real ERP payment sync planning, customer-specific Priority mapping validation, backup/restore rehearsal, and legal/privacy preparation.
- Production Ready: no. `APP_ENV` is staging, domain/HTTPS are deferred, demo-mode behavior exists for staging, real billing and certified e-invoicing are not connected, and production monitoring, incident response, and secrets operations remain incomplete.

For the final gap closure review and go/no-go checklist, use [Pilot Readiness Review](pilot_readiness_review.md).

## Why Domain + HTTPS Is Deferred

Domain + HTTPS should happen after the AP user workflow and access/security posture are ready for real users. Connecting a public domain before pilot/production blockers are resolved can create a false signal that APFlow is production ready.

## Public Access / Domain / HTTPS Readiness

Domain and HTTPS are not connected yet. Public access hardening is still pending, and Production Ready remains no.

PR #64 adds the planning checklist, Nginx vs Caddy decision framework, public port review, reverse proxy route plan, security header plan, TLS checklist, and rollback criteria in [Public Access / Domain / HTTPS Readiness](public_access_https_readiness.md). It does not change DNS, issue certificates, modify live proxy config, or launch production.

PR #67 adds [Public Port / Firewall Hardening Checklist](public_port_firewall_hardening.md) and a read-only `scripts/check_public_ports.sh` helper.

PR #68 updates staging Compose bindings so web/API are expected to bind to `127.0.0.1` and PostgreSQL, Redis, and MinIO are not host-published. Nginx remains the current public ingress on port `80`; Domain + HTTPS and firewall changes remain deferred.

PR #69 adds [Reverse Proxy Security Hardening](reverse_proxy_security_hardening.md), updated Nginx/Caddy templates, and a read-only reverse proxy inspection helper. It does not change live proxy config, connect Domain + HTTPS, issue certificates, or make Production Ready pass.

## Legal / Privacy / Data Handling Readiness

PR #70 adds draft legal/privacy/data-handling materials:

- [Legal / Privacy / Data Handling Pack](legal_privacy_data_pack.md)
- [Customer Data Handling Summary](customer_data_handling_summary.md)
- [Pilot Terms Outline](pilot_terms_outline.md)

These documents are operational readiness drafts only. They are not legal advice, not lawyer-approved terms, not a DPA, not a production SLA, and not a GDPR/SOC 2/ISO compliance claim. Production Ready remains no until counsel review, customer contracts, DPA terms, retention/deletion processes, monitoring, backups, and production access controls are finalized.

## Monitoring / Operations Health Readiness

PR #71 adds [Operations Health](operations_health.md) and a read-only `scripts/check_operations_health.sh` helper for Docker service status, local API health/readiness, public proxy health, PostgreSQL readiness, disk usage, Docker disk usage, backup freshness, demo reset status, public port inspection, and reverse proxy inspection.

This is an operational foundation only. It does not connect Datadog, Sentry, Grafana Cloud, Better Stack, UptimeRobot, external alerts, SMS/email/Slack notifications, log aggregation, automated remediation, or production incident operations. Production Ready remains no until external monitoring/alerting, log retention, backup alerting, incident response ownership, and production runbooks are finalized.

## Backup / Restore / Disaster Recovery Readiness

PR #65 adds the staging backup/restore drill plan and safe helper scripts in [Backup / Restore / Disaster Recovery Drill](backup_restore_drill.md). It documents PostgreSQL backup, temporary restore verification, document storage backup for filesystem and MinIO modes, config inventory, restore verification, and rollback procedure.

PR #72 adds [Scheduled Backup Policy](scheduled_backup_policy.md), `scripts/check_backup_age.sh`, cron/systemd scheduling templates, and a backup age policy. It does not install a live schedule, connect offsite backups, delete old backups, add backup-failure alerts, or make Production Ready pass.

Production Ready remains no until scheduled backups are installed and observed, offsite encrypted copies exist, backup-failure alerting exists, retention automation is reviewed, and a recent restore drill is implemented and verified.

PR #73 adds [Notification Provider Readiness](notification_provider_readiness.md), a safe `/notifications/readiness` API, and Admin UI visibility for the real Email/Slack/Teams configuration gate. Mock remains the default provider, real delivery requires `NOTIFICATION_REAL_DELIVERY_ENABLED=true`, and provider secrets/webhook URLs are not returned.

Production Ready remains no because real provider implementations, sender-domain SPF/DKIM/DMARC verification, approved test recipients, Domain + HTTPS, alerting, and support ownership are still required before external customer/vendor notifications.

## Operator Rule

Use the Product Readiness Gate in the Admin area before demos, pilots, or production discussions:

- Demo Ready can be green while Pilot and Production are blocked.
- Pilot Ready must not be claimed until real customer access controls, notifications, vendor lifecycle, and ERP posture are complete.
- Production Ready must not be claimed until production security, HTTPS/domain, billing/metering, compliance, and operational hardening are complete.

## Related Docs

- [Pilot Readiness Review](pilot_readiness_review.md)
- [Public Access / Domain / HTTPS Readiness](public_access_https_readiness.md)
- [Public Port / Firewall Hardening Checklist](public_port_firewall_hardening.md)
- [Reverse Proxy Security Hardening](reverse_proxy_security_hardening.md)
- [Legal / Privacy / Data Handling Pack](legal_privacy_data_pack.md)
- [Customer Data Handling Summary](customer_data_handling_summary.md)
- [Pilot Terms Outline](pilot_terms_outline.md)
- [Operations Health](operations_health.md)
- [Scheduled Backup Policy](scheduled_backup_policy.md)
- [Notification Provider Readiness](notification_provider_readiness.md)
- [Backup / Restore / Disaster Recovery Drill](backup_restore_drill.md)
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
- [Demo Seed Profiles](demo_seed_profiles.md)
- [Staging Operations](operations_staging.md)
- [Staging Release Checklist](staging_release_checklist.md)
