# Public Access / Domain / HTTPS Readiness

This plan prepares APFlow for a future Domain + HTTPS cutover. It is a planning and guardrail document only.

## A. Purpose

- Prepare APFlow for future Domain + HTTPS without connecting a real domain in this PR.
- Keep the current deployment IP-based staging until the checklist below is complete.
- Keep Product Readiness conservative: APFlow is demo-ready and pilot-shaped, but Production Ready remains no.
- Prevent public exposure from being treated as a production launch.

This PR does not change DNS, issue certificates, alter live proxy config, or modify `.env.staging`.

## B. Current State

- Staging is served by public IP today.
- If Nginx is currently serving the public web route on the VPS, verify it explicitly before changing anything. This repo also includes optional Caddy proxy templates under `deploy/`.
- Docker Compose services include API, web, PostgreSQL, Redis, and MinIO.
- The base Compose file publishes development-friendly container ports for API, web, PostgreSQL, Redis, and MinIO. The staging Compose override is expected to bind web/API to `127.0.0.1` for host-level Nginx and remove host publishing for PostgreSQL, Redis, and MinIO.
- Product Readiness should still show Production Ready: no.
- Priority writes remain disabled.
- `ALLOW_DEMO_RESET` should be false after seed testing.

## C. Decision Framework: Nginx vs Caddy

Option 1 - Continue with Nginx + Certbot:

- Pros: fits the current VPS if Nginx is already installed and serving the IP route.
- Pros: avoids proxy migration during the domain step.
- Cons: certificate renewal, redirect rules, and header configuration must be maintained explicitly.
- Cons: security headers and route behavior must be tested manually.

Option 2 - Use Caddy:

- Pros: automatic HTTPS and certificate renewal.
- Pros: simpler reverse proxy defaults.
- Pros: the repo already contains a Caddy proxy profile and examples.
- Cons: migration from any current Nginx setup must be tested.
- Cons: staging/prod split and single-domain routing must be verified before cutover.

Recommendation:

- Use Caddy for a future clean Domain + HTTPS path if the existing repo templates pass staging tests.
- Otherwise keep Nginx for the current staging IP until the final domain step.
- Do not make the operational decision in a docs-only PR.

## D. Required Prerequisites Before Connecting Domain

- [ ] Domain purchased or owned.
- [ ] DNS access confirmed.
- [ ] Subdomain selected, for example `staging.apflow.ai` or `app.apflow.ai`.
- [ ] DNS A record points to the VPS IP only when ready.
- [ ] `ALLOW_DEMO_RESET=false`.
- [ ] Product Readiness reviewed.
- [ ] Legal/privacy/data handling draft pack reviewed in [Legal / Privacy / Data Handling Pack](legal_privacy_data_pack.md).
- [ ] Counsel review completed before real customer pilot data or customer-facing legal terms.
- [ ] Real notification provider gate reviewed in [Notification Provider Readiness](notification_provider_readiness.md).
- [ ] Confirm `NOTIFICATION_REAL_DELIVERY_ENABLED=false` unless a separate approved provider rollout is underway.
- [ ] Confirm no vendor/customer notification links are sent externally before HTTPS is active.
- [ ] Backup completed.
- [ ] Operations health check run with `bash scripts/check_operations_health.sh http://46.101.97.231`.
- [ ] Backup age green or consciously accepted under [Scheduled Backup Policy](scheduled_backup_policy.md).
- [ ] Latest backup file is non-zero.
- [ ] Restore drill documented or tested.
- [ ] Backup/restore drill plan reviewed in [Backup / Restore / Disaster Recovery Drill](backup_restore_drill.md).
- [ ] Public ports reviewed.
- [ ] Public port/firewall hardening plan reviewed in [Public Port / Firewall Hardening Checklist](public_port_firewall_hardening.md).
- [ ] Internal service exposure reviewed.
- [ ] Reverse proxy and security headers plan reviewed in [Reverse Proxy Security Hardening](reverse_proxy_security_hardening.md).
- [ ] TLS configuration plan reviewed.
- [ ] Vendor access links will use HTTPS base URL.
- [ ] API base URL configured for HTTPS.
- [ ] Runtime verifier plan updated for HTTPS.
- [ ] Rollback plan prepared.

## E. Public Port Exposure Checklist

Desired future public exposure:

- 80 HTTP only for redirect or certificate challenge.
- 443 HTTPS.
- SSH restricted to admin IP if possible.

Should not be public in the future:

- PostgreSQL `5432`.
- Redis `6379`.
- MinIO API/console `9000` and `9001`, unless explicitly protected.
- API `8000` direct public exposure if reverse proxy owns `/api`.
- Web `3000` direct public exposure if reverse proxy owns `/`.

