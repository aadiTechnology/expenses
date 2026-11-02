"""Scheduled-style notifications (recurring reminders, monthly summary), recurring payments, personal data export and account deletion."""
import calendar
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select

from .. import models as m
from ..core import Ctx, audit, current_ctx, fmt, get_db, hash_password, require, tenant_ctx, to_minor, verify_password
from ..ledger import T, month_bounds, totals, visible_filter
from .txn import ser

router = APIRouter(prefix="/api/v1", tags=["extras"])
WATCHER_ROLES = ("owner", "org_admin", "finance_manager")


def _ctx_for(db, tenant, mem, user):
    perms = set(db.scalars(select(m.RolePermission.permission).where(m.RolePermission.role == mem.role)))
    return Ctx(user, tenant, mem, perms, set(), db)


def generate_scheduled(db, tenant: m.Tenant, today: date) -> int:
    """Idempotent: each reminder and summary has a dedupe key, so calling this often never repeats a notification."""
    created = 0
    watchers = [(mem, db.get(m.User, mem.user_id)) for mem in db.scalars(select(m.Membership).where(
        m.Membership.tenant_id == tenant.id, m.Membership.status == "active", m.Membership.role.in_(WATCHER_ROLES)))]

    def add(user_id, kind, key, title, body):
        nonlocal created
        if not db.scalar(select(m.Notification.id).where(m.Notification.tenant_id == tenant.id, m.Notification.user_id == user_id, m.Notification.dedupe_key == key)):
            db.add(m.Notification(tenant_id=tenant.id, user_id=user_id, kind=kind, dedupe_key=key, title=title, body=body))
            created += 1

    for rec in db.scalars(select(m.Recurring).where(m.Recurring.tenant_id == tenant.id)):
        day = min(rec.day_of_month, calendar.monthrange(today.year, today.month)[1])
        due = date(today.year, today.month, day)
        if today <= due <= today + timedelta(days=3):
            for mem, u in watchers:
                add(u.id, "reminder", f"rec:{rec.id}:{due:%Y-%m}", f"Payment due {due:%d %b}: {rec.description}", f"{fmt(rec.amount_minor)} is expected on {due:%d %B %Y}.")
    py, pm = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    period = f"{py}-{pm:02d}"
    s, e = month_bounds(period)
    for mem, u in watchers:
        t = totals(db, _ctx_for(db, tenant, mem, u), s, e)
        if t["income"] or t["expense"]:
            add(u.id, "summary", f"summary:{period}", f"Monthly summary for {period}",
                f"Income {fmt(t['income'])}, expenses {fmt(t['expense'])}, difference {fmt(t['savings'])} (posted figures only).")
    return created


class RefreshIn(BaseModel):
    today: date | None = None


