# Backup / Restore / Disaster Recovery Drill

This drill defines the recovery path APFlow should prove before Domain + HTTPS or real customer pilot work.

## A. Purpose

- Establish backup/restore readiness before public Domain + HTTPS.
- Provide a staging and pilot-readiness drill for PostgreSQL, document storage, deployment state, and restore verification.
- Keep this PR local to docs and safe helper scripts.
- Do not connect a real external backup provider in this PR.
- Do not commit secrets, `.env.staging`, database dumps, document archives, or generated backup inventories.

## B. What Must Be Protected

- PostgreSQL database.
- Uploaded invoice documents.
- Generated vendor access records, payment statuses, audit events, usage events, notification deliveries, and compliance/analytics data when DB-backed.
- `.env.staging` as a server-only secret/config file.
- `docker-compose.yml` and `docker-compose.staging.yml`.
- Current git commit SHA.
- Reverse proxy config if currently used.
- Object/document storage directory or MinIO volume, depending on the active document provider.

## C. Current Storage Assumptions

- PostgreSQL container service is `postgres`.
- Document storage provider may be filesystem or MinIO depending runtime configuration.
- `DOCUMENT_STORAGE_PROVIDER` and `DOCUMENT_STORAGE_PATH` must be checked from the running API environment.
- MinIO may be available even when the app uses filesystem document storage.
- Do not assume one storage mode blindly.

Inspect the running API and Compose state:

```bash
docker inspect apflowai-api-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'DOCUMENT_STORAGE|MINIO|POSTGRES|DATABASE|APP_ENV'
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging ps
```

If the Compose project name changes the API container name, get the actual API container from `docker compose ps`.

## D. PostgreSQL Backup Command

Preferred helper:

```bash
scripts/backup_staging.sh
```

Manual custom-format dump:

```bash
mkdir -p backups
BACKUP_TS=$(date -u +"%Y%m%dT%H%M%SZ")
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging exec -T postgres sh -lc \
  'pg_dump -U "${POSTGRES_USER:-apflow}" -d "${POSTGRES_DB:-apflow}" -Fc' \
  > "backups/apflow-postgres-${BACKUP_TS}.dump"
```

Verify the file:

```bash
ls -lh "backups/apflow-postgres-${BACKUP_TS}.dump"
file "backups/apflow-postgres-${BACKUP_TS}.dump" || true
```

Do not commit anything in `backups/`.

## E. PostgreSQL Restore Drill Plan

Do not restore directly into the active staging DB unless intentionally doing a destructive drill.

Preferred drill:

1. Create a temporary restore database inside the same Postgres container.
2. Restore the backup into the temporary DB.
3. Verify schema/table visibility and basic queries.
4. Drop the temporary DB after the drill.

Preferred helper:

```bash
scripts/restore_drill_staging.sh backups/apflow-postgres-YYYYMMDDTHHMMSSZ.dump
```

Manual drill outline:

```bash
BACKUP_TS=$(date -u +"%Y%m%dT%H%M%SZ")
RESTORE_DB="apflow_restore_drill_${BACKUP_TS}"

APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging exec -T postgres sh -lc \
  'createdb -U "${POSTGRES_USER:-apflow}" "$1"' sh "$RESTORE_DB"

cat "backups/apflow-postgres-${BACKUP_TS}.dump" | APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging exec -T postgres sh -lc \
  'pg_restore -U "${POSTGRES_USER:-apflow}" -d "$1"' sh "$RESTORE_DB"

APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging exec -T postgres sh -lc \
  'psql -U "${POSTGRES_USER:-apflow}" -d "$1" -c "\dt"' sh "$RESTORE_DB"

APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging exec -T postgres sh -lc \
  'dropdb -U "${POSTGRES_USER:-apflow}" "$1"' sh "$RESTORE_DB"
```

If you need to inspect the temporary DB after a failed drill, rerun the helper with `KEEP_RESTORE_DB=true` and drop it manually after review.

## F. Document Storage Backup

Handle both document storage modes.

Filesystem mode:

1. Identify `DOCUMENT_STORAGE_PATH` inside the API container.
2. Archive documents from the API container.

```bash
BACKUP_TS=$(date -u +"%Y%m%dT%H%M%SZ")
mkdir -p backups
docker exec apflowai-api-1 sh -lc 'tar -C /app/.storage -czf /tmp/apflow-documents.tgz documents'
docker cp apflowai-api-1:/tmp/apflow-documents.tgz "backups/apflow-documents-${BACKUP_TS}.tgz"
ls -lh "backups/apflow-documents-${BACKUP_TS}.tgz"
```

MinIO mode:

- Document current MinIO bucket names before backup.
- Prefer `mc mirror` for a future external backup target.
- Do not paste real MinIO secrets into docs, logs, shell history, or chat.

Placeholder only:

```bash
mc alias set apflow-minio http://127.0.0.1:9000 ACCESS_KEY SECRET_KEY
mc mirror apflow-minio/BUCKET "backups/minio-BUCKET-${BACKUP_TS}/"
```

Use server-only environment values or secure shell history practices for real credentials.

## G. Config / State Inventory

Record enough state to reproduce or roll back a deployment:

```bash
BACKUP_TS=$(date -u +"%Y%m%dT%H%M%SZ")
mkdir -p backups
git rev-parse HEAD > "backups/git-head-${BACKUP_TS}.txt"
git status --short > "backups/git-status-${BACKUP_TS}.txt"
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging config > "backups/compose-config-${BACKUP_TS}.yml"
docker images | grep apflowai > "backups/docker-images-${BACKUP_TS}.txt" || true
docker ps > "backups/docker-ps-${BACKUP_TS}.txt"
sudo nginx -T > "backups/nginx-config-${BACKUP_TS}.txt" 2>/dev/null || true
```

If Caddy is used in a future deployment:

```bash
sudo caddy validate --config /path/to/Caddyfile
```

Do not commit generated backup inventories because they may contain environment-derived paths or operational details.

## H. Restore Verification Checklist

After a restore drill or real restore:

- [ ] `/health` returns ok.
- [ ] `/ready` returns ready.
- [ ] Runtime verifier passes.
- [ ] Demo login works.
- [ ] Invoice list loads.
- [ ] Uploaded document can be accessed if storage was restored.
- [ ] Audit Trail loads.
- [ ] Vendor access data exists if expected.
- [ ] Payment statuses exist if expected.
- [ ] Usage, analytics, and compliance panels load.

## I. Disaster Rollback Checklist

- [ ] Record current git commit before deploy.
- [ ] Restore previous git commit if code rollback is needed.
- [ ] Rebuild or restart with Docker Compose.
- [ ] Restore DB from backup only if data corruption occurred.
- [ ] Restore document archive only if document loss occurred.
- [ ] Verify `/health`.
- [ ] Verify `/ready`.
- [ ] Run runtime verifier.
- [ ] Confirm no unexpected 500 errors.

Code rollback does not automatically roll back database migrations. Inspect migration history before restoring an older application version.

## J. Frequency Recommendation

For staging:

- Before risky PRs.
- Before Domain + HTTPS.
- Before real customer pilot.
- After major migrations.

For future production:

- Scheduled daily database backup.
- Document storage backup or mirror.
- Off-server encrypted copy.
- Periodic restore drill.
- Retention policy.

## K. What This PR Does Not Do

- No real scheduled backups.
- No cloud backup provider.
- No external backup destination.
- No automated destructive restore.
- No `.env.staging` backup committed.
- No production/domain/HTTPS changes.
