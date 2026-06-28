# Deploy runbook — clausecraft (single host)

This is the full step-by-step for taking the dev stack to a public,
TLS-terminated production deploy on a single Linux host. The artifacts
shipped in this repo are target-agnostic (Hetzner, Fly.io, bare metal,
your laptop running as a sandbox) — the runbook is the same for each.
The choice of **which host** is yours; this document does not pick for
you.

## Overview

The prod deploy layers two new files on top of the dev stack:

| File | What it does |
|---|---|
| `docker-compose.prod.yml` | extends `docker-compose.yml` (no duplication) — adds the `caddy` service, strips the dev-stack port publishes, sets the prod `NEXTAUTH_URL` |
| `Caddyfile` | the Caddy config — 3 HTTPS routes, `local_certs` for self-signed fallback, `envsubst` rendering at container start |
| `scripts/caddy-entrypoint.sh` | the entrypoint that renders the Caddyfile template with `envsubst`, runs `caddy validate`, then `caddy run` |
| `.env.prod.example` | the prod env template (committed; no real secrets) |
| `scripts/render-env-prod.sh` | the local-only secret generator — fills `.env.prod` with `openssl rand -hex 32` values; refuses to overwrite a file with real-looking values without `--force` |

The dev stack (`docker-compose.yml`) and the prod overlay
(`docker-compose.prod.yml`) merge with `docker compose -f a -f b`.
The dev stack still publishes `18000`/`15173`/`13000` to the host for
local development; the prod overlay **overrides** those publishes to
empty lists so the dev ports are not exposed publicly. Caddy, on the
host network, talks to the services via their internal docker
network aliases and serves HTTPS on `:443`.

## The seven steps

### 1. Provision a host

Pick any single Linux host with Docker 24+ and reachable ports 80/443.
Common choices:

- **Hetzner** — €4/mo CX22, IPv4 + IPv6, ports 80/443 unmetered. Set
  the A/AAAA records for `app.${DOMAIN}`, `api.${DOMAIN}`,
  `langfuse.${DOMAIN}` to the host's IP.
- **Fly.io** — single-VM `fly machines run`, or a 1× shared-cpu-1x
  app. Same port requirements.
- **Bare metal / local VM** — any Debian/Ubuntu host with Docker
  installed.

The spec is single-host, so a CX22 / shared-cpu-1x is plenty. Multi-replica
and load balancer are explicitly out of scope for v1.

```bash
# Hetzner example (run on your local terminal, NOT on the host):
hcloud server create \
    --name clausecraft-prod \
    --type cx22 \
    --image ubuntu-24.04 \
    --ssh-key ody@home \
    --location nbg1
```

### 2. Clone the repo

```bash
ssh ody@<host>
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER  # log out / in
git clone https://github.com/anuragparida/clausecraft.git
cd clausecraft
```

### 3. Generate the prod env

```bash
cp .env.prod.example .env.prod
./scripts/render-env-prod.sh
# Edit .env.prod to set the operator-supplied values:
#   DOMAIN=example.com
#   ACME_EMAIL=ops@example.com
#   ACME_CA=https://acme-v02.api.letsencrypt.org/directory
#   LLM_API_KEY=sk-real-key-if-you-have-one
#   EMBEDDING_API_KEY=sk-or-real-key-if-you-have-one
```

`render-env-prod.sh` fills the 5 secret vars (`POSTGRES_PASSWORD`,
`BACKEND_API_KEY`, `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`,
`LANGFUSE_ENCRYPTION_KEY`) with 64-hex-char random values. It refuses
to overwrite a `.env.prod` that already has real-looking values unless
you pass `--force`. Re-runnable.

### 4. Bring the stack up

```bash
docker compose \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    --env-file .env.prod \
    up -d --build
```

This brings up the dev compose's 4 services (`postgres`, `backend`,
`frontend`, `langfuse-web`) plus the prod overlay's `caddy` service.
Caddy waits for `backend` to be healthy before starting (it has a
`depends_on: service_healthy` block); the dev compose's
`backend` healthcheck on `http://localhost:8000/healthz` is the gate.

The dev ports (18000/15173/13000/13001) are NOT published to the host
in this overlay. The only externally reachable ports are 80/443 (Caddy
on the host network).

### 5. Point DNS

For each of:

- `app.${DOMAIN}`
- `api.${DOMAIN}`
- `langfuse.${DOMAIN}`

create an A record (and AAAA if you want IPv6) pointing at the host's
public IP. DNS propagation takes a few seconds to a few minutes
depending on the TTL.

```bash
# Verify
dig +short app.${DOMAIN}
dig +short api.${DOMAIN}
dig +short langfuse.${DOMAIN}
```

### 6. Caddy auto-issues certs

