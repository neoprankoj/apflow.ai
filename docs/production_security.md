# Production Security Guardrails

APFlow is demo-ready on private staging, but production and real customer pilots require stricter access controls. These guardrails define what must be true before real customer data is allowed.

## Runtime Guardrails

- `DEMO_MODE=true` is rejected when `APP_ENV=production`.
- `ALLOW_DEMO_RESET=true` is rejected when `APP_ENV=production`.
- `AUTH_ENABLED=false` is rejected when `APP_ENV=production`.
- `AUTH_SECRET_KEY` must be non-default and at least 32 characters in staging and production.
- Wildcard CORS origins are rejected in staging and production.
- Default MinIO credentials are rejected in staging and production.

Production startup errors intentionally use safe messages and must not print secrets.

## Demo Reset

`POST /admin/demo/reset` is only for private staging cleanup. It requires:

- authenticated owner/admin access,
- `APP_ENV=staging`,
- `ALLOW_DEMO_RESET=true`.

It remains blocked in production even if an operator accidentally mutates the reset flag.

## Role Matrix

| Role | Intended access |
| --- | --- |
| Owner/Admin | Tenant administration, ERP configuration, approval/export, review, audit, and invoice operations. |
| Controller | Invoice processing, approval, ERP export/sync, review, audit, and notifications. |
| AP Manager | Invoice processing, approval, review, ERP read/sync, and notifications. |
| Approver | Invoice read/approval and review visibility. No ERP configuration or tenant administration. |
| Viewer | Read-only invoice/review/ERP/notification visibility. No approval, export, import, or admin actions. |

Backend RBAC remains the source of truth. Frontend visibility is convenience only.

## Tenant Isolation

Protected routes must resolve the tenant from the authenticated membership. Supplying another tenant ID must return a denial or filter out the other tenant’s records.

The release test gate covers invoices, workflows, approval tasks, review tasks, audit events, notifications, ERP mapping, and Priority imported records.

## Vendor-Safe Boundary

Vendor-facing responses use an allowlist. They must not expose:

- fraud or risk scores,
- internal risk reasons,
- duplicate detection internals,
- approval policy internals,
- audit raw metadata,
- internal user emails/names unless explicitly public,
- ERP adapter configuration or logs,
- tenant internals,
- vendor token hashes,
- bearer/access tokens beyond the one-time vendor access creation response.

Blocked or high-risk invoices should map to safe language such as `under_review`; rejected invoices should show public rejection wording only.

## Still Missing Before Real Pilots

- Production vendor access lifecycle: invitation, expiration, revocation, support, and monitoring.
- Real notification provider and delivery monitoring.
- Payment status sync.
- Domain and HTTPS when access/security hardening is ready.
- Backup/restore drill confirmation for pilot data.
- Real customer ERP mapping validation and write approval process.

## Operator Reminders

- Never commit `.env.staging`, production env files, OCR keys, Priority credentials, JWT secrets, or private keys.
- Keep Priority writes disabled until a customer-specific write mapping and rollback plan are approved.
- Keep demo reset disabled except during controlled private staging cleanup.
- Run the Product Readiness Gate before claiming pilot or production readiness.
