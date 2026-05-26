# Demo Seed Profiles

APFlow demo seed profiles reset a demo tenant into a known, repeatable state for demos and QA. They are tenant-scoped, admin-only, disabled unless `ALLOW_DEMO_RESET=true`, and blocked in production.

## Safety Rules

- Never enable demo seeding in production.
- Never modify or commit `.env.staging`.
- Enable `ALLOW_DEMO_RESET=true` only temporarily on private staging.
- Type `SEED_DEMO_PROFILE` before running a seed profile.
- Seed profiles clear operational demo data for the selected tenant only.
- Vendor access tokens are shown once. If a token appears in a screenshot, chat, log, or ticket, revoke or rotate it.
- Priority writes remain disabled. Seeded Priority data is APFlow-side demo data only.

## Profiles

### Clean Minimal

Use this when you want a quiet tenant and plan to upload a fresh invoice live.

Includes:

- Preserved owner/admin users.
- One supplier.
- One purchase order.
- No invoice workflow history.

### AP Manager Demo

Use this for the core AP manager walkthrough.

Includes:

- Review-required invoice.
- Pending approval invoice.
- Approved/exported invoice.
- Discounted invoice.
- Blocked invoice with a clear AP review reason.

### Vendor Self-Service Demo

Use this for vendor portal, payment status, and chatbot demos.

Includes:

- SuperStore supplier.
- Vendor-visible invoices.
- Pending/scheduled/paid/disputed payment examples.
- One active vendor access token/link shown once.
- Seeded vendor chatbot audit events.

### Priority Connector Demo

Use this for the Priority mapping ladder.

Includes:

- Saved sample Priority mapping.
- Imported vendor example.
- Imported purchase order example.
- Audit copy showing Priority writes are disabled.

### Compliance Demo

Use this for e-invoicing validation walkthroughs.

Includes:

- Generic B2B-ready invoice.
- Invoice missing supplier tax ID.
- VAT/tax warning invoice.
- Buyer identifier caveat where current invoice fields do not yet capture buyer tax ID.

### Analytics-Rich Demo

Use this for founder/operator demos and dashboard screenshots.

Includes:

- AP manager workflow examples.
- Vendor self-service data.
- Priority connector examples.
- Compliance examples.
- Mock notification delivery.
- Usage events for analytics and billing-readiness panels.

## Recommended Staging Flow

1. Temporarily set `ALLOW_DEMO_RESET=true` on the staging VPS only.
2. Recreate the API container so the env change is loaded.
3. Open Admin -> Demo Seed Profiles.
4. Select a profile.
5. Type `SEED_DEMO_PROFILE`.
6. Run the seed profile and copy any one-time vendor token if needed.
7. Set `ALLOW_DEMO_RESET=false`.
8. Recreate the API container again.
9. Run the browser smoke checklist.

Use:

```bash
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging up -d --force-recreate api
```

## API

- `GET /admin/demo/seed-profiles`
- `POST /admin/demo/seed-profile`

Request body:

```json
{
  "tenant_id": "tenant-uuid",
  "profile_key": "analytics_rich_demo",
  "confirm_text": "SEED_DEMO_PROFILE"
}
```

The response includes created counts, cleared counts, warnings, next steps, and one-time vendor links if the profile generated vendor access.
