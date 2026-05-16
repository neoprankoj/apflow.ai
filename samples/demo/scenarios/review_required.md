# Review Required

- Purpose: demonstrate safe human review when required invoice fields are missing or weak.
- Sample file: use a synthetic upload or seed mode `review-required`.
- Expected status: `review_required`.
- What to click: Demo login, open OCR Review, inspect missing fields, show correction inputs.
- Pass: missing fields are clear and the UI treats review as safe.
- Fail: extraction crashes, hides issues, or makes review look like an application failure.
- OCR note: OCR.space commonly lands here for incomplete invoices; mock mode can be used for deterministic local testing.
