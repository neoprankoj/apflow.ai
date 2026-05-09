# Staging Security Checklist

Before exposing a staging APFlow AI deployment:

- `AUTH_ENABLED=true`.
- `AUTH_SECRET_KEY` is at least 32 random characters and not the dev default.
- `DEMO_MODE=false`, or `DEMO_MODE=true` only for a private demo with limited access.
- `POSTGRES_PASSWORD` is strong and not reused elsewhere.
- `DATABASE_URL` uses the same strong PostgreSQL password.
- `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` are changed from `minioadmin`.
- `CORS_ALLOWED_ORIGINS` contains only the staging frontend origin.
- `PUBLIC_APP_URL`, `API_PUBLIC_URL`, `PUBLIC_APP_HOST`, and `API_PUBLIC_HOST` are real staging values.
- HTTPS is enabled through Caddy or another reverse proxy.
- DNS points only to the intended VPS.
- No `.env.staging`, cloud keys, tokens, or database backups are committed to git.
- Logs do not include passwords, bearer tokens, OCR keys, database URLs with passwords, MinIO credentials, or raw invoice bytes.
- Uploaded files are not publicly served from the filesystem or MinIO without application authorization.
- PostgreSQL backups are scheduled and restore has been tested.
- `docker compose down -v` is not used for normal restarts.
- SSH is limited to trusted users and ideally trusted source IPs.
- VPS firewall allows only SSH, HTTP, and HTTPS from the public internet.
- The Caddy admin API is not publicly exposed.
- Real OCR/ERP/email credentials are stored only in environment/secret management, not in request payloads or docs.
- `scripts/check_staging.sh` passes against the HTTPS API and web URLs.
- `scripts/backup_postgres.sh` creates a non-empty backup before each deploy.
- Restore has been dry-run with `scripts/restore_postgres.sh <backup-file>` and the destructive `--yes` path is understood.
- Public DNS only points the intended staging subdomains at this VPS.
- `NEXT_PUBLIC_API_BASE_URL` is the HTTPS API URL used by the deployed frontend build.
- `APFLOW_VERIFY_EMAIL` and `APFLOW_VERIFY_PASSWORD`, if used for checks, are staging-only credentials.

Production additionally requires:

- `APP_ENV=production`.
- `AUTH_ENABLED=true`.
- `DEMO_MODE=false` unless a controlled exception sets `ALLOW_DEMO_MODE_IN_PRODUCTION=true`.
- Domain, CORS, and email/vendor communication policies are reviewed before customer data is uploaded.
