import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from .. import ai
from .. import models as m
from ..core import COUNTED, STORAGE, Ctx, audit, fmt, get_db, require, tenant_ctx, to_minor
from ..ledger import (CREDIT, T, can_act_on_step, current_step, evaluate_budget_alerts, get_visible_txn, route_after_pm_chain,
                      submit_for_approval, visible_filter)

router = APIRouter(prefix="/api/v1", tags=["transactions"])


class Split(BaseModel):
    department_id: str | None = None
    project_id: str | None = None
    member_id: str | None = None
    amount: str | float


class TxIn(BaseModel):
    date: date
    type: str
    amount: str | float
    category_id: str | None = None
    subcategory_id: str | None = None
    description: str = ""
    merchant: str | None = None
    account_id: str | None = None
    to_account_id: str | None = None
    tags: list[str] = []
    department_id: str | None = None
    project_id: str | None = None
    cost_centre_id: str | None = None
    dimensions: dict = {}
    member_id: str | None = None
    shared: bool = False
    notes: str | None = None
    refund_of_id: str | None = None
    splits: list[Split] = []
    submit: bool = True
    allow_duplicate: bool = False
    ai: dict | None = None


def staff(ctx: Ctx) -> bool:
    return ctx.can("txn.edit_any")


def claim_mode(ctx: Ctx) -> bool:
    return ctx.tenant.edition == "business" and not staff(ctx)


def _own(db, model, tenant_id, id_, label):
    if id_ and not db.scalar(select(model.id).where(model.id == id_, model.tenant_id == tenant_id)):
        raise HTTPException(422, f"Unknown {label}")


def ser(t: m.Transaction, extra: dict | None = None) -> dict:
    d = {"id": t.id, "date": t.date.isoformat(), "type": t.type, "amount_minor": t.amount_minor, "amount": fmt(t.amount_minor), "currency": t.currency,
         "category_id": t.category_id, "subcategory_id": t.subcategory_id, "description": t.description, "merchant": t.merchant,
         "account_id": t.account_id, "to_account_id": t.to_account_id, "created_by": t.created_by, "member_id": t.member_id,
         "shared": t.shared, "tags": t.tags or [], "department_id": t.department_id, "project_id": t.project_id,
         "cost_centre_id": t.cost_centre_id, "dimensions": t.dimensions or {}, "status": t.status, "reimbursable": t.reimbursable,
         "refund_of_id": t.refund_of_id, "notes": t.notes, "ai_assisted": bool(t.ai), "sample": t.sample,
         "reject_reason": None}
    if extra:
        d.update(extra)
    return d


