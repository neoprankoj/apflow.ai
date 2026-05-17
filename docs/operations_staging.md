# Staging Operations

This guide covers repeatable operations for the private staging environment. It complements [deployment.md](deployment.md) for initial VPS setup and [runbook.md](runbook.md) for product-specific workflows.

## A. Staging stack overview

The staging stack currently includes:

- `api`: FastAPI backend, Alembic startup migrations, SQLAlchemy/PostgreSQL mode.
- `web`: Next.js dashboard.
- `postgres`: primary persistent data store.
- `redis`: cache/queue-style service, not the primary source of truth today.
- `minio`: available for object storage experiments; current documents use filesystem storage.
- reverse proxy:
  - live private staging may use host-managed Nginx.
  - the repo also includes optional Caddy through the Compose `proxy` profile.

The expected application directory on the VPS is:

```bash
/opt/b2b-app/apflowai
```

Use the staging Compose pair consistently:

```bash
APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging ...
```

## B. Standard deploy procedure

Run from `/opt/b2b-app/apflowai`:

```bash
git fetch
git checkout staging
git pull origin staging
git log --oneline --max-count=5
git show --stat --oneline HEAD

APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging down --remove-orphans

APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging up -d --build

APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging ps

curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl -I http://46.101.97.231
python3 scripts/verify_runtime.py \
  --api-url http://46.101.97.231/api \
  --web-url http://46.101.97.231 \
  --auth-enabled
```

If the deployment uses the optional Caddy profile, add `--profile proxy` to the Compose commands or use `PROXY=true scripts/deploy_staging.sh`.

## C. Docker cache recovery

If Docker build snapshots or layer cache become inconsistent, use the least destructive fix that resolves the issue:

```bash
docker builder prune -f
docker image prune -f

APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging build --no-cache web
```

Stronger fallback:

```bash
docker system prune -af
```

Do **not** run `docker system prune --volumes` on staging unless you intentionally want to delete persistent data.

## D. PostgreSQL backup

Current Compose defaults are `POSTGRES_USER=apflow` and `POSTGRES_DB=apflow`. Confirm them against `.env.staging` before using manual commands.

Manual dump:

```bash
mkdir -p backups
timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging exec -T postgres \
  pg_dump -U apflow -d apflow --clean --if-exists > "backups/apflow_${timestamp}.sql"
```

Preferred helper already in the repo:

```bash
scripts/backup_postgres.sh
```

The helper creates a timestamped dump, fails on an empty file, and prints the resulting file size.

## E. PostgreSQL restore

Restoring a dump can overwrite current staging database data.

1. Create a fresh backup first.
2. Stop user-facing services before restoring:

```bash
APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging stop api web
```

3. Dry-run the checked helper:

```bash
scripts/restore_postgres.sh backups/apflow-YYYYMMDDTHHMMSSZ.sql
```

4. Perform the destructive restore only after review:

```bash
scripts/restore_postgres.sh backups/apflow-YYYYMMDDTHHMMSSZ.sql --yes
```

5. Re-run readiness and runtime verification after services restart.

## F. Document storage backup

Current staging uses:

```text
DOCUMENT_STORAGE_PROVIDER=filesystem
DOCUMENT_STORAGE_PATH=/app/.storage/documents
```

The base Compose file mounts that path from the named `document-data` volume. Inspect the actual deployment before backing it up:

```bash
docker volume ls
docker inspect apflowai-api-1
APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging config
```

If you do not need the host volume path, copy documents directly from the running API container:

```bash
timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
mkdir -p "backups/documents_${timestamp}"
docker cp apflowai-api-1:/app/.storage/documents "backups/documents_${timestamp}"
```

If document storage later moves to MinIO/object storage, also back up the `minio-data` volume and revise this runbook.

## G. Restore document storage

Restore document files only with a matching database state. Database rows and document files must agree.

Example restore:

```bash
docker cp backups/documents_YYYYMMDDTHHMMSSZ/documents apflowai-api-1:/app/.storage/
```

After copying files back, verify upload/extract/process flows against a known invoice.

## H. Redis

Redis is currently a cache/queue-style service and is not the authoritative store for invoices, review tasks, approvals, or audit history. If durable queues or workflow guarantees are added later, update this runbook before relying on Redis recovery semantics.

