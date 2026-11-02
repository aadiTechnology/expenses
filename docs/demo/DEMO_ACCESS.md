# Aadi SpendOS - demo access (non-production, synthetic data only)

Everything in this environment is **illustrative demo data**. No real people, customers, bank details or production credentials exist here. The Aadi Technology figures are demonstration numbers, not Aadi Technology's real accounts.

Demo password for every account below: `SpendOS@Demo26`

This password is disposable and works only on a demo environment (`SPENDOS_ENV=demo`). Rotate it before sharing the environment beyond the review team: change `DEMO_PASSWORD` in `backend/app/seed.py` and run `python -m app.seed --reset`.

## Open the application

| What | Where |
|---|---|
| Web app (demo) | http://localhost:8000 |
| API documentation (Swagger) | http://localhost:8000/docs |

Start it with `ExpenseTracking\start_demo.bat` (creates the demo database if it is missing, then serves the app on port 8000). Sign-in page tip: click **Show demo accounts**, then **Use** next to a person - it fills in the email and the (masked) password for you.

## Personal edition - tenant "Rahul Sharma - Household (SAMPLE DATA)", October 2026

| Persona | Role | Email | What to try |
|---|---|---|---|
| Rahul Sharma | Owner (full access) | rahul.sharma@spendos.demo.test | Dashboard, add expense, transfers, budgets, goals, AI capture and insights, reports |
| Priya Sharma | Family Member | priya.sharma@spendos.demo.test | Her own and shared transactions only; no accounts or settings |
| Aarav Sharma | Family Member | aarav.sharma@spendos.demo.test | Own pocket-money expenses and shared items |
| Sunita Sharma | Family Viewer (read-only) | sunita.sharma@spendos.demo.test | Sees shared items only; cannot add anything |

## Business edition - tenant "Aadi Technology (ILLUSTRATIVE DEMO)", October 2026 (plan: Business Growth)

| Persona | Role | Email | What to try |
|---|---|---|---|
| Anita Deshmukh | Organization Admin | anita.deshmukh@spendos.demo.test | Create project budgets, departments, projects, members, approval policies, audit log, project reports |
| Sanjay Kulkarni | Finance Manager | sanjay.kulkarni@spendos.demo.test | Verify and pay reimbursements, budget vs actual, Growth Spend, growth data import |
| Vikram Joshi | Department Manager (Software Development) | vikram.joshi@spendos.demo.test | Department expenditure - sees only his own department |
| Neha Kapoor | Department Manager (Digital Marketing) | neha.kapoor@spendos.demo.test | Marketing department view |
| Rohit Patil | Project Manager (Multitenant CRM, AI Product Factory) | rohit.patil@spendos.demo.test | Approves claims for his projects only |
| Sneha Iyer | Project Manager (RITeSchool, Preschool ERP, Internship Program) | sneha.iyer@spendos.demo.test | Waiting approvals for her projects |
| Arjun Mehta | Employee (Software Dev, RITeSchool) | arjun.mehta@spendos.demo.test | Create a travel expense; sees only his own |
| Meera Nair | Employee (Software Dev, Multitenant CRM) | meera.nair@spendos.demo.test | Has a claim waiting for finance |
| Kiran Shah | Employee (Product Dev, AI Product Factory) | kiran.shah@spendos.demo.test | Has a claim verified and waiting for payment |
| Divya Rao | Employee (Digital Marketing, Internship Program) | divya.rao@spendos.demo.test | Has a claim waiting for its project manager |
| Sameer Patil | Employee (Training, Internship Program) | sameer.patil@spendos.demo.test | Has a rejected claim with a reason |
| Ravi Menon | Auditor (read-only) | ravi.menon@spendos.demo.test | Reads everything, cannot change anything |

## Platform administration (no tenant)

| Persona | Role | Email | What to try |
|---|---|---|---|
| Platform Admin | Platform administrator | platform.admin@spendos.demo.test | Module catalogue and pillar classification, tenant entitlements (switch modules on and off), aggregated adoption |

## Tenant scope you can verify

* Personal accounts cannot open Aadi Technology records (the server answers "not found" / "no access").
* Aadi employees see only their own expenses; project managers and department managers see only their projects/department; finance, admin and the auditor see the organization.
* The Personal tenant is not entitled to Growth Spend. Calling `/api/v1/growth/spend` with a personal session returns `403 ENTITLEMENT_DENIED`.

## Reset the demo

```
cd ExpenseTracking\backend
python -m app.seed --reset
```

The seed is deterministic and idempotent (stable IDs). Running it without `--reset` changes nothing when the data already exists. It refuses to run if `SPENDOS_ENV=production`.

## Expected totals (October 2026, Aadi Technology)

Income 8,50,000; expenses 5,00,000; simplified operating surplus 3,50,000 (not audited profit). Employee costs 3,00,000 - cloud and infrastructure 35,000 - software 25,000 - marketing 40,000 - office and administration 30,000 - travel 20,000 - training 25,000 - equipment and maintenance 15,000 - other 10,000. Claims still waiting for approval or payment are **not** included in these figures.