Inspection commands:

```bash
bash scripts/check_public_ports.sh
bash scripts/check_reverse_proxy.sh
bash scripts/check_operations_health.sh http://46.101.97.231
docker compose ps
sudo ss -tulpn
sudo ufw status verbose
```

If any internal service is reachable publicly, stop the domain cutover and fix firewall/proxy exposure first. PR #67 added the checklist and read-only inspection helper. PR #68 hardens staging Compose bind addresses but does not change live firewall rules. PR #69 adds reverse proxy security hardening templates and inspection guidance without changing live proxy config.

## F. Reverse Proxy Route Plan

Target single-domain routing:

```text
https://DOMAIN/
-> web app

https://DOMAIN/api/*
-> API service

https://DOMAIN/vendor?tenant_id=...&access_token=...
-> browser-friendly vendor portal

https://DOMAIN/api/health
-> API health

https://DOMAIN/api/ready
-> API readiness
```

Do not expose:

- PostgreSQL.
- Redis.
- MinIO console.
- Raw container ports.

## G. Security Headers Plan

Review and test these headers before enabling them broadly:

- `Strict-Transport-Security` after HTTPS is stable.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options` or CSP `frame-ancestors`.
- `Referrer-Policy`.
- `Permissions-Policy`.
- `Content-Security-Policy`, staged carefully because Next.js may need testing.

Do not blindly add strict CSP during the domain step. Start in report-only mode or test with the full AP, vendor, Priority Admin, and dashboard flows.

Use [Reverse Proxy Security Hardening](reverse_proxy_security_hardening.md) for the detailed proxy header, timeout, upload limit, vendor-token safety, validation, and rollback checklist before applying any live Nginx or Caddy change.

## H. TLS / HTTPS Checklist

- [ ] Valid certificate issued.
- [ ] Certificate auto-renewal verified.
- [ ] HTTP redirects to HTTPS.
- [ ] TLS test passes.
- [ ] HSTS added only after HTTPS is stable.
- [ ] No mixed content.
- [ ] Vendor links use HTTPS.
- [ ] API requests use HTTPS.
- [ ] Runtime verifier uses HTTPS URLs.

## I. Environment / Config Checklist

Review these future values during the domain cutover. Do not set them in this PR.

- `PUBLIC_APP_URL`.
- `API_PUBLIC_URL`.
- `NEXT_PUBLIC_API_BASE_URL`.
- Vendor access base URL if separate from `PUBLIC_APP_URL`.
- Cookie secure settings if applicable.
- `CORS_ALLOWED_ORIGINS`.
- Trusted hosts or proxy headers if added later.
- `ALLOW_DEMO_RESET=false`.
- Priority writes remain disabled unless there is a separate approved ERP write rollout.

## J. Backup And Rollback Checklist

Before domain cutover:

- [ ] Backup PostgreSQL.
- [ ] Backup document storage.
- [ ] Run or review the temporary restore drill in [Backup / Restore / Disaster Recovery Drill](backup_restore_drill.md).
- [ ] Record current git commit.
- [ ] Record current Docker images and Compose state.
- [ ] Test `/health`.
- [ ] Test `/ready`.
- [ ] Prepare DNS rollback plan.
- [ ] Prepare proxy config rollback plan.
- [ ] Keep the previous IP-based access path available until HTTPS verification passes.

## K. Go / No-Go Checklist

Go only if:

- [ ] Product Readiness reviewed.
- [ ] Demo reset off.
- [ ] Backups complete.
- [ ] Latest backup is fresh under the scheduled backup policy, or stale backup risk is consciously accepted and documented.
- [ ] Recent restore drill passed.
- [ ] Operations health check passes or warnings are understood.
- [ ] Direct internal ports closed or explicitly protected.
- [ ] HTTPS config tested.
- [ ] Runtime verifier passes through HTTPS.
- [ ] Vendor link works through HTTPS.
- [ ] AP workflow works through HTTPS.
- [ ] No 500 errors.
- [ ] No secrets exposed.

No-go if:

- `ALLOW_DEMO_RESET=true`.
- DB, Redis, or MinIO are exposed publicly without protection.
- Direct API/web ports remain public unexpectedly.
- Runtime verifier fails.
- Vendor links break.
- Mixed content appears.
- Production Ready accidentally claims ready.

## L. What This PR Does Not Do

- No domain connection.
- No DNS change.
- No real certificate issuance.
- No production launch.
- No real customer data onboarding.
- No legal/compliance certification claim.
- No live proxy changes.
- No `.env.staging` changes.
- No real Priority writes.
