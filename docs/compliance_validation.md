# E-Invoicing Compliance Validation

APFlow has a validation-only compliance foundation for checking whether processed invoices contain the structured data needed for future e-invoicing workflows.

This is not a certified e-invoicing integration. APFlow does not submit invoices to any government, tax authority, PEPPOL network, EU tax platform, Israeli tax authority, IRS, HMRC, or live e-invoicing gateway.

## Profiles

Starter profiles are code-based and deterministic:

- `generic_b2b`: minimum B2B invoice readiness checks.
- `israel_basic`: validation-only Israeli starter checks.
- `eu_vat_basic`: validation-only EU VAT starter checks.
- `us_basic`: validation-only US starter checks.

Profiles define required and recommended fields. The checks are designed to help AP managers identify missing data before any future country-specific e-invoicing work.

## Checked Data

Core checks include:

- supplier name
- supplier tax/VAT ID where the profile requires it
- invoice number
- invoice date
- currency
- subtotal/tax total where relevant
- grand total
- line items as a recommended readiness signal
- buyer identifiers as recommended fields when the current APFlow invoice model does not yet capture them

Grand total checks reuse APFlow's discount-aware total reconciliation:

```text
subtotal + tax + shipping + fees - discounts = grand total
```

## API

- `GET /compliance/profiles`
- `GET /compliance/invoices/{invoice_id}?tenant_id={uuid}&profile_key=generic_b2b`
- `GET /compliance/summary?tenant_id={uuid}&profile_key=generic_b2b`

All endpoints are authenticated, tenant-scoped, and read-only. Invoice validation records an audit event with profile/status counts, but it does not mutate invoice workflow state.

## Dashboard

The E-Invoicing Compliance panel lets an AP manager:

1. Choose a validation profile.
2. Review tenant summary counts.
3. Select an invoice.
4. Validate required and recommended fields.
5. See missing fields, warnings, and next steps.

The panel clearly states that no government or e-invoicing network submission occurs.

## Safety Boundaries

- No government API integration.
- No PEPPOL integration.
- No certified e-invoicing provider.
- No legal certification claim.
- No `.env.staging` changes.
- No secrets, vendor tokens, raw OCR payloads, or tax-authority credentials are exposed.
- Existing AP approval/export behavior is not blocked by compliance warnings.

## Future Path

Future work can add:

- richer country-specific rules
- buyer/customer master-data capture
- certified provider integration
- PEPPOL access point integration
- tax-authority submission and response tracking
- ERP mapping for country-specific e-invoice fields
