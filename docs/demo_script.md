# Demo Script

Use this script for a private staging demo. Keep the presenter flow deterministic; live OCR is a feature to demonstrate, not a dependency for setup.

## A. Demo Preparation

1. Confirm the stack is healthy.
2. Confirm `/health` returns `ok`.
3. Confirm `/ready` returns `ready`.
4. Confirm the current `OCR_PROVIDER`.
5. Confirm demo login works.
6. Confirm demo reset is disabled unless you intentionally enabled `ALLOW_DEMO_RESET=true`.
7. If you need a prepared state, seed it explicitly:
   - clean: `python scripts/seed_demo_data.py --api-base-url <api-url> --mode clean`
   - approval ready: `python scripts/seed_demo_data.py --api-base-url <api-url> --mode approval-ready`
   - review required: `python scripts/seed_demo_data.py --api-base-url <api-url> --mode review-required`
   - vendor preview: `python scripts/seed_demo_data.py --api-base-url <api-url> --mode vendor-preview`
   - inbox demo: `python scripts/seed_demo_data.py --api-base-url <api-url> --mode inbox-demo`

## B. Demo Path 1 - Clean Dashboard

1. Open the dashboard.
2. Click `Demo login`.
3. Show the tenant session, current user, and `owner` role.
4. Show `AP Workflow Guide` and `Next recommended action`.
5. Explain the main workflow: Upload -> OCR -> Review -> Process -> Approve -> Export -> Audit.
6. Show the dashboard sections: overview, workflow guide, upload, OCR review, approval inbox, ERP export, vendor portal preview, audit trail, admin.
7. If starting from a clean seed, show zero operational counts and an empty review queue.

## C. Demo Path 2 - Invoice Upload And OCR

1. Upload the synthetic invoice from the demo pack or the dashboard fake invoice link.
2. Click `Extract`.
3. Show the selected OCR provider and configured state.
4. Explain confidence, required fields, parsed text preview, and provider diagnostics.
5. Point out that the Workflow Guide moves the AP manager toward review, approval, export, or audit.

## D. Demo Path 3 - Review-Required Invoice

1. Use the `review-required` seed or a real OCR sample with missing fields.
2. Show weak or missing required fields.
3. Explain that `review_required` is a safe workflow outcome, not a crash.
4. Show the manual correction inputs.
5. After saving corrections, confirm the message says to run `Process` again.

## E. Demo Path 4 - Manual Correction And Processing

1. Fill any missing required fields.
2. Submit corrections.
3. Click `Process`.
4. Show the workflow timeline moving through validation, duplicate detection, PO matching, risk scoring, and approval routing.
5. Call out the specific result if PO matching, validation, or approval policy changes the final state.
6. If the result is blocked, use the `Next recommended action` to move to Approval Inbox.

## F. Demo Path 5 - ERP Export

1. Use an `approval_ready` invoice.
2. Click `Export to Mock ERP`.
3. Show the external invoice ID and sync result.
4. Explain that the adapter pattern is live now and real ERP adapters are the next integration step.
5. Open Audit Trail to verify the export event.

## G. Demo Path 6 - Priority Mapping Admin

1. Open `Admin`, then show `Priority ERP Mapping`.
2. Confirm that mock mode is still active, read-only fetch is disabled, and real writes are disabled by default.
3. Show `Priority Real Connection Readiness`; explain that the remote drill is GET-only and safely blocked in mock staging.
4. Load the safe sample mapping and explain that it is only a template.
5. Click `Validate` and show status, warnings, and summary.
6. Save only after explaining that customer-specific Priority entity names must be verified first.
7. Keep source set to `Sample records`, then click `Preview Vendor Sync` and show the mapped vendor rows.
8. Click `Preview Purchase Orders` and show the mapped PO rows.
9. Switch source to `Real Priority read-only fetch` and show the safe disabled or missing-credentials message in mock staging.
10. Switch back to `Sample records`.
11. Click `Generate Vendor Import Plan` and show which rows would be created, updated, skipped, or flagged as conflicts.
12. Click `Generate Purchase Order Import Plan` and show the same plan categories for POs.
13. Select one `would_create` vendor row, type `IMPORT_SELECTED`, and import it into APFlow.
14. Generate the PO import plan again, select a PO that references the imported vendor, type `IMPORT_SELECTED`, and import it.
15. Show the controlled import result and explain that APFlow records changed but Priority data did not.
16. Open `Imported Records` and confirm the vendor and PO show Priority source, external ID, APFlow ID, and last import result.
17. Open `Audit Trail` and show the Priority import events.

## H. Demo Path 7 - Approval Inbox

1. Seed `inbox-demo` when you need all approval examples ready before the meeting.
2. Open `Approval Inbox`.
3. Select the blocked/high-risk invoice and show workflow, approval status, missing PO, risk badge, and vendor-safe preview.
4. Approve one blocked invoice and show it move into an export-ready state.
5. Select the existing `On hold` and `Rejected` examples and explain why they remain non-exportable.
6. Select the duplicate-like invoices and explain the duplicate badge plus short invoice ID suffix.
7. Export the approval-ready invoice from the inbox.

## I. Demo Path 8 - Vendor Portal Preview

1. Use the vendor preview section or create a vendor access token through the demo flow.
2. Show the vendor-safe invoice status.
3. Confirm that fraud scores, audit logs, ERP sync logs, approval-policy internals, and risk reasons are not exposed.

## J. Demo Path 9 - Audit Trail

1. After upload, review, approval, and ERP export actions, open `Audit Trail`.
2. Show the sequence of OCR, review, approval, vendor, and ERP events.
3. Use the filters to isolate approval, review, and ERP activity.
4. Explain that the timeline proves what happened without exposing raw technical logs to the presenter.

## K. Demo Path 10 - AP Manager Demo Checklist

1. Expand the `Demo checklist` in the AP Workflow Guide.
2. Walk through each checklist item as a presenter rehearsal path.
3. Confirm key action messages point to the next step and to Audit Trail proof.
4. Confirm Priority connector copy separates dry run, import plan, controlled import, and imported records.

## L. AP User Acceptance Pass

1. Start from the top of the dashboard and confirm the AP manager can identify the next recommended action.
2. Confirm upload, OCR, review, process, approval, ERP export, and Audit Trail use consistent finance-friendly labels.
3. Trigger one safe success path and confirm the message explains what happened and where to verify it.
4. Trigger or show one blocked path and confirm the message explains what the user should do next.
5. In Priority Mapping Admin, confirm each section states whether it is preview-only, APFlow-only, or Priority-safe.
6. Confirm imported vendors and purchase orders are visible after controlled import.
7. Confirm no Priority data is changed during sample preview, import plan, controlled import, or readiness checks.

## M. Demo Cleanup

1. Enable `ALLOW_DEMO_RESET=true` only when needed on private staging.
2. Use the dashboard reset action or `POST /admin/demo/reset`.
3. Confirm the response says `Demo data reset successfully.`
4. Set `ALLOW_DEMO_RESET=false` again.
5. Restart the API service after changing the staging env file.
