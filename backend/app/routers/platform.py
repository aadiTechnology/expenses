from datetime import date

import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from .. import models as m
from .. import mail
from ..core import EMAIL_RE, Ctx, audit, effective_entitlements, get_db, hash_password, platform_admin
from .auth import create_tenant

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


def mod_ser(x: m.Module):
    return {"code": x.code, "name": x.name, "description": x.description, "primary_pillar": x.primary_pillar, "secondary_pillar": x.secondary_pillar,
            "priority": x.priority, "lifecycle": x.lifecycle, "depends_on": x.depends_on, "entitlement_key": x.entitlement_key}


@router.get("/modules")
def modules(ctx: Ctx = Depends(platform_admin), db=Depends(get_db)):
    plans = {}
    for pm in db.scalars(select(m.PlanModule)):
        plans.setdefault(pm.module_code, []).append(pm.plan_code)
    return {"modules": [mod_ser(x) | {"plans": plans.get(x.code, [])} for x in db.scalars(select(m.Module).order_by(m.Module.primary_pillar, m.Module.code))],
            "plans": [{"code": p.code, "name": p.name, "edition": p.edition} for p in db.scalars(select(m.Plan))]}


class PillarIn(BaseModel):
    primary_pillar: str
    secondary_pillar: str | None = None


@router.patch("/modules/{code}")
def classify(code: str, b: PillarIn, ctx: Ctx = Depends(platform_admin), db=Depends(get_db)):
    x = db.get(m.Module, code)
    if not x or b.primary_pillar not in ("P1", "P2", "P3") or b.secondary_pillar not in (None, "P1", "P2", "P3"):
        raise HTTPException(422, "Unknown module or pillar")
    old = (x.primary_pillar, x.secondary_pillar)
    x.primary_pillar, x.secondary_pillar = b.primary_pillar, b.secondary_pillar
    audit(db, ctx, "module", code, "classification_changed", {"from": old, "to": [b.primary_pillar, b.secondary_pillar]}, tenant_id="platform")
    db.commit()
    return mod_ser(x)


@router.get("/tenants")
def tenants(ctx: Ctx = Depends(platform_admin), db=Depends(get_db)):
    out = []
    for t in db.scalars(select(m.Tenant).order_by(m.Tenant.name)):
        ent = effective_entitlements(db, t)
        out.append({"id": t.id, "name": t.name, "edition": t.edition, "plan_code": t.plan_code, "is_demo": t.is_demo, "entitlements": ent})
    return out


class EntIn(BaseModel):
    enabled: bool
    expires_at: date | None = None
    reason: str | None = None


@router.put("/tenants/{tid}/entitlements/{code}")
def set_ent(tid: str, code: str, b: EntIn, ctx: Ctx = Depends(platform_admin), db=Depends(get_db)):
    if not db.get(m.Tenant, tid) or not db.get(m.Module, code):
        raise HTTPException(404, "Unknown tenant or module")
    e = db.scalar(select(m.TenantEntitlement).where(m.TenantEntitlement.tenant_id == tid, m.TenantEntitlement.module_code == code))
    if not e:
        e = m.TenantEntitlement(tenant_id=tid, module_code=code)
        db.add(e)
    e.enabled, e.expires_at, e.reason = b.enabled, b.expires_at, b.reason
    audit(db, ctx, "entitlement", f"{tid}:{code}", "override_set", {"enabled": b.enabled, "expires_at": str(b.expires_at), "reason": b.reason}, tenant_id=tid)
    db.commit()
    return effective_entitlements(db, db.get(m.Tenant, tid))[code]


@router.delete("/tenants/{tid}/entitlements/{code}")
def clear_ent(tid: str, code: str, ctx: Ctx = Depends(platform_admin), db=Depends(get_db)):
    e = db.scalar(select(m.TenantEntitlement).where(m.TenantEntitlement.tenant_id == tid, m.TenantEntitlement.module_code == code))
    if e:
        db.delete(e)
        audit(db, ctx, "entitlement", f"{tid}:{code}", "override_cleared", {}, tenant_id=tid)
        db.commit()
    return {"ok": True}


@router.get("/usage")
def usage(ctx: Ctx = Depends(platform_admin), db=Depends(get_db)):
    """Aggregated adoption by pillar - counts of tenants entitled, never any financial record."""
    out = {"P1": 0, "P2": 0, "P3": 0}
    mods = {x.code: x.primary_pillar for x in db.scalars(select(m.Module))}
    tenants = list(db.scalars(select(m.Tenant)))
    per_module = {}
    for t in tenants:
        for code, e in effective_entitlements(db, t).items():
            if e["enabled"]:
                per_module[code] = per_module.get(code, 0) + 1
    for code, n in per_module.items():
        out[mods[code]] += n
    return {"tenants": len(tenants), "entitled_modules_by_pillar": out, "tenants_per_module": per_module}


class NewOrgIn(BaseModel):
    name: str
    edition: str
    template: str | None = None
    admin_name: str
    admin_email: str


@router.post("/organizations")
def create_organization(b: NewOrgIn, bg: BackgroundTasks, ctx: Ctx = Depends(platform_admin), db=Depends(get_db)):
    """Invite-only onboarding: the platform administrator creates the workspace and invites its first administrator by email."""
    if not EMAIL_RE.match(b.admin_email):
        raise HTTPException(422, "Enter a valid email address for the administrator")
    u = db.scalar(select(m.User).where(m.User.email == b.admin_email.lower()))
    token = None
    if not u:
        u = m.User(email=b.admin_email.lower(), name=b.admin_name.strip(), password_hash=hash_password(secrets.token_hex(24)))
        db.add(u)
        db.flush()
        token = secrets.token_urlsafe(24)
        db.add(m.PasswordReset(token=token, user_id=u.id, expires_at=m.now() + timedelta(days=7)))
    t = create_tenant(db, u, b.name.strip(), b.edition, b.template)
    audit(db, ctx, "tenant", t.id, "created_by_platform_admin", {"admin": u.email, "edition": b.edition}, tenant_id=t.id)
    db.commit()
    out = {"tenant_id": t.id, "admin_email": u.email, "invite_emailed": False, "invite_link": None}
    if token:
        link = f"{mail.public_url()}/reset?token={token}"
        if mail.configured():
            subject, text = mail.invite_email(u.name, t.name, token)
            bg.add_task(mail.send, u.email, subject, text)
            out["invite_emailed"] = True
        else:
            out["invite_link"] = link  # no mail server configured: hand the link over manually
    return out
