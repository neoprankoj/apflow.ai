# Reverse Proxy Security Hardening

## A. Purpose

- Prepare APFlow reverse proxy security before Domain + HTTPS.
- Keep this as a planning and template PR only.
- Make no live proxy change.
- Issue no certificate.
- Keep Domain + HTTPS deferred.

This document gives the founder/operator a reviewable route, header, upload, and rollback plan before a real customer-facing hostname is connected.

## B. Current Reverse Proxy State

- Nginx currently serves public HTTP on port `80`.
- Nginx proxies the public web route to the localhost-bound web service.
- Nginx proxies `/api` to the localhost-bound API service.
- Docker services are no longer publicly exposed after PR #68:
  - web is expected on `127.0.0.1:3000`;
  - API is expected on `127.0.0.1:8000`;
  - PostgreSQL, Redis, and MinIO are not host-published by the staging override.
- UFW allows `443` for future HTTPS, but HTTPS is not connected yet.
- Domain + HTTPS remain intentionally deferred.

## C. Target Reverse Proxy Behavior

Future desired behavior:

- `http://DOMAIN` redirects to `https://DOMAIN`.
- `https://DOMAIN` serves the web app.
- `https://DOMAIN/api/*` proxies to the API.
- `https://DOMAIN/vendor?tenant_id=...&access_token=...` supports browser vendor access links.
- API and web remain localhost-bound or internal behind the reverse proxy.
- PostgreSQL, Redis, and MinIO remain non-public.
- Request body limits support invoice PDFs and images.
- Proxy timeouts support upload, OCR, and review flows.
- Security headers are applied carefully and verified through the full app workflow.

## D. Nginx Hardening Checklist

Before a future live config change, prepare and review an Nginx server block with:

- [ ] `server_name DOMAIN` placeholder replaced only during the approved Domain + HTTPS PR.
- [ ] Web route proxying to `http://127.0.0.1:3000`.
- [ ] `/api/` route proxying to `http://127.0.0.1:8000`.
- [ ] `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Host`, and `X-Forwarded-Proto` preserved.
- [ ] `client_max_body_size` sized for invoice PDFs/images, for example `25m`.
- [ ] `proxy_read_timeout` and `proxy_send_timeout` long enough for OCR/upload flows, for example `120s`.
- [ ] Optional gzip or Brotli reviewed after confirming asset behavior.
- [ ] Access and error log locations documented.
- [ ] Safe validation and reload sequence used:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Do not restart Nginx blindly during the cutover. Reload only after `nginx -t` passes.

## E. Security Headers Plan

Recommended low-risk headers:

- `X-Content-Type-Options: nosniff`.
- `Referrer-Policy: strict-origin-when-cross-origin`.
- `X-Frame-Options: DENY` or `SAMEORIGIN`, or CSP `frame-ancestors` after the embedding policy is confirmed.
- Minimal `Permissions-Policy`, for example disable camera, microphone, geolocation, and payment unless a product flow explicitly requires them.

HTTPS-only later:

- `Strict-Transport-Security` only after HTTPS is stable and rollback risk is understood.

CSP plan:

- Plan Content Security Policy carefully.
- Start with `Content-Security-Policy-Report-Only` if implemented later.
- Do not add strict CSP blindly because Next.js assets, API calls, fonts, images, OCR upload flows, and future provider integrations need testing.
- Validate CSP against the AP manager workflow, vendor portal, chatbot, admin panels, and readiness pages before enforcing it.

## F. TLS / HTTPS Notes

- Certificate issuance should happen only in a later Domain + HTTPS PR.
- HSTS should be enabled only after HTTPS is stable.
- Verify no mixed content before using the domain for demos or pilots.
- Vendor links must use an HTTPS base URL before real public vendor access is sent.
- Runtime verification should run against both `https://DOMAIN/api` and `https://DOMAIN`.

Example future verifier:

```bash
python3 scripts/verify_runtime.py --api-url https://DOMAIN/api --web-url https://DOMAIN --auth-enabled
```

## G. Upload / Proxy Limits

- Invoice uploads need a request body allowance that covers realistic PDFs and scanned images.
- OCR calls may take longer than ordinary API reads.
- Proxy timeouts should not be too short for upload, extraction, and process flows.
- Test oversized uploads and confirm a controlled `413` response.
- Test slow OCR/provider paths and confirm they do not produce avoidable `504` timeouts.
- Keep limits explicit so future operators know whether a failure is caused by the app or the proxy.

## H. Vendor Portal / Token Safety Through Proxy

- Vendor links should use HTTPS.
- Vendor access tokens are query parameters today, so HTTPS is mandatory before real public vendor links are sent.
- Avoid logging full query strings in future proxy access logs where possible.
- Never expose token hashes.
- Rotate or revoke vendor tokens if they appear in screenshots, browser history, logs, tickets, chat, or documentation.

## I. Reverse Proxy Validation Checklist

Before applying real config:

- [ ] Back up the current Nginx config.
- [ ] `sudo nginx -t` passes.
- [ ] Reload Nginx; do not restart blindly.
- [ ] `curl -I` public web route.
- [ ] `curl` public `/api/health`.
- [ ] Runtime verifier passes through the proxy.
- [ ] Browser login works.
- [ ] Invoice upload, OCR, and process flow work.
- [ ] Vendor link works.
- [ ] Vendor chatbot works.
- [ ] Notification, analytics, usage, and compliance panels load.
- [ ] No Priority writes are enabled.
- [ ] No `.env.staging` or secret changes are committed.

Read-only helper:

```bash
bash scripts/check_reverse_proxy.sh
bash scripts/check_reverse_proxy.sh http://46.101.97.231
```

## J. Rollback Checklist

If the proxy change fails:

- [ ] Restore the previous Nginx config.
- [ ] Run `sudo nginx -t`.
- [ ] Reload Nginx.
- [ ] Verify public web and public API health.
- [ ] Do not touch PostgreSQL, Redis, MinIO, or Docker volumes.
- [ ] Keep Domain + HTTPS disabled until the failed condition is understood.
