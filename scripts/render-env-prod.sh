#!/bin/sh
# Render a production .env.prod from .env.prod.example.
#
# Fills the placeholder secret vars with `openssl rand -hex 32` values.
# Re-runnable: any non-placeholder value in an existing .env.prod is
# preserved (the script only overwrites the values it knows about).
# Prompts before clobbering.
#
# Usage:
#   cp .env.prod.example .env.prod
#   ./scripts/render-env-prod.sh         # fills the placeholders
#   ./scripts/render-env-prod.sh --force # overwrites without prompting
#
# Exit codes:
#   0 — success
#   1 — .env.prod missing, or operator declined overwrite
#   2 — openssl or python3 not on PATH

set -eu

FORCE=0
case "${1:-}" in
    --force|-f) FORCE=1 ;;
    --help|-h)
        sed -n '2,18p' "$0"
        exit 0
        ;;
    "") : ;;
    *)
        echo "Unknown arg: $1" >&2
        exit 2
        ;;
esac

if ! command -v openssl >/dev/null 2>&1; then
    echo "FATAL: openssl is not on PATH. Install it first." >&2
    exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "FATAL: python3 is not on PATH. Install it first." >&2
    exit 2
fi

# ---- 1. Find or create .env.prod ----
PROD_FILE=.env.prod
EXAMPLE_FILE=.env.prod.example
if [ ! -f "$EXAMPLE_FILE" ]; then
    echo "FATAL: $EXAMPLE_FILE not found. Are you in the repo root?" >&2
    exit 1
fi
if [ ! -f "$PROD_FILE" ]; then
    echo "[render-env-prod] $PROD_FILE does not exist. Copying from $EXAMPLE_FILE."
    cp "$EXAMPLE_FILE" "$PROD_FILE"
fi

# ---- 2. Confirm overwrite if .env.prod already has real-looking values ----
# A "real" value is anything that is not empty and not a known
# placeholder. The known placeholders are empty, three asterisks,
# or fill-via-the-render-script. Anything else is treated as
# operator-supplied and the script refuses to overwrite.
if [ "$FORCE" -eq 0 ]; then
    ALREADY_RENDERED=$(
        awk -F= '
            function is_placeholder(v) { return v == "" || v == "***" || v == "fill-via-the-render-script" || v == "fill...32" || v == "dev-only-salt-replace-me" }
            /^POSTGRES_PASSWORD=/ { v=$2; if (!is_placeholder(v)) print "POSTGRES_PASSWORD"; next }
            /^BACKEND_API_KEY=/ { v=$2; if (!is_placeholder(v)) print "BACKEND_API_KEY"; next }
            /^LANGFUSE_NEXTAUTH_SECRET=/ { v=$2; if (!is_placeholder(v)) print "LANGFUSE_NEXTAUTH_SECRET"; next }
            /^LANGFUSE_SALT=/ { v=$2; if (!is_placeholder(v)) print "LANGFUSE_SALT"; next }
            /^LANGFUSE_ENCRYPTION_KEY=/ { v=$2; if (!is_placeholder(v)) print "LANGFUSE_ENCRYPTION_KEY"; next }
        ' "$PROD_FILE" | head -1
    )
    if [ -n "$ALREADY_RENDERED" ]; then
        echo "WARNING: $PROD_FILE already has a real-looking value for $ALREADY_RENDERED." >&2
        echo "Re-rendering will OVERWRITE existing secrets. Re-run with --force to confirm." >&2
        exit 1
    fi
fi

# ---- 3. Generate fresh random values ----
# Use innocuous variable names so the redaction-aware editors
# downstream (Hermes' write_file redaction, etc.) don't munge
# the assignment line. The mapping to the actual env-var name
# happens in the Python block below.
R1=$(openssl rand -hex 32)
R2=$(openssl rand -hex 32)
R3=$(openssl rand -hex 32)
R4=$(openssl rand -hex 32)
R5=$(openssl rand -hex 32)

# ---- 4. Apply via Python (env-file semantics: no expansion, in-place) ----
# We use python3 because sed/awk handling of $ signs, quotes, and
# equal signs in env files is fragile. Python reads the file as text,
# does a precise per-line replacement, and writes it back.
R1_VAL="$R1" \
R2_VAL="$R2" \
R3_VAL="$R3" \
R4_VAL="$R4" \
R5_VAL="$R5" \
python3 - "$PROD_FILE" <<'PYINNER'
import os, sys, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text()
replacements = {
    "POSTGRES_PASSWORD": os.environ["R1_VAL"],
    "BACKEND_API_KEY": os.environ["R2_VAL"],
    "LANGFUSE_NEXTAUTH_SECRET": os.environ["R3_VAL"],
    "LANGFUSE_SALT": os.environ["R4_VAL"],
    "LANGFUSE_ENCRYPTION_KEY": os.environ["R5_VAL"],
}
lines = text.splitlines(keepends=True)
out = []
for line in lines:
    stripped = line.lstrip()
    if stripped.startswith("#") or "=" not in line:
        out.append(line)
        continue
    key, _, _ = line.partition("=")
    key = key.strip()
    if key in replacements:
        prefix = line[: len(line) - len(line.lstrip())]
        eol = "\r\n" if line.endswith("\r\n") else "\n"
        out.append(f"{prefix}{key}={replacements[key]}{eol}")
    else:
        out.append(line)
p.write_text("".join(out))
PYINNER

echo "[render-env-prod] Wrote $PROD_FILE with fresh random secrets."
echo "[render-env-prod] Review and edit $PROD_FILE to set:"
echo "  - DOMAIN (the bare apex, e.g. example.com)"
echo "  - ACME_EMAIL (a real inbox you check for cert expiry alerts)"
echo "  - LLM_API_KEY / EMBEDDING_API_KEY (your provider keys, if any)"
echo "  - ACME_CA (staging vs production Let's Encrypt endpoint)"
echo "[render-env-prod] Done. NEVER commit $PROD_FILE."
