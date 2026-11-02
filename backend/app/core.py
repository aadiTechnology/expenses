"""Configuration, database, security, request context, permission and entitlement enforcement."""
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

import bcrypt
from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import models as m

ROOT = Path(__file__).resolve().parent.parent
# PostgreSQL is the product database (docker compose up -d). SQLite remains possible for throwaway local runs via SPENDOS_DB.
# SPENDOS_ENV defaults to production so a forgotten variable can never switch demo conveniences on.
ENV = os.environ.get("SPENDOS_ENV", "production")  # demo | production
if ENV == "production":
    if not os.environ.get("SPENDOS_DB"):
        raise RuntimeError("SPENDOS_DB (PostgreSQL URL) must be set in production")
    if len(os.environ.get("SPENDOS_SECRET", "")) < 32:
        raise RuntimeError("SPENDOS_SECRET must be set to a random value of at least 32 characters in production")
    DB_URL = os.environ["SPENDOS_DB"]
    SECRET = os.environ["SPENDOS_SECRET"]
else:
    DB_URL = os.environ.get("SPENDOS_DB", "postgresql+psycopg://spendos:spendos_dev@localhost:15433/spendos_demo")
    SECRET = os.environ.get("SPENDOS_SECRET", "demo-only-secret-change-me-in-any-real-environment")
ALLOW_REGISTRATION = os.environ.get("SPENDOS_ALLOW_REGISTRATION", "true").lower() == "true"
CORS_ORIGINS = [o.strip() for o in os.environ.get("SPENDOS_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
STORAGE = Path(os.environ.get("SPENDOS_STORAGE", str(ROOT / "data" / "files")))
SESSION_HOURS = 8

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
if DB_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _fk(dbapi, _):  # noqa: ANN001
        dbapi.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- money (decimal-safe, integer minor units) ----------------
def to_minor(value) -> int:
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise HTTPException(422, "Amount must be a number")
    if d != d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP):
        raise HTTPException(422, "Amount can have at most two decimal places")
    if d <= 0:
        raise HTTPException(422, "Amount must be greater than zero")
    return int((d * 100).to_integral_value(ROUND_HALF_UP))


def fmt(minor: int) -> str:
    return f"{Decimal(minor) / 100:.2f}"


# ---------------- passwords and tokens ----------------
def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode()[:72], bcrypt.gensalt(rounds=10)).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode()[:72], h.encode())
    except ValueError:
        return False


def make_token(db: DbSession, user_id: str, tenant_id: str | None) -> str:
    jti = m.uid("jti_")
    db.add(m.Session(jti=jti, user_id=user_id))
    db.commit()
    exp = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    return jwt.encode({"sub": user_id, "tid": tenant_id, "jti": jti, "exp": exp}, SECRET, algorithm="HS256")


# ---------------- roles and permissions (seeded into role_permissions; enforced from the DB) ----------------
ALL_BUSINESS = [
    "txn.create", "txn.export", "report.read", "ai.use",
]
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": ["scope.all", "txn.create", "txn.edit_any", "txn.delete_any", "txn.import", "txn.export", "config.manage",
              "member.manage", "budget.manage", "account.manage", "report.read", "audit.read", "ai.use", "goals.manage",
              "approve.finance"],
    "family_member": ["scope.own", "scope.shared", "txn.create", "txn.export", "report.read", "ai.use"],
    "family_viewer": ["scope.shared", "report.read"],
    "org_admin": ["scope.all", "txn.create", "txn.edit_any", "txn.delete_any", "txn.import", "txn.export", "config.manage",
                  "member.manage", "budget.manage", "account.manage", "report.read", "audit.read", "ai.use",
                  "growth.read", "growth.manage", "approve.finance", "approve.project", "approve.department"],
    "finance_manager": ["scope.all", "txn.create", "txn.edit_any", "txn.import", "txn.export", "budget.manage",
                        "account.manage", "report.read", "ai.use", "growth.read", "growth.manage", "approve.finance",
                        "audit.read"],
    "department_manager": ["scope.department", "scope.own", "txn.create", "txn.export", "report.read", "ai.use",
                           "approve.department"],
    "project_manager": ["scope.project", "scope.own", "txn.create", "txn.export", "report.read", "ai.use",
                        "approve.project"],
    "employee": ["scope.own", "txn.create", "ai.use"],
    "auditor": ["scope.all", "txn.export", "report.read", "audit.read", "growth.read"],
}
PERSONAL_ROLES = ["owner", "family_member", "family_viewer"]
BUSINESS_ROLES = ["org_admin", "finance_manager", "department_manager", "project_manager", "employee", "auditor"]
ROLE_LABELS = {
    "owner": "Owner", "family_member": "Family Member", "family_viewer": "Family Viewer",
    "org_admin": "Organization Admin", "finance_manager": "Finance Manager", "department_manager": "Department Manager",
    "project_manager": "Project Manager", "employee": "Employee", "auditor": "Auditor",
}