def validate_and_build(db, ctx: Ctx, b: TxIn, existing: m.Transaction | None = None) -> dict:
    tid = ctx.tenant.id
    if b.type not in ("income", "expense", "transfer", "refund", "reimbursement"):
        raise HTTPException(422, "Unknown transaction type")
    amount = to_minor(b.amount)
    if b.type in ("income", "transfer") and claim_mode(ctx):
        raise HTTPException(403, "You can record expenses only")
    if b.type == "transfer" and not (ctx.can("account.manage") or ctx.tenant.edition == "personal"):
        raise HTTPException(403, "You do not have permission to transfer between accounts")
    cat = None
    if b.type in ("income", "expense"):
        if not b.category_id:
            raise HTTPException(422, "Category is required")
        cat = db.scalar(select(m.Category).where(m.Category.id == b.category_id, m.Category.tenant_id == tid))
        if not cat or not cat.active:
            raise HTTPException(422, "Choose an active category")
        if cat.kind not in (b.type, "both"):
            raise HTTPException(422, f"{cat.name} cannot be used for {b.type}")
        for f in cat.required_fields or []:
            if not getattr(b, {"project": "project_id", "department": "department_id"}.get(f, f), None) and not (f == "description" and b.description):
                raise HTTPException(422, f"{cat.name} requires {f}")
    for acc in (b.account_id, b.to_account_id):
        if acc:
            a = db.scalar(select(m.Account).where(m.Account.id == acc, m.Account.tenant_id == tid))
            if not a or a.status != "active":
                raise HTTPException(422, "Choose an active account")
    if b.type == "transfer":
        if not b.account_id or not b.to_account_id or b.account_id == b.to_account_id:
            raise HTTPException(422, "A transfer needs two different accounts")
        ca = db.get(m.Account, b.account_id).currency
        if ca != db.get(m.Account, b.to_account_id).currency:
            raise HTTPException(422, "Transfers are between accounts of the same currency")
    elif not b.account_id and not claim_mode(ctx):
        raise HTTPException(422, "Payment account is required")
    _own(db, m.Department, tid, b.department_id, "department")
    _own(db, m.Project, tid, b.project_id, "project")
    _own(db, m.CostCentre, tid, b.cost_centre_id, "cost centre")
    if b.member_id and not db.scalar(select(m.Membership.id).where(m.Membership.id == b.member_id, m.Membership.tenant_id == tid)):
        raise HTTPException(422, "Unknown member")
    dims = {}
    for dim in db.scalars(select(m.Dimension).where(m.Dimension.tenant_id == tid, m.Dimension.active.is_(True))):
        v = (b.dimensions or {}).get(dim.id)
        if v:
            if not db.scalar(select(m.DimensionValue.id).where(m.DimensionValue.id == v, m.DimensionValue.dimension_id == dim.id, m.DimensionValue.active.is_(True))):
                raise HTTPException(422, f"Unknown {dim.name} value")
            dims[dim.id] = v
        elif dim.required and b.type == "expense":
            raise HTTPException(422, f"{dim.name} is required")
    if b.type == "expense" and ctx.tenant.edition == "business" and "project" in (ctx.tenant.config or {}).get("mandatory_fields", []) and not b.project_id:
        raise HTTPException(422, "Project is required for expenses in this organization")
    refund_of = None
    if b.type == "refund" or b.refund_of_id:
        if b.refund_of_id:
            orig = get_visible_txn(db, ctx, b.refund_of_id)
            if orig.type != "expense":
                raise HTTPException(422, "A refund can only be linked to an expense")
            done = db.scalar(select(func.coalesce(func.sum(T.amount_minor), 0)).where(T.refund_of_id == orig.id, T.type.in_(CREDIT),
                                                                                    T.id != (existing.id if existing else "")))
            if amount + done > orig.amount_minor:
                raise HTTPException(422, "Refunds cannot exceed the original expense")
            refund_of = orig.id
    splits = []
    if b.splits:
        tot = sum(to_minor(s.amount) for s in b.splits)
        if tot != amount:
            raise HTTPException(422, f"Allocations total {fmt(tot)} but the transaction is {fmt(amount)}; they must match exactly")
        for s in b.splits:
            _own(db, m.Department, tid, s.department_id, "department")
            _own(db, m.Project, tid, s.project_id, "project")
            _own(db, m.Membership, tid, s.member_id, "member")
            splits.append((s.department_id, s.project_id, to_minor(s.amount), s.member_id))
    dep = b.department_id or (ctx.membership.department_id if ctx.tenant.edition == "business" and b.type == "expense" else None)
    if not b.allow_duplicate and b.type in ("income", "expense") and not existing:
        dup = ai.find_duplicate(db, tid, b.date, amount, b.description, b.merchant)
        if dup:
            raise HTTPException(409, detail={"code": "DUPLICATE", "message": "This looks like a duplicate of an existing transaction.", "duplicate_of": dup.id})
    return {"amount": amount, "dep": dep, "splits": splits, "dims": dims, "refund_of": refund_of}


