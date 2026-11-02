#!/bin/bash
# Rebuild the RECORDING database (PostgreSQL spendos_rec) and restart the recording server on port 8001. Never touches the demo DB.
cd "$(dirname "$0")"
PY=/c/Users/lenovo/AppData/Local/Programs/Python/Python312/python.exe
export SPENDOS_ENV=demo
export SPENDOS_DB=postgresql+psycopg://spendos:spendos_dev@localhost:15433/spendos_rec
pid=$(netstat -ano | grep ":8001 " | grep LISTENING | awk '{print $5}' | head -1); [ -n "$pid" ] && taskkill //PID $pid //F >/dev/null 2>&1
docker exec spendos-postgres psql -U spendos -d postgres -q -c "DROP DATABASE IF EXISTS spendos_rec WITH (FORCE)" -c "CREATE DATABASE spendos_rec"
rm -rf data/files_rec
$PY -m app.seed --reset
(SPENDOS_STORAGE=data/files_rec nohup $PY -m uvicorn app.main:app --port 8001 > data/server_rec.log 2>&1 &)
sleep 4; curl -s localhost:8001/api/health; echo
