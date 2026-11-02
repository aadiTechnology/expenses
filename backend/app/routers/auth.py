import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select

from .. import models as m
from ..core import (ALLOW_REGISTRATION, BUSINESS_ROLES, EMAIL_RE, ENV, PERSONAL_ROLES, ROLE_LABELS, SECRET, Ctx, audit, current_ctx, effective_entitlements,
                    get_db, hash_password, make_token, require, tenant_ctx, verify_password)
from .. import mail
from ..templates import TEMPLATES, apply_template

router = APIRouter(prefix="/api/v1", tags=["auth"])
MAX_FAILED_LOGINS, LOCK_MINUTES = 5, 15


def memberships_of(db, user):
    rows = db.execute(select(m.Membership, m.Tenant).join(m.Tenant, m.Tenant.id == m.Membership.tenant_id)
                      .where(m.Membership.user_id == user.id, m.Membership.status == "active")).all()
    return [{"tenant_id": t.id, "tenant_name": t.name, "edition": t.edition, "role": mem.role, "role_label": ROLE_LABELS[mem.role],
             "is_demo": t.is_demo} for mem, t in rows]


def session_payload(db, user, tenant_id):
    return {"token": make_token(db, user.id, tenant_id), "memberships": memberships_of(db, user),
            "user": {"id": user.id, "name": user.name, "email": user.email, "is_platform_admin": user.is_platform_admin}}


class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    edition: str = "personal"
    template: str | None = None
    organization_name: str | None = None


def check_password(p: str):
    if len(p) < 8 or not any(c.isdigit() for c in p) or not any(c.isalpha() for c in p):
        raise HTTPException(422, "Password needs at least 8 characters with letters and numbers")


def create_tenant(db, user, name, edition, template):
    template = template or ("personal" if edition == "personal" else "it_company")
    if TEMPLATES[template]["edition"] != edition:
        raise HTTPException(422, "That template does not belong to the chosen edition")
    t = m.Tenant(name=name, edition=edition, plan_code="personal_free" if edition == "personal" else "business_standard",
                 template_code=template, currency="INR")
    db.add(t)
    db.flush()
    apply_template(db, t, template)
    mem = m.Membership(user_id=user.id, tenant_id=t.id, role="owner" if edition == "personal" else "org_admin")
    db.add(mem)
    audit(db, None, "tenant", t.id, "created", {"edition": edition, "template": template}, tenant_id=t.id)
    return t


@router.get("/auth/config")
def public_config():
    """What the sign-in page needs to know before anyone is signed in."""
    return {"registration": ALLOW_REGISTRATION, "demo": ENV == "demo", "email": mail.configured()}


@router.post("/auth/register")
def register(body: RegisterIn, db=Depends(get_db)):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "Self-registration is turned off for this environment. Ask an administrator for an invitation.")
    if not EMAIL_RE.match(body.email):
        raise HTTPException(422, "Enter a valid email address")
    check_password(body.password)
    if db.scalar(select(m.User.id).where(m.User.email == body.email.lower())):
        raise HTTPException(409, "An account with this email already exists")
    if body.edition not in ("personal", "business"):
        raise HTTPException(422, "Edition must be personal or business")
    u = m.User(email=body.email.lower(), name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    t = create_tenant(db, u, body.organization_name or (f"{body.name}'s household" if body.edition == "personal" else f"{body.name}'s organization"),
                      body.edition, body.template)
    db.commit()
    return session_payload(db, u, t.id)


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db=Depends(get_db)):
    u = db.scalar(select(m.User).where(m.User.email == body.email.lower().strip()))
    if u and u.locked_until and u.locked_until > m.now():
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes or reset your password.")
    if not u or not u.is_active or not verify_password(body.password, u.password_hash):
        if u:  # lock the account for 15 minutes after 5 consecutive failures
            u.failed_logins = (u.failed_logins or 0) + 1
            if u.failed_logins >= MAX_FAILED_LOGINS:
                u.locked_until = m.now() + timedelta(minutes=LOCK_MINUTES)
                u.failed_logins = 0
                audit(db, None, "user", u.id, "locked_after_failed_logins", {}, tenant_id=None)
            db.commit()
        raise HTTPException(401, "Email or password is incorrect")
    u.failed_logins, u.locked_until = 0, None
    db.commit()
    ms = memberships_of(db, u)
    return session_payload(db, u, ms[0]["tenant_id"] if ms else None)


