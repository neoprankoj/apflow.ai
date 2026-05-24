# Vendor Access Model

APFlow supports a production-shaped vendor portal access foundation for supplier self-service. It is designed for safe invoice and payment-status visibility, including the rules-based vendor payment-status chatbot.

## What It Provides

- Admin/AP manager creation of vendor access records.
- High-entropy URL-safe access tokens.
- Token hashes stored in APFlow; raw tokens are shown only once.
- Safe token prefix for admin identification.
- Browser-friendly vendor links at `/vendor?tenant_id=...&access_token=...`.
- Vendor-safe payment-status chatbot access through the same token.
- Expiration, revocation, rotation, and last-used tracking.
- Audit events for create, revoke, rotate, use, and vendor-safe preview.
- Strict vendor/invoice filtering.

## What Vendors Can See

Vendor tokens can only access invoices linked to that token's vendor. APFlow first matches by vendor ID, then by exact normalized supplier name for demo/OCR data where the vendor record and invoice supplier text may differ only by case, whitespace, or punctuation. Responses include vendor-safe fields such as invoice number, public status, total, currency, and safe payment status/message when available. The chatbot uses the same vendor-safe projection and refuses internal questions.

If a supplier has no matching invoices, the vendor page shows a safe empty state instead of exposing whether another supplier has invoices.

## What Vendors Cannot See

Vendor responses must not expose fraud/risk scores, duplicate internals, approval policy internals, audit raw metadata, ERP config/logs, internal payment notes, internal payment references, tenant internals, token hashes, or raw access tokens after creation/rotation.

## Lifecycle

1. Admin opens Vendor Access Management.
2. Admin creates access for a supplier email/vendor.
3. APFlow returns the raw token once.
4. Supplier opens the generated `/vendor` link or uses the token for vendor-safe invoice/payment API access.
5. APFlow updates `last_used_at` after successful use.
6. Admin can revoke access.
7. Admin can rotate access, which revokes the old token and returns one new token.

No real email delivery is included yet. Operators must not paste vendor tokens into logs, support tickets, screenshots, or public channels. If a raw token is exposed, revoke or rotate that access immediately.

## Future Work

- Real invite email delivery.
- Supplier support workflow.
- Production escalation and abuse controls for the vendor chatbot.
- Domain/HTTPS before real external supplier access.
