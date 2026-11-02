#!/bin/sh
# Applies database migrations (done by the app at startup), optionally loads the demo data, then serves on port 8000.
set -e
if [ "$SPENDOS_SEED_DEMO" = "true" ]; then
  if [ "$SPENDOS_ENV" != "demo" ]; then
    echo "SPENDOS_SEED_DEMO=true requires SPENDOS_ENV=demo (demo data is never loaded in production)"; exit 1
  fi
  python -m app.seed   # idempotent: does nothing when the demo data already exists
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"
