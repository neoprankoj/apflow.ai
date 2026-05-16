# Vendor Portal

- Purpose: show that vendors receive only safe invoice/payment information.
- Sample file: use `vendor-preview` seed mode or an approval-ready invoice.
- Expected status: one vendor-safe public status, never internal workflow detail.
- What to click: Demo login, open Vendor Portal Preview, create or use vendor access, preview the invoice.
- Pass: vendor sees only safe status and invoice basics.
- Fail: fraud, audit, ERP sync, or approval-policy internals appear.
- OCR note: provider choice is irrelevant once the invoice is already seeded for vendor preview.