On the first request to each hostname, Caddy will:

1. Receive the HTTPS connection.
2. Attempt the Let's Encrypt HTTP-01 challenge on `:80`. The DNS A
   record must point at the host, and port 80 must be reachable.
3. Once the challenge succeeds, Caddy stores the issued cert in its
   `/data` volume (`caddy_data` named volume) and renews it
   automatically ~30 days before expiry.

Cert issuance is per-hostname, so the first request to each of
`app.${DOMAIN}`, `api.${DOMAIN}`, `langfuse.${DOMAIN}` triggers its
own issuance. Subsequent requests hit the cached cert.

```bash
# Watch Caddy's logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f caddy
# You should see "obtained certificate" lines for each hostname.
```

### 7. Verify

```bash
curl -sI https://app.${DOMAIN} | head -1     # HTTP/2 200
curl -sI https://api.${DOMAIN}/healthz      # HTTP/2 200
curl -sI https://langfuse.${DOMAIN}         # HTTP/2 200 (the Langfuse login page)
```

The first request per hostname may take ~5–10s as Caddy waits for
Let's Encrypt to issue the cert. Subsequent requests are fast.

If `curl` returns `-k` warnings or a cert error, your DNS isn't
propagated yet — wait a minute and try again.

## Local smoke test (no public DNS)

For a smoke test that doesn't need a real public domain, run Caddy
locally with `DOMAIN=localhost` and the `local_certs` directive in
the Caddyfile will issue self-signed certs when ACME fails:

```bash
# From the repo root:
cp .env.prod.example .env.prod
sed -i 's/^DOMAIN=.*/DOMAIN=localhost/' .env.prod
./scripts/render-env-prod.sh --force
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    --env-file .env.prod up -d --build
curl -kI https://app.localhost | head -1
# HTTP/2 200
```

Caddy's `local_certs` directive in each site block auto-falls-back to
self-signed certs when ACME fails (e.g. `localhost` is not a public
name). The certs are not trusted by your browser by default; use
`curl -k` to ignore the warning, or click through the "not secure"
dialog in the browser. The smoke test exists to verify the wiring —
Caddy, the routes, the prod stack behind it — without burning
Let's Encrypt rate-limit budget.

## Operations

### Tail logs

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f caddy
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
```

### Update the deploy

```bash
# Pull the new code
git pull
# Rebuild the images and re-up
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    --env-file .env.prod up -d --build
```

Caddy hot-reloads its config (it watches the file descriptor), so
changes to the Caddyfile don't need a container restart. Backend and
frontend image changes do.

### Rotate secrets

```bash
# Re-render and force-overwrite
./scripts/render-env-prod.sh --force
# Restart the services that read the new env
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    --env-file .env.prod up -d
```

### Backup Postgres

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec postgres pg_dump -U clausecraft clausecraft > backup-$(date +%F).sql
```

## What's NOT in this runbook

- **Hetzner vs Fly.io choice.** Per the spec, this is Anurag's call.
  The artifacts work on both.
- **A "scale" plan.** Replicas, load balancer, multi-region. Out of
  scope for v1 (single host per the spec).
- **Managed Langfuse.** The v2 self-hosted image is fine for v1; if
  you outgrow it, swap the `langfuse-web` service in the dev
  compose for the managed Langfuse SaaS endpoint and update
  `LANGFUSE_HOST` in `.env.prod`.
- **Backup retention / disaster recovery.** Backup the Postgres
  volume; the rest is in git.
- **TLS beyond Let's Encrypt.** Caddy supports zero-config other
  CAs (ZeroSSL, internal CA) via the `acme_ca` and `tls` blocks in
  the Caddyfile. See the [Caddy docs](https://caddyserver.com/docs/).

## Sharp edges

- **Don't use the dev `.env` as the prod env.** It has the
  `POSTGRES_PASSWORD=clausecraft` default; you do not want that in
  prod.
- **Don't commit `.env.prod`.** It is in `.gitignore`. The render
  script warns on every run.
- **DNS TTL.** Set it low (60s) on the first deploy so a wrong IP
  recovers fast. Bump it to 3600s+ once the certs are issued and
  the deploy is stable.
- **Caddy admin endpoint.** The Caddyfile binds `admin` to
  `localhost:2019` only, but since the container uses the host
  network, that means the admin API is reachable on the host's
  loopback. Don't expose `:2019` to the public internet.
- **Postgres is not published to the host.** The overlay strips
  the dev compose's `ports: ["${POSTGRES_HOST_PORT:-15432}:5432"]`
  by overriding with `ports: []`. The backend and langfuse-web
  reach it via the docker network alias `postgres:5432`.
  Backups run via `docker compose exec` (see above), not via a
  published port.