## I. Demo reset procedure

`ALLOW_DEMO_RESET=false` is the safe default.

For controlled staging cleanup only:

1. Set `ALLOW_DEMO_RESET=true` in `.env.staging`.
2. Restart the stack or at least the API service.
3. Perform the reset as an owner/admin.
4. Set `ALLOW_DEMO_RESET=false` again.
5. Restart the stack again.
6. Verify the clean state.

Do not leave `ALLOW_DEMO_RESET=true` enabled.

## J. Seeding demo data

Current seed modes from `scripts/seed_demo_data.py`:

- `clean`
- `approval-ready`
- `review-required`
- `vendor-preview`
- `inbox-demo`
- `all`

Check the current CLI before use:

```bash
python3 scripts/seed_demo_data.py --help
```

Example:

```bash
python3 scripts/seed_demo_data.py \
  --api-base-url http://46.101.97.231/api \
  --mode inbox-demo
```

The script uses the running API and does not call live OCR during deterministic seed modes.

## K. Rollback procedure

Inspect recent history:

```bash
git log --oneline --max-count=10
```

Two rollback patterns:

```bash
git checkout <previous-good-commit>
```

or, when reverting a merged PR on `staging`:

```bash
git revert -m 1 <merge_commit_sha>
```

Then rebuild, restart, and run the health/runtime checks from the standard deploy procedure.

Code rollback does not automatically roll back database migrations. If a release changed schema, inspect Alembic history first and restore a database backup when necessary.

## L. Alembic and migrations

The API container runs migrations on startup with:

```text
alembic -c alembic.ini upgrade head
```

Manual commands inside the container:

```bash
APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging exec api alembic -c alembic.ini current

APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging exec api alembic -c alembic.ini upgrade head
```

Treat downgrades as destructive operations. Inspect the migration history and take a fresh database backup before attempting one.

## M. Health and readiness verification

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl -I http://46.101.97.231
python3 scripts/verify_runtime.py \
  --api-url http://46.101.97.231/api \
  --web-url http://46.101.97.231 \
  --auth-enabled
```

## N. Logs

```bash
APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging logs api --tail=200

APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging logs web --tail=200

APFLOW_ENV_FILE=.env.staging docker compose \
  -f docker-compose.yml \
  -f docker-compose.staging.yml \
  --env-file .env.staging logs --tail=200
```

If the deployment uses Caddy, inspect `caddy` logs as well. If it uses host-managed Nginx, inspect the host service logs separately.

## O. Security reminders

- Never commit `.env.staging`.
- Never commit OCR.space keys, Azure keys, private keys, tokens, or real invoice files.
- Keep `ALLOW_DEMO_RESET=false` except during controlled cleanup.
- Keep authentication enabled.
- Keep PostgreSQL, Redis, MinIO, and internal app ports restricted from the public internet.
- Rotate credentials immediately if exposed.
- Use SSH keys instead of passwords.
- Keep backups private and test restores before relying on them.

## Pre-deploy checklist

- [ ] Current branch and target commit are confirmed.
- [ ] Fresh PostgreSQL backup exists.
- [ ] `.env.staging` remains uncommitted and secret values are still present.
- [ ] Compose config validates.
- [ ] Rollback target is known.

## Post-deploy checklist

- [ ] `docker compose ps` shows healthy services.
- [ ] `/health` returns `ok`.
- [ ] `/ready` returns `ready`.
- [ ] Public web endpoint responds.
- [ ] Runtime verifier passes.
- [ ] Logs show no migration or startup errors.

## Before destructive operation checklist

- [ ] Fresh database backup exists and is non-empty.
- [ ] Document storage backup exists when document retention matters.
- [ ] Restore target and blast radius are understood.
- [ ] API/web are stopped before destructive restore.
- [ ] A rollback plan is documented.

## Incident quick checklist

- [ ] Check `docker compose ps`.
- [ ] Check API and web logs.
- [ ] Check `/health` and `/ready`.
- [ ] Confirm recent deploy commit.
- [ ] Confirm disk space and Docker volume presence.
- [ ] Re-run the runtime verifier.
- [ ] If data risk exists, take a backup before further changes.
