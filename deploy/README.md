# Deploying

One small Lightsail server runs everything with Docker Compose (no Kubernetes):

```
Lightsail server (Ubuntu 24.04, 2 GB, ~$12/mo)
├── /srv/caddy             shared Caddy: ports 80/443, automatic HTTPS, routes by hostname
└── /srv/fake-sportsbook   db + backend + frontend (nginx); no published ports
```

Caddy sends `sportsbook.martinteran.me/api/*` to the backend and everything else to the
frontend, so the app and API share one origin (no CORS in production).

## One-time setup

1. **Buy the domain**: Route 53 → Registered domains → `martinteran.me`. This also creates
   the hosted zone.
2. **Create the server**: Lightsail → Create instance → Linux/Unix → OS only →
   **Ubuntu 24.04 LTS** → the **$12 (2 GB)** plan. Under SSH key, upload your own public key
   (`~/.ssh/id_ed25519.pub`) or download Lightsail's default key.
3. **Static IP**: Lightsail → Networking → Create static IP → attach it to the server.
   It's free while attached.
4. **Firewall**: on the instance's Networking tab, add **HTTPS (TCP 443)**. SSH and HTTP
   are open by default.
5. **Snapshots**: on the instance's Snapshots tab, turn on **automatic snapshots** (daily
   backups, a dollar or two a month).
6. **DNS**: Route 53 → Hosted zones → `martinteran.me` → Create record:
   `sportsbook`, type **A**, value = the static IP.
   Check it with `dig +short sportsbook.martinteran.me`.
7. **Prepare the server** (from the repo root on your Mac):
   ```bash
   ssh ubuntu@<static-ip> 'bash -s' < deploy/setup-server.sh
   ```
8. **Production secrets** live only on the server:
   ```bash
   ssh ubuntu@<static-ip>
   mkdir -p /srv/fake-sportsbook/deploy
   nano /srv/fake-sportsbook/deploy/.env.prod     # template: deploy/.env.prod.example
   ```
   Generate `POSTGRES_PASSWORD` and `JWT_SECRET_KEY` with `openssl rand -hex 32`.

## Every deploy

**Automatic:** push to `main`. GitHub Actions (`.github/workflows/ci.yml`) runs the backend
and frontend checks, then runs `deploy/deploy.sh` against the server. Pull requests run
checks only. You can also trigger it by hand from the Actions tab ("Run workflow").

**Manual** (same script, from your Mac):

```bash
DEPLOY_HOST=ubuntu@<static-ip> deploy/deploy.sh
```

Either way, the script rsyncs the repo to the server, rebuilds the containers (migrations run on backend
start), and reloads Caddy. The first deploy also gets the HTTPS certificate, which only
works once the DNS record from step 6 resolves.

## GitHub Actions setup (one time, after the server exists)

Use a dedicated SSH key for CI rather than your personal key, so you can revoke it on
its own:

```bash
ssh-keygen -t ed25519 -N "" -C github-actions-deploy -f ~/.ssh/sportsbook_deploy
ssh-copy-id -i ~/.ssh/sportsbook_deploy.pub ubuntu@<static-ip>

gh api -X PUT "repos/{owner}/{repo}/environments/production" >/dev/null   # create the environment
gh secret set DEPLOY_HOST --env production --body "ubuntu@<static-ip>"
gh secret set DEPLOY_SSH_KEY --env production < ~/.ssh/sportsbook_deploy
ssh-keyscan -t ed25519 <static-ip> | gh secret set DEPLOY_KNOWN_HOSTS --env production
```

The secrets are scoped to a `production` environment. In the repo's Settings →
Environments → production, you can restrict deploys to the `main` branch.

GitHub's runners don't have fixed IP addresses, so SSH (port 22) has to stay open to the
internet in the Lightsail firewall. That's fine because Lightsail's Ubuntu image only
allows key login (no passwords).

## Handy commands (on the server)

```bash
cd /srv/fake-sportsbook
alias dc='docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod'
dc ps
dc logs -f backend
dc exec backend python -m app.services.odds        # force an odds refresh
dc exec db psql -U sportsbook fake_sportsbook       # database shell
```

## Adding volunteer-scheduler later

1. Give its prod compose file the same shape: join the external `web` network with aliases
   `volunteer-backend` / `volunteer-frontend`, and publish no ports.
2. Uncomment the `volunteer.martinteran.me` block in `deploy/caddy/Caddyfile`.
3. Add a `volunteer` A record pointing to the same static IP.
