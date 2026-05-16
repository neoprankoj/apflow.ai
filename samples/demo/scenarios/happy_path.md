# Happy Path

- Purpose: show a clean approval-ready AP workflow without relying on live OCR.
- Sample file: optional; use deterministic seed mode `approval-ready`.
- Expected status: `approval_ready`.
- What to click: Demo login, inspect seeded invoice, open ERP Export, export to mock ERP.
- Pass: invoice is approval-ready, PO is matched, ERP export is enabled.
- Fail: workflow depends on live OCR or lands in review unexpectedly.
- OCR note: use deterministic seed mode for the presenter path; use upload/extract separately when demonstrating OCR.
