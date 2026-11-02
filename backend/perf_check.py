"""Initial performance check (PRD target: dashboard and transaction list under 2 s for normal workloads).
Loads extra synthetic transactions into a scratch PostgreSQL database and times the API in-process.
Run:  python perf_check.py [extra_rows]      (needs the spendos_perf database; created automatically)"""
import os
import random
import statistics
import subprocess
import sys
import time

EXTRA = int(sys.argv[1]) if len(sys.argv) > 1 else 25000
os.environ["SPENDOS_ENV"] = "demo"
os.environ["SPENDOS_DB"] = "postgresql+psycopg://spendos:spendos_dev@localhost:15433/spendos_perf"
subprocess.run(["docker", "exec", "spendos-postgres", "psql", "-U", "spendos", "-d", "postgres", "-q", "-c", "DROP DATABASE IF EXISTS spendos_perf WITH (FORCE)", "-c", "CREATE DATABASE spendos_perf"], check=True)

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models as m  # noqa: E402
from app import seed  # noqa: E402
from app.core import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

seed.run(do_reset=True)
random.seed(7)
with SessionLocal() as db:
    cats = [c.id for c in db.scalars(select(m.Category).where(m.Category.tenant_id == seed.BUSINESS_ID, m.Category.kind == "expense", m.Category.parent_id.is_(None)))]
    projs = [p.id for p in db.scalars(select(m.Project).where(m.Project.tenant_id == seed.BUSINESS_ID))]
    deps = [d.id for d in db.scalars(select(m.Department).where(m.Department.tenant_id == seed.BUSINESS_ID))]
    rows = []
    for i in range(EXTRA):
        d = date(2026, 8, 1) + timedelta(days=random.randrange(0, 92))
        rows.append(m.Transaction(id=f"txn_perf_{i}", tenant_id=seed.BUSINESS_ID, seq=1000 + i, date=d, type="expense", amount_minor=random.randrange(10000, 900000), currency="INR",
                                  category_id=random.choice(cats), description=f"Load test expense {i}", account_id="acc_a_bank", created_by="mem_a_sanjay", member_id="mem_a_sanjay",
                                  department_id=random.choice(deps), project_id=random.choice(projs), status="posted", sample=True))
    db.bulk_save_objects(rows)
    db.commit()
    total = db.query(m.Transaction).filter(m.Transaction.tenant_id == seed.BUSINESS_ID).count()
print(f"Aadi tenant now has {total} transactions")

with TestClient(app) as c:
    h = {"Authorization": "Bearer " + c.post("/api/v1/auth/login", json={"email": "sanjay.kulkarni" + seed.DOMAIN, "password": seed.DEMO_PASSWORD}).json()["token"]}
    cases = [("dashboard (October)", "/api/v1/dashboard?period=2026-10"), ("dashboard (September)", "/api/v1/dashboard?period=2026-09"), ("transaction list, page 1 of 25", "/api/v1/transactions?page_size=25"),
             ("transaction list, filtered", "/api/v1/transactions?q=Load&project_id=prj_a_crm&page_size=25"), ("report: project expenditure", "/api/v1/reports/project?period=2026-10"),
             ("report: category", "/api/v1/reports/category?period=2026-09"), ("growth spend", "/api/v1/growth/spend?period=2026-10"), ("budgets", "/api/v1/budgets?period=2026-10")]
    print(f"{'case':36}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}")
    for name, url in cases:
        ts = []
        for _ in range(12):
            t0 = time.perf_counter()
            r = c.get(url, headers=h)
            ts.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200, (url, r.text[:200])
        ts.sort()
        print(f"{name:36}{statistics.median(ts):10.0f}{ts[int(len(ts) * 0.95) - 1]:10.0f}{ts[-1]:10.0f}")