@router.post("/auth/logout")
def logout(ctx: Ctx = Depends(current_ctx), authorization: str = Header(default=""), db=Depends(get_db)):
    claims = jwt.decode(authorization.removeprefix("Bearer ").strip(), SECRET, algorithms=["HS256"])
    s = db.get(m.Session, claims["jti"])
    if s:
        s.revoked = True
        db.commit()
    return {"ok": True}


@router.post("/auth/switch/{tenant_id}")
def switch(tenant_id: str, ctx: Ctx = Depends(current_ctx), db=Depends(get_db)):
    mem = db.scalar(select(m.Membership).where(m.Membership.user_id == ctx.user.id, m.Membership.tenant_id == tenant_id, m.Membership.status == "active"))
    if not mem:
        raise HTTPException(403, "You do not have access to this organization")
    return {"token": make_token(db, ctx.user.id, tenant_id)}


class NewOrg(BaseModel):
    name: str
    edition: str
    template: str | None = None


@router.post("/organizations")
def new_org(body: NewOrg, ctx: Ctx = Depends(current_ctx), db=Depends(get_db)):
    t = create_tenant(db, ctx.user, body.name, body.edition, body.template)
    db.commit()
    return session_payload(db, ctx.user, t.id)


class ForgotIn(BaseModel):
    email: str


@router.post("/auth/forgot")
def forgot(body: ForgotIn, bg: BackgroundTasks, db=Depends(get_db)):
    u = db.scalar(select(m.User).where(m.User.email == body.email.lower().strip()))
    out = {"message": "If that email exists, a reset link has been sent."}
    if u and u.is_active:
        tok = secrets.token_urlsafe(24)
        db.add(m.PasswordReset(token=tok, user_id=u.id, expires_at=m.now() + timedelta(hours=1)))
        db.commit()
        if mail.configured():
            subject, text = mail.reset_email(u.name, tok)
            bg.add_task(mail.send, u.email, subject, text)  # same answer whether or not the address exists
        if ENV == "demo":  # the demo shows the code so the flow can be tried without a mailbox
            out["demo_reset_token"] = tok
    return out


class ResetIn(BaseModel):
    token: str
    password: str


@router.post("/auth/reset")
def reset(body: ResetIn, db=Depends(get_db)):
    check_password(body.password)
    pr = db.get(m.PasswordReset, body.token)
    if not pr or pr.used:
        raise HTTPException(400, "Reset link is invalid or already used")
    if pr.expires_at and pr.expires_at < m.now():
        raise HTTPException(400, "This link has expired. Ask for a new one.")
    u = db.get(m.User, pr.user_id)
    u.password_hash = hash_password(body.password)
    u.failed_logins, u.locked_until = 0, None
    pr.used = True
    for s in db.scalars(select(m.Session).where(m.Session.user_id == u.id)):
        s.revoked = True
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(current_ctx), db=Depends(get_db)):
    out = {"user": {"id": ctx.user.id, "name": ctx.user.name, "email": ctx.user.email, "is_platform_admin": ctx.user.is_platform_admin},
           "memberships": memberships_of(db, ctx.user), "tenant": None}
    if ctx.tenant:
        t = ctx.tenant
        out["tenant"] = {"id": t.id, "name": t.name, "edition": t.edition, "currency": t.currency, "is_demo": t.is_demo,
                         "plan_code": t.plan_code, "config": t.config}
        out["role"] = ctx.membership.role
        out["role_label"] = ROLE_LABELS[ctx.membership.role]
        out["membership_id"] = ctx.membership.id
        out["permissions"] = sorted(ctx.perms)
        out["entitlements"] = {k: v["enabled"] for k, v in effective_entitlements(db, t).items()}
        out["unread"] = len(list(db.scalars(select(m.Notification.id).where(m.Notification.tenant_id == t.id, m.Notification.user_id == ctx.user.id, m.Notification.read.is_(False)))))
    return out