@router.post("/transactions")
def create_txn(b: TxIn, ctx: Ctx = Depends(require("txn.create")), db=Depends(get_db)):
    v = validate_and_build(db, ctx, b)
    me = ctx.membership.id
    claim = claim_mode(ctx) and b.type == "expense"
    t = m.Transaction(tenant_id=ctx.tenant.id, date=b.date, type=b.type, amount_minor=v["amount"], currency=ctx.tenant.currency, category_id=b.category_id,
                      subcategory_id=b.subcategory_id, description=b.description.strip(), merchant=b.merchant, account_id=b.account_id,
                      to_account_id=b.to_account_id, created_by=me, member_id=b.member_id or me, shared=b.shared, tags=b.tags,
                      cost_centre_id=b.cost_centre_id, department_id=v["dep"], project_id=b.project_id, dimensions=v["dims"],
                      reimbursable=claim, refund_of_id=v["refund_of"], notes=b.notes, ai=b.ai,
                      status="draft" if claim else "posted")
    t.seq = (db.scalar(select(func.max(T.seq)).where(T.tenant_id == ctx.tenant.id)) or 0) + 1
    db.add(t)
    db.flush()
    for d, p, a, mb in v["splits"]:
        db.add(m.TransactionSplit(tenant_id=ctx.tenant.id, transaction_id=t.id, department_id=d, project_id=p, member_id=mb, amount_minor=a))
    audit(db, ctx, "transaction", t.id, "created", {"type": t.type, "amount": fmt(t.amount_minor), "ai_assisted": bool(b.ai)})
    if claim and b.submit:
        submit_for_approval(db, ctx, t)
    if t.status in COUNTED:
        evaluate_budget_alerts(db, ctx.tenant, lambda: ctx)
    db.commit()
    return ser(t)


def _filters(q, ctx, p):
    if p.get("q"):
        like = f"%{p['q'].lower()}%"
        q = q.where(or_(func.lower(T.description).like(like), func.lower(func.coalesce(T.merchant, "")).like(like)))
    for k, col in (("type", T.type), ("category_id", T.category_id), ("account_id", T.account_id), ("member_id", T.member_id),
                   ("department_id", T.department_id), ("project_id", T.project_id), ("status", T.status)):
        if p.get(k):
            q = q.where(col == p[k])
    if p.get("date_from"):
        q = q.where(T.date >= p["date_from"])
    if p.get("date_to"):
        q = q.where(T.date <= p["date_to"])
    if p.get("mine"):
        q = q.where(T.created_by == ctx.membership.id)
    return q


def _params(q: str | None = None, type: str | None = None, category_id: str | None = None, account_id: str | None = None,
            member_id: str | None = None, department_id: str | None = None, project_id: str | None = None, status: str | None = None,
            date_from: date | None = None, date_to: date | None = None, mine: bool = False):
    return dict(q=q, type=type, category_id=category_id, account_id=account_id, member_id=member_id, department_id=department_id,
                project_id=project_id, status=status, date_from=date_from, date_to=date_to, mine=mine)


