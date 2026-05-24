# Vendor Access Model

APFlow supports a production-shaped vendor portal access foundation for supplier self-service. It is designed for safe invoice and payment-status visibility, and later vendor chatbot access.

## What It Provides

- Admin/AP manager creation of vendor access records.
- High-entropy URL-safe access tokens.
- Token hashes stored in APFlow; raw tokens are shown only once.
- Safe token prefix for admin identification.
- Expiration, revocation, rotation, and last-used tracking.
- Audit events for create, revoke, rotate, use, and vendor-safe preview.
- Strict vendor/invoice filtering.

## What Vendors Can See

Vendor tokens can only access invoices linked to that token's vendor. Responses include vendor-safe fields such as invoice number, public status, total, currency, and safe payment status/message when available.

## What Vendors Cannot See

Vendor responses must not expose fraud/risk scores, duplicate internals, approval policy internals, audit raw metadata, ERP config/logs, internal payment notes, internal payment references, tenant internals, token hashes, or raw access tokens after creation/rotation.

## Lifecycle

1. Admin opens Vendor Access Management.
2. Admin creates access for a supplier email/vendor.
3. APFlow returns the raw token once.
4. Supplier uses the token for vendor-safe invoice/payment access.
5. APFlow updates `last_used_at` after successful use.
6. Admin can revoke access.
7. Admin can rotate access, which revokes the old token and returns one new token.

No real email delivery is included yet. Operators must not paste vendor tokens into logs, support tickets, or public channels.

## Future Work

- Real invite email delivery.
- Supplier support workflow.
- Vendor chatbot bound to this access model.
- Domain/HTTPS before real external supplier access.
