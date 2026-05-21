# Frontend QA Checklist

Use this short checklist before merging frontend UI changes.

## Standard validation

- [ ] `npm --workspace apps/web run lint`
- [ ] `npm --workspace apps/web run build`
- [ ] `docker compose up -d --build`
- [ ] `git diff --check`

## Dashboard

- [ ] Dashboard loads without layout breakage.
- [ ] AP Workflow Guide appears near the top of the dashboard.
- [ ] Next Recommended Action is visible and points to the correct section for the current demo state.
- [ ] Demo checklist expands without covering the main workflow.
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
- [ ] Correction success message tells the user to run Process again.
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
- [ ] Priority Real Connection Readiness shows mode, read-only fetch, writes, status, and checklist rows.
- [ ] Remote connection drill is safely blocked in mock/missing-config staging and says it is GET-only.
- [ ] Priority Admin explains section order: readiness, mapping, validation, dry run, import plan, controlled import, imported records.
- [ ] Invalid mapping JSON shows a local validation message before any save attempt.
- [ ] View-only users can read the mapping but cannot edit or save it.
- [ ] Priority Vendor Sync preview shows mapped vendor sample rows without importing data.
- [ ] Priority PO Sync preview shows mapped purchase-order sample rows without importing data.
- [ ] Priority preview source defaults to Sample records.
- [ ] Switching to Real Priority read-only fetch shows a safe disabled/config message when real credentials are not configured.
- [ ] Real Priority read-only copy clearly says GET-only and no Priority data is changed.
- [ ] Priority Vendor Import Plan shows create/update/skip/conflict counts without importing data.
- [ ] Priority PO Import Plan shows create/update/skip/conflict counts without importing data.
- [ ] Import plan conflict and warning text is visible and does not imply records were changed.
- [ ] Controlled import requires selecting rows and typing `IMPORT_SELECTED`.
- [ ] Vendor controlled import creates or updates only selected APFlow records.
- [ ] PO controlled import blocks clearly when the referenced vendor has not been imported.
- [ ] Controlled import result says APFlow changed but no Priority data was changed.
- [ ] Imported Vendors shows Priority source, external ID, APFlow ID, and last import result after vendor import.
- [ ] Imported Purchase Orders shows Priority source, PO number, vendor external ID, APFlow ID, and last import result after PO import.
- [ ] Sync Dry Run, Import Plan, Controlled Import, and Imported Records are visually distinct and cannot be confused.
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
