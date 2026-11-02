#!/bin/bash
cd "$(dirname "$0")"
for n in 01-personal 02-business 03-pillars 04-mobile; do
  bash ../backend/reset_rec.sh >/dev/null
  echo "=== recording $n"
  SPENDOS_URL=http://localhost:8001 node record-$n.mjs 2>&1 | tail -6
done
echo ALL_DONE
