# Staging Deployment

This runbook deploys APFlow AI to a private VPS using Docker Compose, PostgreSQL, Redis, filesystem document storage, Next.js, FastAPI, and optional Caddy HTTPS.

## Recommended VPS

- 2 vCPU minimum, 4 vCPU preferred.
- 4 GB RAM minimum, 8 GB preferred.
- 40 GB SSD minimum for demos; increase for invoice document retention.
- Ubuntu 22.04 or 24.04 LTS.
- Public IPv4 address.
- DNS access for the staging domain.

## Install Docker

On Ubuntu, install Docker Engine and the Compose plugin from Docker's official repository. Confirm:

```bash
docker --version
docker compose version
```

Add your deploy user to the `docker` group only if your security policy allows it. Otherwise run Docker commands with `sudo`.

The repository includes a conservative bootstrap helper for a fresh Ubuntu 24.04 VPS:

```bash
scripts/bootstrap_vps.sh --dry-run
scripts/bootstrap_vps.sh --execute
```

The script installs Docker from Docker's official Ubuntu repository, enables the Docker service, creates `/opt/apflow-ai`, and verifies `docker` plus `docker compose`. Review the dry-run output before using `--execute`.

## Copy Project

Clone or copy the repo onto the VPS:

```bash
git clone <your-private-repo-url> apflow-ai
cd apflow-ai
```

Keep `.env.staging` out of git.

## DNS

Default deployment uses subdomains:

- `PUBLIC_APP_HOST=app.example.com` points to the VPS.
- `API_PUBLIC_HOST=api.example.com` points to the VPS.

Create `A` records for both names. Wait for DNS propagation before starting Caddy.

Optional single-domain deployment is documented in `deploy/Caddyfile.single-domain.example`.

## Staging Environment

Create the staging env file:

```bash
cp .env.staging.example .env.staging
```

Edit every `replace-with-*` value.

Required values:

- `APP_ENV=staging`
- `PUBLIC_APP_URL=https://app.example.com`
- `API_PUBLIC_URL=https://api.example.com`
- `PUBLIC_APP_HOST=app.example.com`
- `API_PUBLIC_HOST=api.example.com`
- `CORS_ALLOWED_ORIGINS=https://app.example.com`
- `POSTGRES_PASSWORD=<strong random value>`
- `DATABASE_URL=postgresql+psycopg://apflow:<same password>@postgres:5432/apflow`
- `MINIO_ROOT_USER=<non-default user>`
- `MINIO_ROOT_PASSWORD=<strong random value>`
- `AUTH_ENABLED=true`
- `AUTH_SECRET_KEY=<at least 32 random chars>`
- `NEXT_PUBLIC_API_BASE_URL=https://api.example.com`

Use `DEMO_MODE=true` only for private demos. Use `DEMO_MODE=false` for realistic tenant/user testing.

## Start Stack

Without public HTTPS proxy:

```bash
scripts/deploy_staging.sh
```

With Caddy and Let's Encrypt:

```bash
PROXY=true scripts/deploy_staging.sh
```

The API container runs Alembic migrations before Uvicorn starts.

## Verify

Check service status:

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging ps
```

Run remote verification:

```bash
scripts/check_staging.sh https://api.example.com https://app.example.com
```

Or directly:

```bash
python scripts/verify_runtime.py --api-url https://api.example.com --web-url https://app.example.com --auth-enabled --email owner@example.com --password '<password>'
```

For partial checks during incident response:

```bash
python scripts/verify_runtime.py --api-url https://api.example.com --web-url https://app.example.com --auth-enabled --skip-upload
python scripts/verify_runtime.py --api-url https://api.example.com --web-url https://app.example.com --auth-enabled --skip-vendor
```

## Seed Demo Data

```bash
python scripts/seed_demo_data.py --api-base-url https://api.example.com
```

The script prints tenant and demo login details, but not bearer tokens.

## Logs

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging logs --tail=200 api
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging logs --tail=200 web
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging logs --tail=200 caddy
```

Startup logs should show environment, auth mode, demo mode, repository mode, OCR provider, storage provider, ERP adapters, and public URLs. They must not show secrets.

## Safe Restart

Restart application services:

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging restart api web
```

Restart everything:

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging restart
```

Stop without deleting data:

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging stop
```

Do not run this on staging unless data loss is intentional:

```bash
docker compose down -v
```

`down -v` deletes PostgreSQL, MinIO, Caddy, and document storage volumes.

## Backup PostgreSQL

```bash
scripts/backup_postgres.sh
```

The default output is `backups/apflow-<timestamp>.sql`. The script fails if the dump is empty and prints `ls -lh` for the created file.

Also back up uploaded document storage and MinIO volumes if invoice documents matter for the environment.

## Restore PostgreSQL

Restore is destructive. First do a dry run to confirm the file:

```bash
scripts/restore_postgres.sh backups/apflow-20260507T120000Z.sql
```

Then restore with explicit confirmation:

```bash
scripts/restore_postgres.sh backups/apflow-20260507T120000Z.sql --yes
```

The script stops API/web, drops and recreates the `apflow` database, restores the SQL file, and restarts API/web.

## Optional Single-Domain Caddy

Default Caddy uses:

- frontend: `https://app.example.com`
- API: `https://api.example.com`

