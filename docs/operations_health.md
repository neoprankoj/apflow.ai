# Operations Health

## A. Purpose

This document defines a basic staging operations health foundation for APFlow.

- Designed for pre-domain and pilot readiness.
- Gives founder/operators one safe place to check staging health before demos, public access work, or risky operations.
- Connects no external monitoring provider yet.
- Uses read-only checks only.

## B. What This Checks

The operations health flow checks:

- Docker Compose service status.
- API `/health`.
- API `/ready`.
- Public proxy `/api/health` when a public base URL is supplied.
- Public web response when a public base URL is supplied.
- PostgreSQL readiness.
- Root filesystem disk usage.
- Docker disk usage when available.
- Backup freshness using the policy in [Scheduled Backup Policy](scheduled_backup_policy.md).
- `ALLOW_DEMO_RESET` status.
- Public port exposure inspection.
- Reverse proxy inspection.
- Real notification provider gate reminder in [Notification Provider Readiness](notification_provider_readiness.md).
- Runtime verifier reminder.

## C. What This Does Not Do

- No uptime provider.
- No real alerts.
- No SMS, email, Slack, Teams, or webhook notifications.
- No real notification provider connection; mock remains the safe default.
- No log aggregation.
- No automated remediation.
- No destructive cleanup.
- No service restarts.
- No firewall, proxy, Domain + HTTPS, or certificate changes.

## D. Daily Staging Health Checklist

Run these on the staging host:

```bash
docker compose ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl -I http://46.101.97.231
curl -i http://46.101.97.231/api/health
bash scripts/check_public_ports.sh
bash scripts/check_reverse_proxy.sh http://46.101.97.231
bash scripts/check_operations_health.sh http://46.101.97.231
```

Runtime verifier reminder:

```bash
python3 scripts/verify_runtime.py --api-url http://46.101.97.231/api --web-url http://46.101.97.231 --auth-enabled
```

## E. Disk Usage Policy

- Warn above `75%` on the root filesystem.
- Treat above `90%` on the root filesystem as critical.
- Check Docker disk usage when `docker system df` is available.
- Do not delete logs, images, containers, volumes, backups, or uploads automatically.
- Do not run `docker system prune` from this health check.

## F. Backup Freshness Policy

- Green: latest valid backup is `<= 24` hours old.
- Warning: latest valid backup is `> 24` hours old.
- Critical: no valid backup exists, or latest valid backup is `> 72` hours old before risky work.
- Treat no valid backup as blocking before Domain + HTTPS or real customer pilot data.
- Reject zero-byte dumps as invalid.
- Repeat the backup/restore drill before a real customer pilot.
- Do not delete old backups from health checks.
- Full policy: [Scheduled Backup Policy](scheduled_backup_policy.md).

## G. Operational Escalation

If health fails:

1. Check `docker compose ps`.
2. Check API logs.
3. Check web logs.
4. Check disk space.
5. Check backup freshness.
6. Do not run destructive cleanup unless a recent backup exists and the cleanup plan is understood.
7. Use rollback/runbook guidance if the failure is deploy-related.

Useful log commands:

```bash
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging logs api --tail=120
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging logs web --tail=120
```

## H. Future Monitoring Providers

Future monitoring work may add:

- Uptime monitor.
- Error tracking.
- Log retention.
- Backup-failure alert.
- Disk usage alert.
- SSL certificate expiry alert after HTTPS.

Do not choose or connect a monitoring provider in this PR. Provider selection should happen in a separate implementation after Domain + HTTPS and pilot requirements are clear.
