# Public Port / Firewall Hardening Checklist

This checklist prepares APFlow for future Domain + HTTPS by reviewing public port exposure before public access changes.

## A. Purpose

- Prepare APFlow for future Domain + HTTPS by reviewing public port exposure.
- Keep firewall changes and public Domain + HTTPS changes out of this PR.
- Bind staging app/debug ports to localhost through the staging Compose override.
- Make no live firewall changes.
- Avoid any command path that could lock out SSH.

## B. Current Risk Model

- Earlier staging checks showed several Docker-published ports bound to all interfaces.
- Publicly published container ports may be reachable outside the host.
- UFW alone may not reliably protect Docker-published ports because Docker manipulates iptables/NAT.
- Desired model: reverse proxy owns public ingress; app and internal services are bound to localhost or the internal Docker network.
- UFW and provider firewalls are defense-in-depth, not substitutes for correct Docker bind addresses and reverse proxy topology.
- PR #68 moves staging Compose bindings for web and API to `127.0.0.1` and removes host publishing for PostgreSQL, Redis, and MinIO. The app still reaches internal services over the Docker network, while Nginx can reach web/API locally.

## C. Current Inspection Commands

Run these on the VPS before any public access or firewall change:

```bash
docker compose ps
sudo ss -tulpn
sudo ufw status verbose
sudo iptables -S | head -n 80
sudo iptables -t nat -S | head -n 120
docker ps --format 'table {{.Names}}\t{{.Ports}}'
APFLOW_ENV_FILE=.env.staging docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging ps
```

Read-only helper:

```bash
bash scripts/check_public_ports.sh
```

## D. Current Expected Ports To Review

Ports that were previously observed as publicly bound and must now be checked after PR #68:

- `3000` web.
- `8000` API.
- `5432` PostgreSQL.
- `6379` Redis.
- `9000` / `9001` MinIO.
- `80` Nginx/proxy if present. This is expected to remain public for current IP-based access.
- `22` SSH.

The desired post-PR #68 result is `127.0.0.1` binding for `3000` and `8000`, and no host binding for `5432`, `6379`, `9000`, and `9001`. The actual list must be confirmed on the VPS with the inspection commands.

## E. Desired Future Public Exposure

Desired public:

- `80` HTTP only for redirect or ACME challenge.
- `443` HTTPS.
- `22` SSH, preferably restricted by source IP or provider firewall if possible.

Not public:

- `3000` web direct.
- `8000` API direct.
- `5432` PostgreSQL.
- `6379` Redis.
- `9000` / `9001` MinIO.
- Any internal object storage, database, or cache port.

## F. Docker Compose Hardening Plan

Current staging target pattern after PR #68:

- Web and API host ports bind to `127.0.0.1`.
- PostgreSQL, Redis, and MinIO are not host-published.
- Nginx remains the current public ingress on port `80`.
- Domain + HTTPS remain deferred.
- If inspection still shows these service ports on `0.0.0.0` or `[::]`, hardening is incomplete.

Future production/domain target pattern:

- Reverse proxy publishes `80` and `443`.
- Web service binds to the internal Docker network only, or to `127.0.0.1` if a host proxy needs it.
- API service binds to the internal Docker network only, or to `127.0.0.1` if a host proxy needs it.
- PostgreSQL, Redis, and MinIO do not publish public host ports in staging/prod.
- Local-only debug ports, if needed, bind to `127.0.0.1`.

Examples only:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

Or remove `ports` and use `expose` or internal networks where appropriate.

Binding to `127.0.0.1` makes the port accessible from the host, not directly from the internet.

See [docker-compose.public-hardening.example.yml](examples/docker-compose.public-hardening.example.yml) for a docs-only override example. Do not apply it without testing.

## G. UFW Hardening Plan

Safe future sequence:

1. Confirm console/provider recovery access.
2. Confirm SSH access rule before enabling UFW.
3. Allow SSH.
4. Allow HTTP/HTTPS.
5. Default deny incoming.
6. Default allow outgoing.
7. Enable UFW only after confirming rules.
8. Verify a new SSH session before closing the old session.
9. Verify app access via reverse proxy.
10. Verify internal ports are not public.

Example commands, do not run blindly:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status verbose
```

Do not run `ufw enable` from this checklist unless recovery access and SSH rules are confirmed.

## H. Provider Firewall Checklist

For DigitalOcean or another cloud provider firewall:

- Allow SSH from admin IP where feasible.
- Allow `80` and `443` from anywhere.
- Block DB/cache/object storage ports.
- Document current droplet firewall state.
- Do not rely only on server UFW if Docker publishes ports.

## I. Public Exposure Verification Checklist

After future hardening:

From local machine/browser:

- [ ] `https://DOMAIN` works.
- [ ] `https://DOMAIN/api/health` works.
- [ ] Vendor link works.

From outside the VPS host, verify these are closed:

- [ ] `3000`.
- [ ] `8000`.
- [ ] `5432`.
- [ ] `6379`.
- [ ] `9000`.
- [ ] `9001`.

From the VPS host, internal checks still work:

- [ ] `curl http://127.0.0.1:8000/health` if intentionally local-bound.
- [ ] `docker compose ps`.
- [ ] Runtime verifier through public HTTPS URL.

Use caution with port scanners. Keep checks basic, authorized, and responsible.

## J. Rollback Plan

If firewall/proxy hardening breaks access:

1. Use provider console.
2. Revert firewall rule.
3. Restore previous proxy config.
4. Revert Compose override.
5. Run `docker compose up -d`.
6. Verify SSH.
7. Verify `/health`.
8. Verify `/ready`.

## K. Go / No-Go Before Domain + HTTPS

Go only if:

- [ ] Backup/restore drill passed.
- [ ] `ALLOW_DEMO_RESET=false`.
- [ ] Internal ports plan reviewed.
- [ ] Proxy route plan reviewed.
- [ ] Firewall rules staged.
- [ ] Rollback documented.
- [ ] Runtime verifier passes.
- [ ] Vendor link plan uses HTTPS.

No-go if:

- DB, Redis, or MinIO are publicly reachable.
- SSH lockout risk is unresolved.
- No provider console access exists.
- Backup/restore is not verified.
- App depends on direct public `8000` or `3000` access without a transition plan.

## L. What This PR Does Not Do

- No live firewall changes.
- No UFW enable/disable.
- No Domain + HTTPS connection.
- No `.env.staging` changes.
- No real customer data onboarding.