@router.get("/transactions")
def list_txns(p: dict = Depends(_params), page: int = 1, page_size: int = Query(25, le=200), ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    base = _filters(select(T).where(visible_filter(ctx)), ctx, p)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    inc = {"income": 0, "expense": 0}
    rows = list(db.scalars(base.order_by(T.date.desc(), T.seq.desc()).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [ser(t) for t in rows], "total": total, "page": page, "page_size": page_size}


def _safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@router.get("/transactions/export")
def export_csv(p: dict = Depends(_params), ctx: Ctx = Depends(require("txn.export")), db=Depends(get_db)):
    names = {c.id: c.name for c in db.scalars(select(m.Category).where(m.Category.tenant_id == ctx.tenant.id))}
    accts = {a.id: a.name for a in db.scalars(select(m.Account).where(m.Account.tenant_id == ctx.tenant.id))}
    projs = {a.id: a.name for a in db.scalars(select(m.Project).where(m.Project.tenant_id == ctx.tenant.id))}
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", "type", "amount", "currency", "category", "description", "merchant", "account", "project", "status"])
    for t in db.scalars(_filters(select(T).where(visible_filter(ctx)), ctx, p).order_by(T.date, T.seq)):
        w.writerow([t.date, t.type, fmt(t.amount_minor), t.currency, names.get(t.category_id, ""), _safe(t.description), _safe(t.merchant),
                    accts.get(t.account_id, ""), projs.get(t.project_id, ""), t.status])
    audit(db, ctx, "transaction", None, "exported", {})
    db.commit()
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=transactions.csv"})


@router.get("/transactions/{tid}")
def get_txn(tid: str, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    t = get_visible_txn(db, ctx, tid)
    steps = list(db.scalars(select(m.ApprovalStep).where(m.ApprovalStep.transaction_id == tid).order_by(m.ApprovalStep.level_no, m.ApprovalStep.acted_at)))
    names = {x.id: x.user_id for x in db.scalars(select(m.Membership).where(m.Membership.tenant_id == ctx.tenant.id))}
    users = {u.id: u.name for u in db.scalars(select(m.User))}
    hist = db.scalars(select(m.AuditEvent).where(m.AuditEvent.entity == "transaction", m.AuditEvent.entity_id == tid, m.AuditEvent.tenant_id == ctx.tenant.id)
                      .order_by(m.AuditEvent.at))
    rej = next((s.reason for s in reversed(steps) if s.status == "rejected"), None)
    cur = current_step(db, tid)
    return ser(t, {
        "reject_reason": rej if t.status == "rejected" else None,
        "splits": [{"department_id": s.department_id, "project_id": s.project_id, "member_id": s.member_id, "amount": fmt(s.amount_minor)} for s in
                   db.scalars(select(m.TransactionSplit).where(m.TransactionSplit.transaction_id == tid))],
        "steps": [{"level": s.level_no, "role": s.role, "status": s.status, "reason": s.reason,
                   "by": users.get(names.get(s.acted_by)) if s.acted_by else None, "at": s.acted_at.isoformat() if s.acted_at else None} for s in steps],
        "history": [{"action": h.action, "by": h.actor_name, "at": h.at.isoformat(), "detail": h.detail} for h in hist],
        "attachments": [{"id": a.id, "filename": a.filename} for a in db.scalars(select(m.Attachment).where(m.Attachment.transaction_id == tid))],
        "can_act": bool(cur and ctx.membership and can_act_on_step(db, ctx, t, cur)),
        "ai": t.ai})


@router.patch("/transactions/{tid}")
def edit_txn(tid: str, b: TxIn, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    t = get_visible_txn(db, ctx, tid)
    own_open = t.created_by == ctx.membership.id and t.status in ("draft", "rejected", "posted") and (t.status != "posted" or ctx.tenant.edition == "personal")
    if not (staff(ctx) or own_open):
        raise HTTPException(403, "You cannot edit this transaction")
    if t.status in ("paid",) and not staff(ctx):
        raise HTTPException(403, "Paid claims are locked")
    v = validate_and_build(db, ctx, b, existing=t)
    before = ser(t)
    for k, val in (("date", b.date), ("type", b.type), ("amount_minor", v["amount"]), ("category_id", b.category_id), ("description", b.description.strip()),
                   ("merchant", b.merchant), ("account_id", b.account_id), ("to_account_id", b.to_account_id), ("tags", b.tags), ("shared", b.shared),
                   ("department_id", v["dep"] if v["dep"] else t.department_id), ("project_id", b.project_id), ("dimensions", v["dims"]),
                   ("notes", b.notes), ("refund_of_id", v["refund_of"])):
        setattr(t, k, val)
    if b.member_id:
        t.member_id = b.member_id
    for s in db.scalars(select(m.TransactionSplit).where(m.TransactionSplit.transaction_id == tid)):
        db.delete(s)
    for d, p, a, mb in v["splits"]:
        db.add(m.TransactionSplit(tenant_id=ctx.tenant.id, transaction_id=t.id, department_id=d, project_id=p, member_id=mb, amount_minor=a))
    if t.status == "rejected":
        t.status = "draft"
    after = ser(t)
    audit(db, ctx, "transaction", tid, "edited", {k: {"from": before[k], "to": after[k]} for k in after if k in before and before[k] != after[k] and k != "status"})
    if t.status in COUNTED:
        evaluate_budget_alerts(db, ctx.tenant, lambda: ctx)
    db.commit()
    return ser(t)


@router.delete("/transactions/{tid}")
def delete_txn(tid: str, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    t = get_visible_txn(db, ctx, tid)
    if not (ctx.can("txn.delete_any") or (t.created_by == ctx.membership.id and t.status in ("draft", "rejected"))):
        raise HTTPException(403, "You cannot delete this transaction")
    if db.scalar(select(T.id).where(T.refund_of_id == tid)):
        raise HTTPException(409, "Delete the linked refunds first")
    audit(db, ctx, "transaction", tid, "deleted", {"description": t.description, "amount": fmt(t.amount_minor)})
    for s in db.scalars(select(m.TransactionSplit).where(m.TransactionSplit.transaction_id == tid)):
        db.delete(s)
    for s in db.scalars(select(m.ApprovalStep).where(m.ApprovalStep.transaction_id == tid)):
        db.delete(s)
    for r in db.scalars(select(m.Reimbursement).where(m.Reimbursement.transaction_id == tid)):
        db.delete(r)
    db.delete(t)
    db.commit()
    return {"ok": True}


# ---------------- approvals and reimbursements ----------------
@router.post("/transactions/{tid}/submit")
def submit(tid: str, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    t = get_visible_txn(db, ctx, tid)
    if t.created_by != ctx.membership.id or t.status not in ("draft", "rejected") or not t.reimbursable:
        raise HTTPException(403, "Only the owner of a draft or rejected claim can submit it")
    submit_for_approval(db, ctx, t)
    db.commit()
    return ser(t)


class Act(BaseModel):
    comment: str | None = None
    reason: str | None = None
    account_id: str | None = None


def _step_for(db, ctx, tid):
    t = get_visible_txn(db, ctx, tid)
    st = current_step(db, tid)
    if not st or t.status not in ("submitted", "pm_approved"):
        raise HTTPException(409, "This expense is not waiting for approval")
    if not can_act_on_step(db, ctx, t, st):
        raise HTTPException(403, "You are not an approver for this expense at its current step")
    return t, st


@router.post("/transactions/{tid}/approve")
def approve(tid: str, b: Act, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    t, st = _step_for(db, ctx, tid)
    st.status, st.acted_by, st.acted_at, st.reason = "approved", ctx.membership.id, datetime.utcnow(), b.comment
    route_after_pm_chain(db, t)
    audit(db, ctx, "transaction", tid, "finance_verified" if st.role == "finance" else "approved", {"level": st.role})
    db.commit()
    return ser(t)


@router.post("/transactions/{tid}/reject")
def reject(tid: str, b: Act, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    t, st = _step_for(db, ctx, tid)
    if not (b.reason or "").strip():
        raise HTTPException(422, "A rejection reason is required")
    st.status, st.acted_by, st.acted_at, st.reason = "rejected", ctx.membership.id, datetime.utcnow(), b.reason.strip()
    for other in db.scalars(select(m.ApprovalStep).where(m.ApprovalStep.transaction_id == tid, m.ApprovalStep.status == "pending")):
        other.status = "skipped"
    t.status = "rejected"
    creator = db.get(m.Membership, t.created_by)
    if creator:
        db.add(m.Notification(tenant_id=t.tenant_id, user_id=creator.user_id, kind="rejected", dedupe_key=f"rejected:{t.id}:{datetime.utcnow().timestamp()}",
                              title="Your expense was rejected", body=f"{t.description}: {b.reason.strip()}"))
    audit(db, ctx, "transaction", tid, "rejected", {"reason": b.reason.strip(), "level": st.role})
    db.commit()
    return ser(t)


@router.post("/transactions/{tid}/pay")
def pay(tid: str, b: Act, ctx: Ctx = Depends(require("approve.finance")), db=Depends(get_db)):
    t = get_visible_txn(db, ctx, tid)
    if t.status != "verified" or not t.reimbursable:
        raise HTTPException(409, "Only finance-verified reimbursable expenses can be marked paid")
    if t.created_by == ctx.membership.id:
        raise HTTPException(403, "You cannot pay your own claim")
    a = db.scalar(select(m.Account).where(m.Account.id == b.account_id, m.Account.tenant_id == ctx.tenant.id, m.Account.status == "active")) if b.account_id else None
    if not a:
        raise HTTPException(422, "Choose the account the reimbursement was paid from")
    t.status, t.account_id = "paid", a.id
    rec = db.scalar(select(m.Reimbursement).where(m.Reimbursement.transaction_id == tid)) or m.Reimbursement(tenant_id=t.tenant_id, transaction_id=tid,
                                                                                                           employee_membership_id=t.created_by, amount_minor=t.amount_minor)
    rec.status, rec.paid_at, rec.paid_account_id, rec.paid_by = "paid", datetime.utcnow(), a.id, ctx.membership.id
    db.add(rec)
    creator = db.get(m.Membership, t.created_by)
    if creator:
        db.add(m.Notification(tenant_id=t.tenant_id, user_id=creator.user_id, kind="reimbursement", dedupe_key=f"paid:{t.id}",
                              title="Reimbursement paid", body=f"{t.description}: {fmt(t.amount_minor)}"))
    audit(db, ctx, "transaction", tid, "reimbursement_paid", {"account": a.name})
    evaluate_budget_alerts(db, ctx.tenant, lambda: ctx)
    db.commit()
    return ser(t)


@router.get("/approvals")
def approvals(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    out = []
    projs = {p.id: p.name for p in db.scalars(select(m.Project).where(m.Project.tenant_id == ctx.tenant.id))}
    mem_user = {mm.id: u.name for mm, u in db.execute(select(m.Membership, m.User).join(m.User, m.User.id == m.Membership.user_id).where(m.Membership.tenant_id == ctx.tenant.id))}
    for t in db.scalars(select(T).where(T.tenant_id == ctx.tenant.id, T.status.in_(("submitted", "pm_approved", "verified"))).order_by(T.date)):
        st = current_step(db, t.id)
        if t.status == "verified":
            actionable = ctx.can("approve.finance") and t.created_by != ctx.membership.id
            action = "pay"
        else:
            actionable = bool(st and can_act_on_step(db, ctx, t, st))
            action = "approve"
        if actionable:
            out.append(ser(t, {"action": action, "waiting_for": st.role if st else "payment", "employee": mem_user.get(t.created_by), "project_name": projs.get(t.project_id)}))
    return out


@router.get("/reimbursements")
def reimbursements(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    q = select(T).where(visible_filter(ctx), T.reimbursable.is_(True)).order_by(T.date.desc())
    mem_user = {mm.id: u.name for mm, u in db.execute(select(m.Membership, m.User).join(m.User, m.User.id == m.Membership.user_id).where(m.Membership.tenant_id == ctx.tenant.id))}
    items = [ser(t, {"employee": mem_user.get(t.created_by)}) for t in db.scalars(q)]
    pend = sum(i["amount_minor"] for i in items if i["status"] in ("submitted", "pm_approved", "verified"))
    return {"items": items, "pending_minor": pend, "paid_minor": sum(i["amount_minor"] for i in items if i["status"] == "paid")}


# ---------------- attachments ----------------
@router.post("/transactions/{tid}/attachments")
async def attach(tid: str, file: UploadFile = File(...), ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    t = get_visible_txn(db, ctx, tid)
    if not (staff(ctx) or t.created_by == ctx.membership.id):
        raise HTTPException(403, "You cannot add attachments here")
    return await _store(db, ctx, file, t.id)


async def _store(db, ctx, file: UploadFile, txn_id=None):
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "Files can be up to 5 MB")
    ok = {"image/jpeg", "image/png", "application/pdf"}
    if file.content_type not in ok or not (data[:4] in (b"%PDF", b"\x89PNG") or data[:3] == b"\xff\xd8\xff"):
        raise HTTPException(415, "Only JPG, PNG or PDF files are accepted")
    att = m.Attachment(tenant_id=ctx.tenant.id, transaction_id=txn_id, filename=(file.filename or "file")[:200], content_type=file.content_type,
                       size=len(data), path="", uploaded_by=ctx.membership.id)
    db.add(att)
    db.flush()
    folder = STORAGE / ctx.tenant.id
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / att.id
    p.write_bytes(data)
    att.path = str(p)
    db.commit()
    return {"id": att.id, "filename": att.filename, "_data": data}


@router.get("/attachments/{aid}")
def get_attachment(aid: str, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    a = db.scalar(select(m.Attachment).where(m.Attachment.id == aid, m.Attachment.tenant_id == ctx.tenant.id))
    if not a:
        raise HTTPException(404, "Not found")
    if a.transaction_id:
        get_visible_txn(db, ctx, a.transaction_id)
    elif a.uploaded_by != ctx.membership.id and not staff(ctx):
        raise HTTPException(404, "Not found")
    return FileResponse(a.path, media_type=a.content_type, filename=a.filename)


# ---------------- bulk import ----------------
@router.post("/transactions/import")
async def import_csv(commit: bool = False, file: UploadFile = File(...), ctx: Ctx = Depends(require("txn.import")), db=Depends(get_db)):
    text = (await file.read()).decode("utf-8-sig", "ignore")
    cats = {c.name.lower(): c for c in db.scalars(select(m.Category).where(m.Category.tenant_id == ctx.tenant.id))}
    accts = {a.name.lower(): a for a in db.scalars(select(m.Account).where(m.Account.tenant_id == ctx.tenant.id))}
    rows, created = [], 0
    for i, r in enumerate(csv.DictReader(io.StringIO(text)), 2):
        res = {"row": i, "status": "ok", "message": "", "data": r}
        try:
            c, a = cats.get((r.get("category") or "").lower()), accts.get((r.get("account") or "").lower())
            if not c and (r.get("type") or "expense") in ("income", "expense"):
                raise HTTPException(422, f"Unknown category '{r.get('category')}'")
            if not a:
                raise HTTPException(422, f"Unknown account '{r.get('account')}'")
            body = TxIn(date=date.fromisoformat((r.get("date") or "").strip()), type=(r.get("type") or "expense").strip(), amount=r.get("amount") or "",
                        category_id=c.id if c else None, description=r.get("description") or "", merchant=r.get("merchant") or None, account_id=a.id)
            v = validate_and_build(db, ctx, body)
            if commit:
                t = m.Transaction(tenant_id=ctx.tenant.id, date=body.date, type=body.type, amount_minor=v["amount"], currency=ctx.tenant.currency,
                                  category_id=body.category_id, description=body.description, merchant=body.merchant, account_id=a.id,
                                  created_by=ctx.membership.id, member_id=ctx.membership.id, department_id=v["dep"], status="posted")
                db.add(t)
                created += 1
        except HTTPException as e:
            d = e.detail
            res["status"] = "duplicate" if isinstance(d, dict) and d.get("code") == "DUPLICATE" else "error"
            res["message"] = d["message"] if isinstance(d, dict) else str(d)
        except ValueError:
            res["status"], res["message"] = "error", "Invalid date (use YYYY-MM-DD)"
        res.pop("data")
        rows.append(res)
    if commit:
        audit(db, ctx, "transaction", None, "imported", {"created": created})
        db.commit()
    return {"rows": rows, "ok": sum(r["status"] == "ok" for r in rows), "skipped": sum(r["status"] != "ok" for r in rows), "created": created}
