# Scheduled Backup Policy

## A. Purpose

This document defines the APFlow staging backup routine before Domain + HTTPS.

- This is policy and templates only.
- No live schedule is installed by this PR.
- Manual backup and restore drill helpers already work.
- Domain + HTTPS work, risky deploys, and pilot data import should not proceed without acceptable backup freshness.

## B. Current Backup State

- `scripts/backup_staging.sh` creates PostgreSQL custom-format dumps.
- `scripts/restore_drill_staging.sh` restores a dump into a temporary database for a non-destructive drill.
- `scripts/check_operations_health.sh` reports latest backup age through `scripts/check_backup_age.sh`.
- Document storage backup remains documented in [Backup / Restore / Disaster Recovery Drill](backup_restore_drill.md), but it is not fully automated or offsite yet.
- Backups are local to the VPS unless an operator manually copies them elsewhere.

## C. Backup Frequency Policy

Staging:

- Run a backup before risky PRs or deploys.
- Run a backup before Domain + HTTPS work.
- Run a backup before importing pilot data.
- Run at least daily while pilot data exists.

Future production:

- Daily database backups minimum.
- More frequent database backups if real customer volume increases.
- Document storage backup or mirror.
- Offsite encrypted copy.
- Restore drill monthly or before major migrations.

## D. Backup Age Policy

- Green: latest valid backup is `<= 24` hours old.
- Warning: latest valid backup is `> 24` hours old.
- Critical: no valid backup exists, or latest valid backup is `> 72` hours old before risky work.
- No Domain + HTTPS work if backup is missing or stale.
- No real pilot data import if backup is missing or stale.
- Zero-byte dumps are invalid.
- `.partial` files are ignored.

## E. Retention Draft

Staging draft:

- Keep daily backups for 7 days.
- Keep weekly backups for 4 weeks if storage allows.
- Never delete the latest known-good backup automatically.
- Use manual cleanup only until retention automation is reviewed.

Future production draft:

- Keep daily backups for 14-30 days.
- Keep weekly backups for 2-3 months.
- Keep monthly archives if required by customer terms or regulation.
- Maintain an offsite encrypted copy.

## F. Backup Log Policy

- Logs should go to `backups/logs/`.
- Backup command stdout/stderr should be captured.
- Failures should be visible in `scripts/check_operations_health.sh` output or runbook review.
- Do not log secrets, `.env.staging`, database passwords, provider keys, bearer tokens, or raw vendor tokens.

## G. Cron Template

Template only. Do not install blindly.

Example daily backup at 02:15 UTC:

```cron
15 2 * * * cd /opt/b2b-app/apflowai && ./scripts/backup_staging.sh >> backups/logs/backup-staging.log 2>&1
```

Notes:

- Cron has a limited environment.
- Use absolute paths.
- Verify the command with a manual dry run first.
- Ensure `backups/logs/` exists before the first scheduled run.
- Confirm the backup file is non-zero.
- Confirm restore drills periodically.
- Do not paste secrets into crontab.
- Do not add deletion logic to the cron entry.

## H. systemd Timer Template

Docs-only templates are available:

- [apflow-backup-staging.service](examples/apflow-backup-staging.service)
- [apflow-backup-staging.timer](examples/apflow-backup-staging.timer)

They are not installed by this PR. Review them before use, run a manual backup first, confirm logs after the first timer run, and do not install on production without a separate production backup plan review.

## I. Offsite Backup Future Plan

Local VPS backups are not enough for production.

Future offsite options:

- Object storage bucket.
- Encrypted `rsync` destination.
- Provider snapshot.
- Dedicated backup service.

Any offsite plan must include encryption, least-privilege access control, restore testing, retention rules, and alerting. Do not implement offsite backup in this PR.

## J. Restore Drill Policy

Run a restore drill:

- After changing backup scripts.
- Before Domain + HTTPS.
- Before pilot data import.
- Periodically during a pilot.
- Before major migrations.

Document:

- Backup filename.
- Temporary restore database name.
- Table count.
- `/health` and `/ready` after the drill.
- Runtime verifier result when applicable.

## K. Failure Handling

If backup fails:

1. Do not continue risky deployment, Domain + HTTPS work, or pilot data import.
2. Check disk space.
3. Check PostgreSQL readiness.
4. Check the database identity: `app_user` / `apflow`.
5. Check container health.
6. Rerun backup manually.
7. Do not delete the previous known-good backup.

## L. What This PR Does Not Do

- No live cron job installation.
- No system crontab changes.
- No systemd service or timer installation.
- No automatic backup deletion.
- No cloud/offsite backup provider.
- No `.env.staging` changes.
- No secrets.
- No Domain + HTTPS changes.
- No Priority writes.
