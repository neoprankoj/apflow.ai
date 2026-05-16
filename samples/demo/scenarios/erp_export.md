# ERP Export

- Purpose: show explicit ERP export after approval readiness.
- Sample file: deterministic `approval-ready` seed.
- Expected status: `approval_ready` before export and `success` after mock export.
- What to click: Demo login, inspect ERP Export section, click Export to Mock ERP.
- Pass: export button is gated correctly and an external invoice ID appears.
- Fail: export is enabled before readiness or hides the sync result.
- OCR note: keep this path independent from OCR so ERP export can be demonstrated reliably.
