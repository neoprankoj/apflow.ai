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

## AP user acceptance

- [ ] A first-time AP manager can identify the next action without developer explanation.
- [ ] Upload, OCR, review, process, approval, ERP export, and Audit Trail copy uses consistent AP workflow terms.
- [ ] Success messages explain what happened and where to verify it next.
- [ ] Blocker messages explain the next user action, not only the internal status.
- [ ] Review-required invoices tell the user to correct highlighted fields and run Process again.
- [ ] Blocked invoices point the user toward Approval Inbox.
- [ ] ERP export messages say whether export is unavailable, ready, or completed.
- [ ] Priority Admin clearly separates Sync dry run, Import plan, Controlled import, and Imported records.
- [ ] Priority Admin always says when an action is preview-only, APFlow-only, or Priority-safe.
- [ ] Imported records are visible after controlled Priority import.

## Final AP user smoke test

- [ ] Demo Login works.
- [ ] Tenant Session shows Demo Owner, owner role, and API ready.
- [ ] AP Workflow Guide appears and the Next Recommended Action is sensible.
- [ ] Demo checklist is readable and not intrusive.
- [ ] Dashboard overview loads without API errors.
- [ ] Known working invoice PDF uploads successfully.
- [ ] OCR extraction works and extracted text/fields appear.
- [ ] Invalid fake PDF upload shows a clear invalid-file message.
- [ ] No generic `RuntimeError` appears in OCR errors.
- [ ] OCR engine/fallback messaging is visible only when relevant.
- [ ] Corrections can be submitted if review is required.
- [ ] Run Process continues the workflow.
- [ ] Human Review state clears or shows a clear blocker.
- [ ] Approval Inbox loads and invoice details are readable.
- [ ] Approve works and the approval message is clear.
- [ ] Dashboard refreshes after approval without 500 errors.
- [ ] Vendor-safe preview works and does not expose fraud/risk details.
- [ ] Mock ERP export works and success points to Audit Trail.
- [ ] Audit Trail events are readable and main rows do not show raw UUID noise.
- [ ] Priority Mapping Admin loads.
- [ ] Priority readiness shows mock mode, read-only disabled, and writes disabled.
- [ ] Sample mapping loads and validation works.
- [ ] Vendor sync preview, vendor import plan, controlled vendor import, and Imported Vendors work.
- [ ] PO preview, PO import plan, controlled PO import, and Imported Purchase Orders work.
- [ ] Audit Trail shows Priority import events.
- [ ] UI confirms no Priority data changed.
- [ ] No 500 errors appear during the full flow.

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
- [ ] Invalid PDF/image uploads show a clear invalid-file message instead of a generic OCR failure.
- [ ] OCR.space engine failures show an engine/fallback message and do not expose secrets.
- [ ] Fallback success, when configured, shows the engine used.
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
