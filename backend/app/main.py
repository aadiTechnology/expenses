from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from . import models as m
from .core import CORS_ORIGINS, ENV, ROLE_PERMISSIONS, SessionLocal, engine
from .routers import auth, config, extras, insight, platform, txn

MODULES = [
    # code, name, description, pillar, secondary, priority, depends
    ("transactions", "Transactions", "Income, expense, transfer, refund, reimbursement ledger", "P1", None, "P0", []),
    ("accounts", "Accounts", "Cash, bank, UPI, card and wallet accounts", "P1", None, "P0", []),
    ("categories", "Categories", "Tenant-configurable category tree", "P1", None, "P0", []),
    ("budgets", "Budgets", "Monthly budgets and utilisation alerts", "P1", None, "P0", []),
    ("approvals", "Approvals & reimbursements", "Multi-level approval and reimbursement", "P1", None, "P0", ["transactions"]),
    ("org_structure", "Departments & projects", "Organisation dimensions", "P1", None, "P0", []),
    ("reports", "Reports & dashboards", "Operational visibility and exports", "P1", None, "P0", []),
    ("audit", "Audit history", "Secure audit log", "P1", None, "P0", []),
    ("growth_dimensions", "Growth spend dimensions", "Campaign / channel / initiative dimensions", "P2", "P1", "P1", []),
    ("growth_spend", "Marketing & sales spend reports", "Spend vs budget by campaign", "P2", "P1", "P1", ["growth_dimensions"]),
    ("growth_import", "Growth data import", "CSV import of lead/customer metrics with provenance", "P2", None, "P2", ["growth_spend"]),
    ("ai_capture", "AI expense capture", "Voice, receipt and register capture with confirmation", "P3", "P1", "P1", ["transactions"]),
    ("ai_insights", "AI insights & questions", "Permission-aware insights and natural-language questions", "P3", None, "P1", []),
    ("ai_anomaly", "Anomaly review", "Advisory unusual-spend flags", "P3", None, "P2", ["ai_insights"]),
    ("ai_forecast", "Forecast estimates", "Labelled estimates, never actuals", "P3", None, "P2", ["ai_insights"]),
]
P1 = ["transactions", "accounts", "categories", "budgets", "approvals", "org_structure", "reports", "audit"]
AI = ["ai_capture", "ai_insights", "ai_anomaly", "ai_forecast"]
PLANS = [("personal_free", "Personal (Free)", "personal", P1 + AI), ("business_standard", "Business Standard", "business", P1 + ["ai_capture", "ai_insights"]),
         ("business_growth", "Business Growth", "business", P1 + AI + ["growth_dimensions", "growth_spend", "growth_import"])]


def ensure_catalogue(db):
    """Idempotent: catalogue, plans and role permissions are data, loaded from code definitions."""
    for code, name, desc, p1, p2, prio, dep in MODULES:
        if not db.get(m.Module, code):
            db.add(m.Module(code=code, name=name, description=desc, primary_pillar=p1, secondary_pillar=p2, priority=prio, depends_on=dep, entitlement_key=f"spendos.{code}"))
    for code, name, ed, mods in PLANS:
        if not db.get(m.Plan, code):
            db.add(m.Plan(code=code, name=name, edition=ed))
            for mc in mods:
                db.add(m.PlanModule(plan_code=code, module_code=mc))
    if not db.scalar(select(m.RolePermission.id).limit(1)):
        for role, perms in ROLE_PERMISSIONS.items():
            for p in perms:
                db.add(m.RolePermission(role=role, permission=p))
    db.commit()


def migrate():
    """Schema is managed by Alembic migrations (alembic/versions); startup applies any that are pending."""
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(cfg, "head")


def init_db():
    migrate()
    with SessionLocal() as db:
        ensure_catalogue(db)


prod = ENV == "production"
app = FastAPI(title="Aadi SpendOS API", version="1.1.0", docs_url=None if prod else "/docs", redoc_url=None, openapi_url=None if prod else "/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, txn.router, config.router, insight.router, platform.router, extras.router):
    app.include_router(r)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
