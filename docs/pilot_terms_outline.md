# Pilot Terms Outline

This is an outline for counsel review. It is not a binding legal contract, not legal advice, not a DPA, and not a production SLA. Qualified counsel must review and convert it into appropriate customer terms before any real customer pilot.

## 1. Pilot Purpose

- Validate APFlow's accounts payable workflow with a limited customer team.
- Test invoice upload, OCR, human review, approval routing, audit trail, vendor-safe status, payment-status visibility, and selected integration readiness.
- Confirm customer-specific ERP mapping assumptions before any real ERP writeback is considered.

## 2. Pilot Data Boundaries

- Use synthetic/demo data unless written approval allows limited customer data.
- Define approved invoice types, vendors, entities, and time period before upload.
- Do not upload highly sensitive documents unless specifically approved in the pilot terms.
- Do not use production customer data for demos outside the approved pilot group.
- Do not use real vendor links until Domain + HTTPS is connected and approved for pilot use.

## 3. Authorized Users

Document:

- Customer pilot sponsor.
- Customer tenant owner/admins.
- APFlow operator/admins.
- Approved AP users.
- Approved vendor users, if any.
- Support contacts.

Only authorized users should access pilot data. Role changes should be tracked.

## 4. Data Retention / Deletion Expectations

Define before pilot:

- Pilot start date.
- Pilot end date.
- Uploaded document retention period.
- Audit event retention period.
- Usage/analytics retention period.
- Backup retention period.
- Data export requirements.
- Deletion or cleanup request process.
- Exceptions for logs, security evidence, audit records, or legal preservation.

Current limitation: automated retention/deletion is not fully implemented yet, so cleanup is expected to be a manual operational process unless implemented later.

## 5. Support / Incident Contact Placeholder

Document:

- Customer business contact:
- Customer technical contact:
- Customer legal/privacy contact:
- APFlow operator contact:
- APFlow support channel:
- Incident escalation channel:
- Expected support hours:

No production SLA exists yet unless separately agreed in reviewed customer terms.

## 6. Limitations

- APFlow is demo-ready and pilot-shaped, not production-ready.
- Domain + HTTPS are still deferred until the approved deployment step.
- No production SLA is provided by this outline.
- No certified e-invoicing, tax authority, PEPPOL, or government submission exists.
- No real billing provider is connected.
- No real Email, Slack, or Teams delivery is connected.
- No real Priority writes are enabled unless separately approved, configured, tested, backed up, and documented.
- Production monitoring, alerting, offsite scheduled backups, automated retention, and deletion workflows are not finalized.

## 7. Customer Responsibilities

- Confirm the pilot sponsor and authorized users.
- Confirm which data may be uploaded.
- Avoid uploading data outside the approved pilot scope.
- Avoid sharing vendor access tokens in insecure channels.
- Review extracted invoice data before relying on it.
- Validate customer-specific ERP mappings before any future real ERP action.
- Report suspected access, data, or security issues promptly.

## 8. APFlow Responsibilities

- Maintain tenant-scoped access controls during the pilot.
- Keep Priority writes disabled unless separately approved.
- Keep real billing and external notification providers disabled unless separately approved.
- Preserve audit events needed to understand pilot activity.
- Run or confirm backup before pilot data import.
- Respond to pilot support and incident reports through the agreed channel.
- Document known limitations and avoid production-readiness claims.

## 9. Exit / Cleanup Checklist

At pilot end:

- [ ] Confirm whether pilot data should be retained, exported, anonymized, or deleted.
- [ ] Revoke or rotate vendor access tokens.
- [ ] Disable unneeded pilot users.
- [ ] Confirm Priority writes remain disabled unless separately approved.
- [ ] Capture final pilot feedback and open issues.
- [ ] Preserve required audit/security records according to agreed terms.
- [ ] Confirm backup retention and cleanup expectations.
- [ ] Document any follow-up needed before production or broader rollout.
