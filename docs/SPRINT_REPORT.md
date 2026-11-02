# SpendOS - Sprint S1 report and requirements traceability

Scope: PRD v1.1 MVP built in one pass (milestones M1-M8) on explicit approval from the Product Owner to proceed without per-sprint sign-off. The repository had no existing SpendOS code (only the two PRD documents and the video register template), so there was nothing to preserve or conflict with.

Status key: **Done** = implemented, exercised by an automated test and/or the recorded journeys. **Partial** = implemented with a stated gap. **Not done** = not in this release.

## Verification evidence (executed)

| Check | Command | Result |
|---|---|---|
| Backend tests on PostgreSQL 16 | `cd backend; python -m pytest tests -q` | 41 passed (30 from S1, 11 new in S2) |
| Migrations | `alembic upgrade head`, `downgrade base`, `upgrade head` on an empty PostgreSQL database | succeeded; head = 0002 (0001 initial schema, 0002 lockout + member allocations) |
| Frontend type-check and production build | `cd frontend; npm run build` | succeeded |
| Browser sign-in and every menu page for all 17 personas | `node videos/check-screens.mjs` | see final run in the handoff message |
| Narrated journeys on the real app | `videos/record-0*.mjs` | four videos recorded |

## Requirements traceability

| Req | Status | Where | Notes |
|---|---|---|---|
| FR-01 Auth and onboarding | Done | `routers/auth.py`, `pages/Auth.tsx` | register, login/logout (revocable sessions), reset (demo shows the token because there is no mail server), template choice, invite members, several organizations per user (switch menu). |
| FR-02 Dashboards | Done | `routers/insight.py:dashboard`, `pages/Dashboard.tsx` | widgets are listed in each tenant's own configuration. |
| FR-03 Transactions | Done | `routers/txn.py`, `ledger.py` | five types, filters, pagination, CSV export (formula-safe), CSV import with preview, duplicate detection, history via audit. Refund cap and linkage, transfers excluded, card purchases are expenses. Attachments: JPG/PNG/PDF stored on local disk (not S3). |
| FR-04 Categories | Done | `routers/config.py`, `templates.py` | per-tenant copies; icon is stored but not editable in the UI. |
| FR-05 Accounts | Done | `ledger.account_balances` | calculated balances; no bank credentials anywhere. |
| FR-06 Budgets | Done | `ledger.budget_status`, `evaluate_budget_alerts` | household, category, department, project, campaign; thresholds configurable via API, deduplicated notifications. Annual budgets: monthly only. Savings targets are goals, not budget lines. |
| FR-07 Family and organization | Done in S2 except branches/cost-centre screens | `pages/Setup.tsx` | departments, projects, cost centres (table and seed only, no screen), members, project assignments. S2 added member allocation of shared expenses (must reconcile to the amount) and the Family contributions report. Cost centres exist in data only (no screen); branches are not separate from departments. |
| FR-08 Approvals | Done | `ledger.py`, `routers/txn.py` | amount-based, department/project-specific policies, multi-level, reasons, history, pending list, notifications. |
| FR-09 AI capture | Partial | `ai.py`, `pages/AI.tsx` | voice (browser speech where available, or typed), receipt upload, register lines, confidence, duplicates, mandatory review. **No OCR/LLM provider is connected**: receipts are read from embedded text and filename hints; handwriting photos are not recognised. Labelled "simulated" in the UI. |
| FR-10 Insights | Done (rules) | `ai.insights/answer` | facts vs estimates labelled; permission-scoped. Rule-based, not a language model. |
| FR-11 Reports | Done | `routers/insight.py:report` | personal and business reports, CSV and PDF. |
| FR-12 Notifications | Done (in-app) | `routers/auth.py`, `routers/extras.py` | budget, approval, rejection, reimbursement, recurring reminders (3 days ahead) and monthly summary, all deduplicated and preference-controlled. No email/push channel. |
| FR-13/14 Catalogue and entitlements | Done | `main.py` (catalogue), `core.effective_entitlements`, `routers/platform.py` | enabled/disabled/expired/override/dependency; consistent `ENTITLEMENT_DENIED`. |
| FR-15/16 Growth dimensions and spend | Done | `routers/config.py`, `insight.growth_rows` | campaign and channel as dimensions; no ROI/CAC without data. |
| FR-17 Growth import | Done | `insight.growth_import` | CSV, all-or-nothing, source/period/currency/attribution recorded. |
| FR-18 AI provenance | Done | `AiExtraction`, `Transaction.ai` | |
| FR-19 AI permission scope | Done | `ai.py` uses `visible_filter` | tests cover leakage. |
| FR-20 Anomaly review | Done | `ai.insights`, `InsightReview` | advisory wording, acknowledge/dismiss audited. |
| FR-21 Estimate labelling | Done | `ai.insights` | |
| FR-22 Pillar reporting | Partial | `/usage`, `/platform/usage` | counts per tenant and aggregate entitlement counts; no time-series. |
| NFR security | Partial | | backend RBAC and tenant filter on every query; bcrypt; JWT sessions with revocation. S2 added login lockout (5 failures, 15 minutes), personal data export and account deletion. **Not done**: encryption-at-rest configuration, secure object storage. |
| NFR performance | Measured once | `backend/perf_check.py` | 25,045 transactions in one tenant, PostgreSQL, in-process: dashboard p50 1.3 s (was 8.2 s before the S2 query rewrite), budgets 0.16 s, transaction list 0.02 s, project report 0.10 s, category report 0.27 s. Meets the 2 s target on this machine for this data size; not a load test (single user, no network). |
| NFR accessibility | Automated scan only | `videos/check-a11y.mjs` | axe-core WCAG 2.0/2.1/2.2 A and AA rules over 35 page views (4 personas): first run found 6 rule violations (contrast, names, list structure); fixed; re-run found none. 20 items are flagged by axe as needing manual review, and no keyboard/screen-reader audit has been done. |
| Redis / workers / S3 | Not done | | AI runs inline; files on local disk. |
| React Native app | Not done | | the responsive web app is shown on a phone viewport instead. |
| Hindi/Marathi | Partial (draft) | `frontend/src/i18n.ts` | navigation and page titles only; draft wording needs native-speaker review. Forms, messages and reports are English. |
| Seed data 7.1/7.2 | Done | `seed.py`, tests | deterministic, stable ids, idempotent, `--reset`; Aadi totals asserted equal to the PRD summary (income 850000, expenses 500000, surplus 350000, category groups). Personal: 5 accounts, 20 categories and subcategories, 60 transactions (52 in October), 3 goals. |

