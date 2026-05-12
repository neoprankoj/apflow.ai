# Demo QA Checklist

Use this checklist before a private APFlow AI staging demo.

## Internal AP Workflow

- Open the dashboard and confirm `/ready` is ready.
- Confirm overview cards show invoices, pending approvals, review required, and low confidence counts.
- Confirm the invoice queue renders an empty state or recent tenant invoices.
- Confirm role/session details are visible and match the expected demo user.

## Upload, Extract, Process

- Download `apps/web/public/demo/fake-apflow-invoice.pdf` or use the dashboard link.
- Upload the fake invoice from the Upload Invoice section.
- Run Extract and confirm OCR fields, confidence, and review-required flags render.
- Run Process and confirm workflow status is `approval_ready` or `auto_approved`.
- Confirm timeline stages advance through validation, duplicate check, PO match, risk scoring, and approval routing.

## ERP Export

- Confirm the Export to Mock ERP button is enabled only when `erp_export_ready=true`.
- Export the invoice to the mock Priority adapter.
- Confirm an external invoice ID appears.
- Confirm recent ERP sync log summary is visible.
- Confirm users without `invoice:export_erp` cannot use the export action.

## Vendor-Safe Status

- Click the vendor-safe preview action after processing an invoice.
- Confirm the public status is one of `received`, `under_review`, `needs_information`, `approved`, `scheduled_for_payment`, `paid`, or `rejected`.
- Confirm fraud scores, internal risk reasons, audit logs, approval-policy internals, and ERP sync logs are not shown in the vendor preview.

## Vendor Chatbot

- Use the Vendor Portal section to ask a payment-status question.
- Confirm the response is deterministic and limited to allowed invoice/payment fields.
- Ask an unsupported or internal-risk question and confirm it deflects or escalates.

## Auth And RBAC

- Confirm unauthenticated protected API calls return `401`.
- Confirm users without permission receive `403`.
- Confirm tenant admin actions are visible only for owner/admin roles.
- Confirm ERP export, review correction, audit access, and demo reset are hidden or disabled when the role lacks permission.

## Demo Reset

- Confirm `APP_ENV=staging` and `ALLOW_DEMO_RESET=true` only on private staging when reset is needed.
- As owner/admin, call `POST /admin/demo/reset`.
- Confirm the response message is `Demo data reset successfully.` and `workflow_status=clean`.
- Confirm invoices, review tasks, workflow states, approval tasks, notifications, uploaded documents, ERP sync logs, vendor access, and vendor messages are cleared for the demo tenant.
- Confirm tenant, users, memberships, vendor fixtures, purchase order fixtures, and approval policy remain available for the next demo.
- Confirm the endpoint returns `403` when reset is disabled or the role is not owner/admin.
- Confirm production never enables `ALLOW_DEMO_RESET`.

## Restart Persistence

- Run the runtime smoke script.
- Restart API and web containers.
- Confirm `/ready` returns ready.
- Confirm invoice count and dashboard data remain after restart.
- Re-run the runtime smoke script.

## Backup Check

- Run `scripts/backup_postgres.sh`.
- Confirm the backup file is non-empty.
- Run `scripts/restore_postgres.sh <backup-file>` without `--yes` to review the dry-run output.
- Do not run destructive restore during a demo unless recovery is intentionally being tested.

## Security Check

- Confirm `.env.staging` is not committed.
- Confirm no secrets appear in GitHub Actions logs, app logs, or screenshots.
- Confirm internal service ports remain firewalled.
- Confirm uploaded demo files contain no real vendor, tax, bank, customer, or payment data.
- Confirm dashboard errors do not expose stack traces or secrets.
