# Accuracy & Exception Analytics

APFlow includes a tenant-scoped Accuracy & Exceptions dashboard for AP managers and operators.

The dashboard summarizes existing APFlow data only. It does not use external BI tools, external analytics services, data warehouses, tracking scripts, or third-party telemetry.

## What It Measures

- Invoice volume and processed invoice count.
- OCR extraction attempts, provider failures, invalid file diagnostics, and review-required rate.
- Human review workload and submitted corrections.
- Approval status counts: pending, approved, rejected, and on hold.
- Exception counts: blocked invoices, missing PO flags, duplicate/risk flags, OCR failures, invalid files, and validation blockers.
- Mock ERP export outcomes.
- Payment status distribution.
- Vendor self-service activity: active/used vendor links, vendor-safe preview views, chatbot answered/refused counts.
- Notification delivery outcomes from APFlow's mock/placeholder delivery history.

## What It Does Not Measure Yet

- Long-term trend charts.
- SLA aging by invoice, supplier, or approver.
- Per-supplier accuracy and exception trend analysis.
- Real ERP payment-sync accuracy.
- Real notification provider delivery rates.
- External analytics, warehouse exports, or customer telemetry.

## Safety Boundaries

- Analytics are tenant-scoped and require authenticated invoice-read access.
- Analytics return summarized counts and recommendations only.
- No vendor raw tokens or token hashes are returned.
- No OCR provider payloads, API keys, webhook URLs, auth headers, or secrets are returned.
- No full raw audit metadata is exposed.
- Vendor chatbot/refusal activity is counted without exposing sensitive question contents.

## Demo Path

1. Process an invoice.
2. Approve/export the invoice to mock ERP.
3. Run mock payment sync.
4. Create vendor access and ask one vendor chatbot question.
5. Send a mock notification.
6. Open `Accuracy & Exceptions`.
7. Confirm metrics and recommendations update.
8. Confirm no sensitive data appears.

## Future Path

- Add SLA and aging analytics.
- Add time-series trend history.
- Add per-supplier and per-approver analytics.
- Add real ERP payment-sync accuracy once read-only payment sync is connected.
- Add real notification provider analytics after provider rollout.