# ---------------- members ----------------
@router.get("/members")
def members(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    if not (ctx.can("member.manage") or ctx.can("scope.all") or ctx.can("approve.project")):
        # others only see themselves
        rows = db.execute(select(m.Membership, m.User).join(m.User).where(m.Membership.id == ctx.membership.id)).all()
    else:
        rows = db.execute(select(m.Membership, m.User).join(m.User, m.User.id == m.Membership.user_id).where(m.Membership.tenant_id == ctx.tenant.id)).all()
    pa = {}
    for a in db.scalars(select(m.ProjectAssignment).where(m.ProjectAssignment.tenant_id == ctx.tenant.id)):
        pa.setdefault(a.membership_id, []).append(a.project_id)
    return [{"id": mem.id, "name": u.name, "email": u.email, "role": mem.role, "role_label": ROLE_LABELS[mem.role],
             "department_id": mem.department_id, "title": mem.title, "status": mem.status, "project_ids": pa.get(mem.id, [])} for mem, u in rows]


class MemberIn(BaseModel):
    name: str
    email: str
    role: str
    department_id: str | None = None
    project_ids: list[str] = []
    title: str | None = None
    password: str | None = None


@router.post("/members")
def add_member(body: MemberIn, bg: BackgroundTasks, ctx: Ctx = Depends(require("member.manage")), db=Depends(get_db)):
    allowed = PERSONAL_ROLES if ctx.tenant.edition == "personal" else BUSINESS_ROLES
    if body.role not in allowed:
        raise HTTPException(422, "Role is not available in this edition")
    if not EMAIL_RE.match(body.email):
        raise HTTPException(422, "Enter a valid email address")
    u = db.scalar(select(m.User).where(m.User.email == body.email.lower()))
    temp, invite_token = None, None
    if not u:
        if mail.configured():  # invitation by email: the person sets their own password, nobody ever sees one
            invite_token = secrets.token_urlsafe(24)
            u = m.User(email=body.email.lower(), name=body.name.strip(), password_hash=hash_password(secrets.token_hex(24)))
        else:
            temp = body.password or ("Temp-" + secrets.token_hex(4))
            check_password(temp)
            u = m.User(email=body.email.lower(), name=body.name.strip(), password_hash=hash_password(temp))
        db.add(u)
        db.flush()
        if invite_token:
            db.add(m.PasswordReset(token=invite_token, user_id=u.id, expires_at=m.now() + timedelta(days=7)))
    elif db.scalar(select(m.Membership.id).where(m.Membership.user_id == u.id, m.Membership.tenant_id == ctx.tenant.id)):
        raise HTTPException(409, "This person is already a member")
    if body.department_id and not db.scalar(select(m.Department.id).where(m.Department.id == body.department_id, m.Department.tenant_id == ctx.tenant.id)):
        raise HTTPException(422, "Unknown department")
    mem = m.Membership(user_id=u.id, tenant_id=ctx.tenant.id, role=body.role, department_id=body.department_id, title=body.title)
    db.add(mem)
    db.flush()
    for pid in body.project_ids:
        if not db.scalar(select(m.Project.id).where(m.Project.id == pid, m.Project.tenant_id == ctx.tenant.id)):
            raise HTTPException(422, "Unknown project")
        db.add(m.ProjectAssignment(tenant_id=ctx.tenant.id, membership_id=mem.id, project_id=pid, is_manager=body.role == "project_manager"))
    audit(db, ctx, "membership", mem.id, "invited", {"email": u.email, "role": body.role})
    db.commit()
    if invite_token:
        subject, text = mail.invite_email(u.name, ctx.tenant.name, invite_token)
        bg.add_task(mail.send, u.email, subject, text)
        return {"id": mem.id, "temporary_password": None, "invite_emailed": True, "note": f"An invitation email is on its way to {u.email}."}
    return {"id": mem.id, "temporary_password": temp, "invite_emailed": False, "note": "Share the temporary password securely; it is shown only once."}


class MemberPatch(BaseModel):
    role: str | None = None
    department_id: str | None = None
    project_ids: list[str] | None = None
    status: str | None = None


@router.patch("/members/{mid}")
def patch_member(mid: str, body: MemberPatch, ctx: Ctx = Depends(require("member.manage")), db=Depends(get_db)):
    mem = db.scalar(select(m.Membership).where(m.Membership.id == mid, m.Membership.tenant_id == ctx.tenant.id))
    if not mem:
        raise HTTPException(404, "Member not found")
    if body.role:
        mem.role = body.role
    if body.department_id is not None:
        mem.department_id = body.department_id or None
    if body.status:
        mem.status = body.status
    if body.project_ids is not None:
        for a in db.scalars(select(m.ProjectAssignment).where(m.ProjectAssignment.membership_id == mid)):
            db.delete(a)
        for pid in body.project_ids:
            db.add(m.ProjectAssignment(tenant_id=ctx.tenant.id, membership_id=mid, project_id=pid, is_manager=mem.role == "project_manager"))
    audit(db, ctx, "membership", mid, "updated", body.model_dump(exclude_none=True))
    db.commit()
    return {"ok": True}


# ---------------- notifications ----------------
@router.get("/notifications")
def notifications(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    rows = db.scalars(select(m.Notification).where(m.Notification.tenant_id == ctx.tenant.id, m.Notification.user_id == ctx.user.id)
                      .order_by(m.Notification.created_at.desc()).limit(50))
    prefs = ctx.membership.notif_prefs or {}
    return {"items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "read": n.read, "at": n.created_at.isoformat()}
                      for n in rows if prefs.get(n.kind, True)],
            "preferences": {k: prefs.get(k, True) for k in ("budget_alert", "approval", "rejected", "reimbursement", "reminder", "summary")}}


@router.post("/notifications/read")
def mark_read(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    for n in db.scalars(select(m.Notification).where(m.Notification.tenant_id == ctx.tenant.id, m.Notification.user_id == ctx.user.id, m.Notification.read.is_(False))):
        n.read = True
    db.commit()
    return {"ok": True}


@router.put("/notifications/preferences")
def set_prefs(body: dict, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    ctx.membership.notif_prefs = {k: bool(v) for k, v in body.items()}
    db.commit()
    return {"ok": True}


@router.get("/demo/accounts")
def demo_accounts(db=Depends(get_db)):
    """Demo environment only: lists the synthetic demo personas so a reviewer can browse. Never available in production."""
    if ENV != "demo":
        raise HTTPException(404, "Not found")
    from ..seed import DEMO_PASSWORD, DOMAIN
    rows = db.execute(select(m.User, m.Membership, m.Tenant).outerjoin(m.Membership, m.Membership.user_id == m.User.id)
                      .outerjoin(m.Tenant, m.Tenant.id == m.Membership.tenant_id).where(m.User.email.like("%" + DOMAIN)).order_by(m.Tenant.name, m.User.name)).all()
    return {"password_hint": DEMO_PASSWORD, "accounts": [{"email": u.email, "name": u.name, "tenant": t.name if t else "Platform",
                                                          "role": ROLE_LABELS.get(mem.role, "Platform Administrator") if mem else "Platform Administrator"} for u, mem, t in rows]}


@router.get("/templates")
def templates():
    return [{"code": k, "label": v["label"], "edition": v["edition"]} for k, v in TEMPLATES.items()]
