@echo off
REM Starts PostgreSQL (Docker), prepares the demo database if empty, and serves Aadi SpendOS on http://localhost:8000
cd /d "%~dp0"
docker compose up -d
docker exec spendos-postgres psql -U spendos -d postgres -c "CREATE DATABASE spendos_demo" 2>nul
cd backend
set SPENDOS_ENV=demo
set PY=C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe
if not exist ..\frontend\dist ( cd ..\frontend && call npm install && call npm run build && cd ..\backend )
"%PY%" -m app.seed
start "SpendOS API + web" "%PY%" -m uvicorn app.main:app --port 8000
echo Open http://localhost:8000  (demo logins: docs\demo\DEMO_ACCESS.md)
