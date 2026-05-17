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
4. Show the dashboard sections: overview, upload, OCR review, approvals, ERP export, vendor portal preview, admin.
5. If starting from a clean seed, show zero operational counts and an empty review queue.

## C. Demo Path 2 - Invoice Upload And OCR

1. Upload the synthetic invoice from the demo pack or the dashboard fake invoice link.
2. Click `Extract`.
3. Show the selected OCR provider and configured state.
4. Explain confidence, required fields, parsed text preview, and provider diagnostics.

## D. Demo Path 3 - Review-Required Invoice

1. Use the `review-required` seed or a real OCR sample with missing fields.
2. Show weak or missing required fields.
3. Explain that `review_required` is a safe workflow outcome, not a crash.
4. Show the manual correction inputs.

## E. Demo Path 4 - Manual Correction And Processing

1. Fill any missing required fields.
2. Submit corrections.
3. Click `Process`.
4. Show the workflow timeline moving through validation, duplicate detection, PO matching, risk scoring, and approval routing.
5. Call out the specific result if PO matching, validation, or approval policy changes the final state.

## F. Demo Path 5 - ERP Export

1. Use an `approval_ready` invoice.
2. Click `Export to Mock ERP`.
3. Show the external invoice ID and sync result.
4. Explain that the adapter pattern is live now and real ERP adapters are the next integration step.

## G. Demo Path 6 - Approval Inbox

1. Seed `inbox-demo` when you need all approval examples ready before the meeting.
2. Open `Approval Inbox`.
3. Select the blocked/high-risk invoice and show workflow, approval status, missing PO, risk badge, and vendor-safe preview.
4. Approve one blocked invoice and show it move into an export-ready state.
5. Select the existing `On hold` and `Rejected` examples and explain why they remain non-exportable.
6. Select the duplicate-like invoices and explain the duplicate badge plus short invoice ID suffix.
7. Export the approval-ready invoice from the inbox.

## H. Demo Path 7 - Vendor Portal Preview

1. Use the vendor preview section or create a vendor access token through the demo flow.
2. Show the vendor-safe invoice status.
3. Confirm that fraud scores, audit logs, ERP sync logs, approval-policy internals, and risk reasons are not exposed.

## I. Demo Path 8 - Audit Trail

1. After upload, review, approval, and ERP export actions, open `Audit Trail`.
2. Show the sequence of OCR, review, approval, vendor, and ERP events.
3. Use the filters to isolate approval, review, and ERP activity.
4. Explain that the timeline proves what happened without exposing raw technical logs to the presenter.

## J. Demo Cleanup

1. Enable `ALLOW_DEMO_RESET=true` only when needed on private staging.
2. Use the dashboard reset action or `POST /admin/demo/reset`.
3. Confirm the response says `Demo data reset successfully.`
4. Set `ALLOW_DEMO_RESET=false` again.
5. Restart the API service after changing the staging env file.
