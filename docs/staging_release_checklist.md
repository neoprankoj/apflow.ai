# Staging Release Checklist

Use this checklist before and after deploying APFlow AI to staging. For the detailed operating procedure, see [operations_staging.md](operations_staging.md).

## Pre-deploy

- [ ] Confirm the target branch and commit are correct.
- [ ] Confirm `.env.staging` exists only on the server and is not committed.
- [ ] Confirm required GitHub Actions secrets are configured for staging deployment.
- [ ] Confirm database migrations are ready for the release.
- [ ] Confirm the rollback target commit is known.

## Validate before deploy

Run from the repo root:

```bash
npm --workspace apps/web run lint
npm --workspace apps/web run build
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs api --tail=80
```

## Post-deploy

- [ ] `GET /health` returns healthy.
- [ ] `GET /ready` returns ready.
- [ ] Dashboard loads.
- [ ] Approval Inbox loads.
- [ ] Invoice upload flow works.
- [ ] Vendor-safe preview works.
- [ ] Mock ERP export works.

## Rollback notes

1. Identify the previous known-good commit.
2. Redeploy that previous commit through the normal staging deployment path.
3. Check container status with `docker compose ps`.
4. Verify `/health` and `/ready` again before handing staging back to users.