For a single domain:

1. Copy `deploy/Caddyfile.single-domain.example` over `deploy/Caddyfile`.
2. Set:
   - `PUBLIC_APP_HOST=example.com`
   - `PUBLIC_APP_URL=https://example.com`
   - `API_PUBLIC_URL=https://example.com/api`
   - `NEXT_PUBLIC_API_BASE_URL=https://example.com/api`
   - `CORS_ALLOWED_ORIGINS=https://example.com`
3. Rebuild web because `NEXT_PUBLIC_API_BASE_URL` is baked into the Next.js build.

## Firewall

Allow inbound:

- SSH from trusted IPs.
- 80 and 443 for Caddy.

The base Compose file publishes service ports for local development. On a VPS, use a host firewall or provider firewall so only SSH, 80, and 443 are reachable publicly. Do not expose PostgreSQL, Redis, MinIO, FastAPI, or Next.js directly to the public internet.

## Real VPS Deployment Checklist

1. Provision Ubuntu 24.04 LTS with at least 2 vCPU, 4 GB RAM, and 40 GB SSD.
2. Point `app.example.com` and `api.example.com` `A` records to the VPS public IPv4.
3. Run `scripts/bootstrap_vps.sh --dry-run`, review it, then run `scripts/bootstrap_vps.sh --execute`.
4. Clone or copy the project into `/opt/apflow-ai`.
5. Copy `.env.staging.example` to `.env.staging`.
6. Replace every placeholder and use strong `POSTGRES_PASSWORD`, `AUTH_SECRET_KEY`, and MinIO credentials.
7. Set `PUBLIC_APP_URL`, `API_PUBLIC_URL`, `PUBLIC_APP_HOST`, `API_PUBLIC_HOST`, `CORS_ALLOWED_ORIGINS`, and `NEXT_PUBLIC_API_BASE_URL` to the real HTTPS domains.
8. Run `PROXY=true scripts/deploy_staging.sh`.
9. Confirm Caddy obtained certificates with `docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging logs --tail=200 caddy`.
10. Seed demo data if needed with `python scripts/seed_demo_data.py --api-base-url https://api.example.com`.
11. Run `scripts/check_staging.sh https://api.example.com https://app.example.com`.
12. Create a backup with `scripts/backup_postgres.sh` and confirm the file is non-empty.

## Troubleshooting

DNS not resolving:
Check `A` records for both subdomains and wait for TTL propagation. From the VPS, run `dig app.example.com` and `dig api.example.com` if `dnsutils` is installed.

Caddy certificate issue:
Confirm ports 80 and 443 are open to the internet, `PUBLIC_APP_HOST` and `API_PUBLIC_HOST` match DNS, and `CADDY_ACME_EMAIL` is set. Check `docker compose ... logs caddy`.

API not reachable:
Run `docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging ps` and check `api` health. Inspect `docker compose ... logs --tail=200 api`.

CORS blocked:
Set `CORS_ALLOWED_ORIGINS` to the exact frontend origin, for example `https://app.example.com`. Do not include a trailing slash or wildcard in staging/production.

Database migration failure:
Inspect API logs. The API runs Alembic before Uvicorn starts. Confirm `DATABASE_URL` uses the Compose service name `postgres`, the same `POSTGRES_PASSWORD`, and the `postgres` service is healthy.

Container restart loop:
Run `docker compose ... ps` and then `docker compose ... logs --tail=200 <service>`. Most staging loops are caused by unsafe env defaults, missing database credentials, or failed migrations.

File upload failing:
Check `MAX_INVOICE_UPLOAD_BYTES`, allowed content type, available disk space, and the `document-data` volume. `scripts/check_staging.sh` prints disk space and verifies the Postgres volume.

Wrong `NEXT_PUBLIC_API_BASE_URL`:
Next.js bakes this value at build time. Update `.env.staging`, then rebuild the web image with `PROXY=true scripts/deploy_staging.sh`.

401 or 403 auth issues:
Use `/auth/login` with the seeded owner or run `seed_demo_data.py` again for a private demo tenant. `401` means missing/invalid token; `403` means the user lacks tenant membership or permission.

Backup or restore issue:
Run `scripts/backup_postgres.sh` and verify the output file size. Restore only with `scripts/restore_postgres.sh <file> --yes`; it intentionally stops API/web and recreates the database.