@router.post("/notifications/refresh")
def refresh(b: RefreshIn, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    n = generate_scheduled(db, ctx.tenant, b.today or date.today())
    db.commit()
    return {"created": n}


# ---------------- recurring payments ----------------
class RecIn(BaseModel):
    description: str
    amount: str | float
    day_of_month: int
    category_id: str | None = None


@router.get("/recurring")
def recurring(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    cats = {c.id: c.name for c in db.scalars(select(m.Category).where(m.Category.tenant_id == ctx.tenant.id))}
    return [{"id": r.id, "description": r.description, "amount_minor": r.amount_minor, "day_of_month": r.day_of_month, "category": cats.get(r.category_id)}
            for r in db.scalars(select(m.Recurring).where(m.Recurring.tenant_id == ctx.tenant.id).order_by(m.Recurring.day_of_month))]


@router.post("/recurring")
def add_recurring(b: RecIn, ctx: Ctx = Depends(require("config.manage", "budget.manage")), db=Depends(get_db)):
    if not 1 <= b.day_of_month <= 31:
        raise HTTPException(422, "Day of month must be between 1 and 31")
    if b.category_id and not db.scalar(select(m.Category.id).where(m.Category.id == b.category_id, m.Category.tenant_id == ctx.tenant.id)):
        raise HTTPException(422, "Unknown category")
    r = m.Recurring(tenant_id=ctx.tenant.id, description=b.description.strip(), amount_minor=to_minor(b.amount), day_of_month=b.day_of_month, category_id=b.category_id)
    db.add(r)
    db.flush()
    audit(db, ctx, "recurring", r.id, "created", {"description": r.description})
    db.commit()
    return {"id": r.id}


@router.delete("/recurring/{rid}")
def del_recurring(rid: str, ctx: Ctx = Depends(require("config.manage", "budget.manage")), db=Depends(get_db)):
    r = db.scalar(select(m.Recurring).where(m.Recurring.id == rid, m.Recurring.tenant_id == ctx.tenant.id))
    if not r:
        raise HTTPException(404, "Not found")
    audit(db, ctx, "recurring", rid, "deleted", {"description": r.description})
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------------- privacy: export and deletion ----------------
@router.get("/me/export")
def export_me(ctx: Ctx = Depends(current_ctx), db=Depends(get_db)):
    """Everything this person can see about themselves: profile, memberships and the transactions their role allows them to read."""
    out = {"profile": {"name": ctx.user.name, "email": ctx.user.email, "created_at": ctx.user.created_at.isoformat()},
           "memberships": [{"tenant_id": mem.tenant_id, "role": mem.role, "status": mem.status} for mem in db.scalars(select(m.Membership).where(m.Membership.user_id == ctx.user.id))],
           "tenant": None, "transactions": []}
    if ctx.tenant:
        out["tenant"] = {"id": ctx.tenant.id, "name": ctx.tenant.name}
        out["transactions"] = [ser(t) for t in db.scalars(select(T).where(visible_filter(ctx)).order_by(T.date, T.seq))]
        out["notifications"] = [{"title": n.title, "body": n.body, "at": n.created_at.isoformat()} for n in db.scalars(
            select(m.Notification).where(m.Notification.tenant_id == ctx.tenant.id, m.Notification.user_id == ctx.user.id))]
    audit(db, ctx, "user", ctx.user.id, "data_exported", {})
    db.commit()
    return out


class DeleteIn(BaseModel):
    password: str


def purge_tenant(db, tid: str):
    for tbl in reversed(m.Base.metadata.sorted_tables):
        if "tenant_id" in tbl.c and tbl.name != "audit_events":
            db.execute(delete(tbl).where(tbl.c.tenant_id == tid))
    db.execute(delete(m.Tenant).where(m.Tenant.id == tid))


@router.post("/me/delete")
def delete_me(b: DeleteIn, ctx: Ctx = Depends(current_ctx), db=Depends(get_db)):
    u = ctx.user
    if not verify_password(b.password, u.password_hash):
        raise HTTPException(403, "Password is incorrect")
    mems = list(db.scalars(select(m.Membership).where(m.Membership.user_id == u.id, m.Membership.status == "active")))
    for mem in mems:
        t = db.get(m.Tenant, mem.tenant_id)
        if t.is_demo:
            raise HTTPException(409, "Demo accounts cannot be deleted. Use a registered account.")
        others = db.scalars(select(m.Membership.id).where(m.Membership.tenant_id == t.id, m.Membership.status == "active", m.Membership.id != mem.id)).all()
        if mem.role in ("owner", "org_admin") and others:
            raise HTTPException(409, f"You are the administrator of {t.name}, which has other members. Give someone else the administrator role first.")
    for mem in mems:
        t = db.get(m.Tenant, mem.tenant_id)
        others = db.scalars(select(m.Membership.id).where(m.Membership.tenant_id == t.id, m.Membership.status == "active", m.Membership.id != mem.id)).all()
        if not others:
            purge_tenant(db, t.id)  # sole member: the whole workspace goes with the account
        else:
            mem.status = "removed"
    for s in db.scalars(select(m.Session).where(m.Session.user_id == u.id)):
        s.revoked = True
    audit(db, None, "user", u.id, "account_deleted", {}, tenant_id=None)
    u.email, u.name, u.is_active = f"deleted-{u.id}@deleted.invalid", "Deleted user", False
    u.password_hash = hash_password(secrets.token_hex(16))
    db.commit()
    return {"ok": True}