## Conflicts and decisions

* PRD says Redis workers and S3; neither was built because nothing in the demo needs them yet. Recorded as gaps rather than faked.
* "Reimbursement" transaction type is interpreted as money received back against an expense (like a refund, e.g. insurer); employee claims are expenses flagged reimbursable that finish as "paid". Change if the Product Owner intended otherwise.
* Unpaid claims are not counted in actuals; paid and posted ones are. This keeps the Aadi summary exactly at 5,00,000.

## Known issues / limits

* Recording used browser date pinning (October / November 2026) so the demo period lines up; the app itself uses the real date.
* The demo reset token for forgotten passwords is returned by the API in demo mode only.
* Voice capture needs a browser with the Web Speech API; typing always works.
* Passwords for demo users are one shared disposable value documented in `docs/demo/DEMO_ACCESS.md`.

## Sprint S2 (gap closure) - what changed

* Sign-in lockout, recurring payments with reminders and monthly summary, member allocation of shared expenses and contributions report, personal data export and account deletion (demo accounts protected), Hindi/Marathi navigation, dashboard and budget query rewrite, accessibility fixes, migration 0002. Video: `videos/05-spendos-sprint-2-gap-closure.mp4`.
* Tests added: `backend/tests/test_sprint2.py` (11). Full run: 41 passed.

## Still open (needs a decision, credentials or a separate project)

* Native React Native/Expo app (DEC-07).
* A real OCR and language-model provider, with cost and retention rules (DEC-04, DEC-05).
* Redis and background workers, S3-compatible storage.
* Live ad-platform/CRM integrations (DEC-03).
* Native-speaker review of Hindi/Marathi and externalising all remaining strings (DEC-08).
* A manual accessibility audit and a multi-user load test.
* Email delivery for notifications and password reset.
