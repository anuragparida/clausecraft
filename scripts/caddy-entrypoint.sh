#!/bin/sh
# Caddy entrypoint: render the Caddyfile template, then exec caddy.
#
# The Caddyfile uses `@VAR@` sentinels for env-var substitution.
# We use sed (not envsubst) to do the replacement because Caddy's
# own runtime placeholders (`{$VAR}`) collide with shell
# expansion. After sed renders the file, we run `caddy validate`
# to fail fast on syntax errors, then `caddy run`.
#
# Local smoke test: set DOMAIN=localhost. Caddy's `local_certs`
# directive in the Caddyfile issues a self-signed cert when ACME
# fails. The smoke test ignores the cert with `curl -k`.

set -eu

if [ -z "${DOMAIN:-}" ]; then
    echo "FATAL: DOMAIN env var is not set. Add it to .env.prod." >&2
    exit 1
fi

: "${ACME_EMAIL:=ops@${DOMAIN}}"
: "${ACME_CA:=https://acme-v02.api.letsencrypt.org/directory}"

echo "[caddy-entrypoint] Starting Caddy for domain: ${DOMAIN}"
echo "[caddy-entrypoint] ACME email: ${ACME_EMAIL}"
echo "[caddy-entrypoint] ACME CA: ${ACME_CA}"

# Render the template. We use sed with a unique delimiter (|) so
# colons and dots in the values do not need escaping. The
# sentinels (@DOMAIN@, @ACME_EMAIL@, @ACME_CA@) are unique to
# this template, so the replacement is safe.
sed -e "s|@DOMAIN@|${DOMAIN}|g" \
    -e "s|@ACME_EMAIL@|${ACME_EMAIL}|g" \
    -e "s|@ACME_CA@|${ACME_CA}|g" \
    /etc/caddy/Caddyfile.template \
    > /etc/caddy/Caddyfile

# Validate before exec so we don't crash-loop Caddy in a way
# that loses the healthcheck. Caddy prints JSON to stderr on
# success. --adapter '' skips adapter conversion (raw Caddyfile).
caddy validate --config /etc/caddy/Caddyfile --adapter ''

echo "[caddy-entrypoint] Caddyfile valid; starting caddy"
# `caddy run` reads the Caddyfile from --config and starts
# listening. It will:
#   - On :80, answer ACME HTTP-01 challenges and redirect to HTTPS.
#   - On :443, serve HTTPS with Let's Encrypt certs (or self-signed
#     via `local_certs` if the ACME challenge fails).
# Caddy stays in the foreground; container restart policy is
# handled by docker compose (restart: unless-stopped).
exec caddy run --config /etc/caddy/Caddyfile --environ