# transaction states: draft, submitted, pm_approved (awaiting finance), verified (awaiting payout), paid, posted, rejected
COUNTED = ("posted", "paid")  # states that move money and count in actuals
PENDING = ("submitted", "pm_approved", "verified")


@dataclass
class Ctx:
    user: m.User
    tenant: m.Tenant | None
    membership: m.Membership | None
    perms: set = field(default_factory=set)
    project_ids: set = field(default_factory=set)
    db: DbSession | None = None

    def can(self, p: str) -> bool:
        return p in self.perms

    @property
    def role(self) -> str:
        return self.membership.role if self.membership else "platform_admin"


def current_ctx(authorization: str = Header(default=""), db: DbSession = Depends(get_db)) -> Ctx:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Not signed in")
    try:
        claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(401, "Session expired or invalid")
    sess = db.get(m.Session, claims["jti"])
    user = db.get(m.User, claims["sub"])
    if not sess or sess.revoked or not user or not user.is_active:
        raise HTTPException(401, "Session ended")
    tenant = membership = None
    perms: set = set()
    projects: set = set()
    if claims.get("tid"):
        tenant = db.get(m.Tenant, claims["tid"])
        membership = db.scalar(select(m.Membership).where(m.Membership.user_id == user.id,
                                                          m.Membership.tenant_id == claims["tid"],
                                                          m.Membership.status == "active"))
        if not tenant or not membership:
            raise HTTPException(403, "You do not have access to this organization")
        perms = set(db.scalars(select(m.RolePermission.permission).where(m.RolePermission.role == membership.role)))
        projects = set(db.scalars(select(m.ProjectAssignment.project_id).where(
            m.ProjectAssignment.membership_id == membership.id)))
    return Ctx(user, tenant, membership, perms, projects, db)


def tenant_ctx(ctx: Ctx = Depends(current_ctx)) -> Ctx:
    if not ctx.tenant:
        raise HTTPException(403, "Select an organization first")
    return ctx


def require(*perms: str):
    """Backend authorization: the caller needs at least one of the permissions."""
    def dep(ctx: Ctx = Depends(tenant_ctx)) -> Ctx:
        if not any(ctx.can(p) for p in perms):
            raise HTTPException(403, "You do not have permission for this action")
        return ctx
    return dep


def platform_admin(ctx: Ctx = Depends(current_ctx)) -> Ctx:
    if not ctx.user.is_platform_admin:
        raise HTTPException(403, "Platform administrators only")
    return ctx


# ---------------- entitlements ----------------
def effective_entitlements(db: DbSession, tenant: m.Tenant, today: date | None = None) -> dict[str, dict]:
    """Auditable per-module decision: plan membership first, then the explicit override and its expiry."""
    today = today or date.today()
    plan_mods = set(db.scalars(select(m.PlanModule.module_code).where(m.PlanModule.plan_code == tenant.plan_code)))
    overrides = {e.module_code: e for e in db.scalars(select(m.TenantEntitlement).where(m.TenantEntitlement.tenant_id == tenant.id))}
    out = {}
    for mod in db.scalars(select(m.Module)):
        enabled, source = mod.code in plan_mods, "plan" if mod.code in plan_mods else "not in plan"
        ov = overrides.get(mod.code)
        if ov:
            if ov.expires_at and ov.expires_at < today:
                source += " (override expired)"
            else:
                enabled, source = ov.enabled, "override" + (f" until {ov.expires_at}" if ov.expires_at else "")
        out[mod.code] = {"enabled": enabled, "source": source}
    # a module is only usable when its dependencies are
    for mod in db.scalars(select(m.Module)):
        if out[mod.code]["enabled"] and any(not out.get(d, {}).get("enabled") for d in (mod.depends_on or [])):
            out[mod.code] = {"enabled": False, "source": "dependency not entitled"}
    return out


def require_module(code: str):
    def dep(ctx: Ctx = Depends(tenant_ctx)) -> Ctx:
        ent = effective_entitlements(ctx.db, ctx.tenant)
        if not ent.get(code, {}).get("enabled"):
            raise HTTPException(403, detail={"code": "ENTITLEMENT_DENIED", "message": "This feature is not available for your subscription."})
        return ctx
    return dep


# ---------------- audit ----------------
def audit(db: DbSession, ctx: Ctx | None, entity: str, entity_id: str | None, action: str, detail: dict | None = None,
          tenant_id: str | None = None):
    db.add(m.AuditEvent(tenant_id=tenant_id or (ctx.tenant.id if ctx and ctx.tenant else None),
                        actor_user_id=ctx.user.id if ctx else None, actor_name=ctx.user.name if ctx else "system",
                        entity=entity, entity_id=entity_id, action=action, detail=detail or {}))


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
