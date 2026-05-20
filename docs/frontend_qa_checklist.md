# Frontend QA Checklist

Use this short checklist before merging frontend UI changes.

## Standard validation

- [ ] `npm --workspace apps/web run lint`
- [ ] `npm --workspace apps/web run build`
- [ ] `docker compose up -d --build`
- [ ] `git diff --check`

## Dashboard

- [ ] Dashboard loads without layout breakage.
- [ ] KPI cards show readable labels, values, and context text.
- [ ] Quick actions are visible and work as expected.
- [ ] Priority work and recent activity are understandable at a glance.
- [ ] Audit Trail shows readable activity after invoice actions.

## Approval Inbox

- [ ] Invoice queue rows are scannable and selected state is clear.
- [ ] Selected invoice detail panel shows summary, statuses, and blocker context.
- [ ] Approve, Reject, Keep on Hold, ERP, and vendor actions remain visible where allowed.
- [ ] Duplicate, blocked, missing-PO, and risk badges are easy to distinguish.

## Invoice Upload

- [ ] Upload, extract, and process actions remain usable.
- [ ] OCR fields, confidence, and review state render correctly.
- [ ] Review-required invoices show clear correction guidance.
- [ ] Buttons disable appropriately while actions are running.

## Vendor Preview

- [ ] Vendor-safe preview loads for processed invoices.
- [ ] Internal risk, audit, and ERP details are not exposed.
- [ ] Vendor-safe status language remains understandable.

## ERP Export

- [ ] Export action is available only when the invoice is export-ready.
- [ ] Export result and external ID are shown after success.
- [ ] Blocked or rejected invoices explain why export is unavailable.
- [ ] Priority Mapping Admin loads the current tenant mapping safely.
- [ ] Invalid mapping JSON shows a local validation message before any save attempt.
- [ ] View-only users can read the mapping but cannot edit or save it.
- [ ] Priority Vendor Sync preview shows mapped vendor sample rows without importing data.
- [ ] Priority PO Sync preview shows mapped purchase-order sample rows without importing data.
- [ ] Users without ERP sync/config permission cannot run sync previews.

## Audit Trail

- [ ] Approval, review, OCR, ERP, vendor, and system filters work.
- [ ] Activity items show readable labels instead of raw technical event names.
- [ ] Unknown or incomplete historical events render safely without breaking the page.

## Loading, empty, and error states

- [ ] Loading skeletons or busy states appear during data fetches.
- [ ] Empty states are helpful when lists have no data.
- [ ] API or action errors are visible and specific.
- [ ] Unauthorized states explain that sign-in is required.

## Responsive desktop checks

- [ ] Check the main dashboard at `1440x900`.
- [ ] Check the main dashboard at `1920x1080`.
- [ ] Sidebar, headers, cards, tables, and action areas remain readable at both sizes.
- [ ] No important text is clipped or overlapping.
