# Aadi SpendOS

Configurable expense and spend management platform (PRD v1.1): one shared financial engine, a Personal edition and a Business edition, three product pillars (Software Product, Marketing & Sales spend, AI Solutions).

| Layer | Technology |
|---|---|
| Web | React 19, TypeScript, Vite, Material UI (responsive) |
| API | Python FastAPI, SQLAlchemy 2, Alembic migrations |
| Database | **PostgreSQL 16** (Docker, `docker-compose.yml`) |
| Money | Integer minor units (paise); no floating point is stored or summed |

## Run it

```
docker compose up -d          # PostgreSQL on localhost:15433
start_demo.bat                # migrates, seeds if empty, serves http://localhost:8000
```

Or by hand: `cd backend && python -m app.seed --reset && python -m uvicorn app.main:app --port 8000` (the built web app in `frontend/dist` is served by the API). For frontend work: `cd frontend && npm install && npm run dev` (port 5173, proxies `/api`).

Demo logins and what to try: [docs/demo/DEMO_ACCESS.md](docs/demo/DEMO_ACCESS.md). Sprint videos and the register: [docs/SPENDOS_SPRINT_VIDEO_REFERENCE.xlsx](docs/SPENDOS_SPRINT_VIDEO_REFERENCE.xlsx). Requirements status: [docs/SPRINT_REPORT.md](docs/SPRINT_REPORT.md).

## Tests

```
cd backend
python -m pytest tests -q            # runs against PostgreSQL database spendos_test
cd ../frontend && npm run build      # type-check + production build
cd ../videos && node check-screens.mjs   # browser sign-in + every page for all 17 demo personas
```

## Layout

* `backend/app` - `models.py` (data model), `core.py` (auth, permissions, entitlements, money), `ledger.py` (balances, allocations, budgets, approvals), `ai.py` (assistive engine), `routers/`, `seed.py` (deterministic demo data), `alembic/` (migrations).
* `frontend/src` - pages for dashboard, transactions, approvals, accounts, categories, budgets, family/goals, AI assistant, reports, growth spend, settings, platform admin.
* `videos/` - recorders reusing the DMS project's Playwright + narration + FFmpeg pipeline; output MP4/SRT/VTT/CSV.

## Not in this release (see the sprint report)

Native mobile app, Redis/background workers, S3 object storage, a real OCR/LLM provider (the AI layer is a deterministic rules engine, labelled as such), live ad-platform integrations, Hindi/Marathi translations.
