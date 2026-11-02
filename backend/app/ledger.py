"""The shared financial engine used by every edition: visibility scoping, balances, allocations,
budget utilisation and alerts, approval routing. All amounts are integer minor units."""
from collections import defaultdict, namedtuple
from datetime import date

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as DbSession

from . import models as m
from .core import COUNTED, Ctx, audit

T = m.Transaction
CREDIT = ("refund", "reimbursement")  # money coming back that reduces net expense


def visible_filter(ctx: Ctx):
    """Row-level authorization for transactions, used by lists, dashboards, reports, exports AND the AI layer."""
    base = T.tenant_id == ctx.tenant.id
    if ctx.can("scope.all"):
        return base
    me = ctx.membership
    conds = []
    if ctx.can("scope.own"):
        conds += [T.created_by == me.id, T.member_id == me.id]
    if ctx.can("scope.shared"):
        conds.append(T.shared.is_(True))
    if ctx.can("scope.department") and me.department_id:
        conds.append(T.department_id == me.department_id)
    if ctx.can("scope.project") and ctx.project_ids:
        conds.append(T.project_id.in_(ctx.project_ids))
    return and_(base, or_(*conds)) if conds else and_(base, T.id == "__none__")


def get_visible_txn(db: DbSession, ctx: Ctx, txn_id: str) -> m.Transaction:
    t = db.scalar(select(T).where(T.id == txn_id, visible_filter(ctx)))
    if not t:
        raise HTTPException(404, "Transaction not found")  # same answer whether it exists or is hidden
    return t


def delta(t: m.Transaction, account_id: str) -> int:
    """Effect of one counted transaction on one account balance."""
    if t.status not in COUNTED:
        return 0
    a = t.amount_minor
    if t.type in ("income",) or t.type in CREDIT:
        return a if t.account_id == account_id else 0
    if t.type == "expense":
        return -a if t.account_id == account_id else 0
    if t.type == "transfer":
        d = 0
        if t.account_id == account_id:
            d -= a
        if t.to_account_id == account_id:
            d += a
        return d
    return 0


def account_balances(db: DbSession, tenant_id: str) -> dict[str, int]:
    accts = list(db.scalars(select(m.Account).where(m.Account.tenant_id == tenant_id)))
    bal = {a.id: a.opening_minor for a in accts}
    for t in db.scalars(select(T).where(T.tenant_id == tenant_id, T.status.in_(COUNTED))):
        for aid in {t.account_id, t.to_account_id}:
            if aid in bal:
                bal[aid] += delta(t, aid)
    return bal


def month_bounds(period: str) -> tuple[date, date]:
    y, mth = int(period[:4]), int(period[5:7])
    start = date(y, mth, 1)
    end = date(y + (mth == 12), 1 if mth == 12 else mth + 1, 1)
    return start, end


Light = namedtuple("Light", "id type category_id department_id project_id dimensions date amount_minor")


def _cache(ctx: Ctx) -> dict:
    return ctx.__dict__.setdefault("_cache", {})


def allocations(db: DbSession, ctx: Ctx, start: date | None = None, end: date | None = None):
    """Yield (row, department_id, project_id, signed_minor) for counted expense-side movements.
    Splits replace the transaction's own dimensions, and always sum to the original amount.
    Rows are light column tuples (not ORM objects) and cached for the duration of one request."""
    key = ("alloc", start, end)
    c = _cache(ctx)
    if key not in c:
        base = [visible_filter(ctx), T.status.in_(COUNTED), T.type.in_(("expense",) + CREDIT)]
        if start:
            base.append(T.date >= start)
        if end:
            base.append(T.date < end)
        rows = [Light(*r) for r in db.execute(select(T.id, T.type, T.category_id, T.department_id, T.project_id, T.dimensions, T.date, T.amount_minor).where(*base))]
        splits = defaultdict(list)
        if rows:
            for tid, dep, prj, amt in db.execute(select(m.TransactionSplit.transaction_id, m.TransactionSplit.department_id, m.TransactionSplit.project_id, m.TransactionSplit.amount_minor)
                                                 .join(T, T.id == m.TransactionSplit.transaction_id).where(*base)):
                splits[tid].append((dep, prj, amt))
        out = []
        for t in rows:
            sign = -1 if t.type in CREDIT else 1
            parts = splits.get(t.id)
            if parts and all(d or p for d, p, _ in parts):  # project/department allocations; family-member shares do not change the cost dimensions
                out += [(t, d, p, sign * a) for d, p, a in parts]
            else:
                out.append((t, t.department_id, t.project_id, sign * t.amount_minor))
        c[key] = out
    return iter(c[key])


def totals(db: DbSession, ctx: Ctx, start: date, end: date) -> dict:
    key = ("totals", start, end)
    c = _cache(ctx)
    if key not in c:
        agg = dict(db.execute(select(T.type, func.coalesce(func.sum(T.amount_minor), 0)).where(visible_filter(ctx), T.status.in_(COUNTED), T.date >= start, T.date < end).group_by(T.type)).all())
        inc, exp = int(agg.get("income", 0)), int(agg.get("expense", 0))
        ref = int(sum(v for k, v in agg.items() if k in CREDIT))
        net = exp - ref
        c[key] = {"income": inc, "expense_gross": exp, "refunds": ref, "expense": net, "savings": inc - net,
                  "savings_rate": round((inc - net) / inc * 100, 1) if inc else None}
    return c[key]


# ---------------- budgets ----------------
def budget_actual(db: DbSession, ctx: Ctx, b: m.Budget) -> int:
    start, end = month_bounds(b.period)
    cat_ids = None
    if b.scope == "category":
        key = ("catfamily", b.scope_id)
        c = _cache(ctx)
        if key not in c:
            c[key] = {b.scope_id, *db.scalars(select(m.Category.id).where(m.Category.parent_id == b.scope_id))}
        cat_ids = c[key]
    total = 0
    for t, dep, prj, amt in allocations(db, ctx, start, end):
        if cat_ids is not None and t.category_id not in cat_ids:
            continue
        if b.scope == "department" and dep != b.scope_id:
            continue
        if b.scope == "project" and prj != b.scope_id:
            continue
        if b.scope == "dimension" and (t.dimensions or {}).get(b.dimension_id) != b.scope_id:
            continue
        total += amt
    return total


def budget_status(db: DbSession, ctx: Ctx, b: m.Budget) -> dict:
    actual = budget_actual(db, ctx, b)
    pct = round(actual / b.amount_minor * 100, 1) if b.amount_minor else 0
    return {"id": b.id, "name": b.name, "scope": b.scope, "scope_id": b.scope_id, "dimension_id": b.dimension_id,
            "period": b.period, "budget_minor": b.amount_minor, "actual_minor": actual,
            "variance_minor": b.amount_minor - actual, "utilization": pct, "thresholds": b.thresholds}


def visible_budgets(db: DbSession, ctx: Ctx, period: str | None = None):
    q = select(m.Budget).where(m.Budget.tenant_id == ctx.tenant.id)
    if period:
        q = q.where(m.Budget.period == period)
    out = []
    for b in db.scalars(q.order_by(m.Budget.name)):
        if not ctx.can("scope.all"):
            ok = (b.scope == "department" and ctx.can("scope.department") and b.scope_id == ctx.membership.department_id) or \
                 (b.scope == "project" and ctx.can("scope.project") and b.scope_id in ctx.project_ids) or \
                 (b.scope in ("category", "overall") and ctx.tenant.edition == "personal")
            if not ok:
                continue
        out.append(b)
    return out


def evaluate_budget_alerts(db: DbSession, tenant: m.Tenant, admin_ctx_factory) -> int:
    """Create one notification per budget per threshold crossed (deduplicated by key)."""
    created = 0
    _cache(admin_ctx_factory()).clear()  # data just changed: never reuse figures cached earlier in this request
    watchers = [mem for mem in db.scalars(select(m.Membership).where(m.Membership.tenant_id == tenant.id, m.Membership.status == "active"))
                if mem.role in ("owner", "org_admin", "finance_manager")]
    for b in db.scalars(select(m.Budget).where(m.Budget.tenant_id == tenant.id)):
        ctx = admin_ctx_factory()
        st = budget_status(db, ctx, b)
        for th in sorted(b.thresholds or []):
            if st["utilization"] >= th:
                for w in watchers:
                    key = f"budget:{b.id}:{th}"
                    exists = db.scalar(select(m.Notification.id).where(m.Notification.tenant_id == tenant.id,
                                                                       m.Notification.user_id == w.user_id,
                                                                       m.Notification.dedupe_key == key))
                    if not exists:
                        db.add(m.Notification(tenant_id=tenant.id, user_id=w.user_id, kind="budget_alert", dedupe_key=key,
                                              title=f"{b.name} has reached {th}% of its budget",
                                              body=f"{st['utilization']}% used ({st['actual_minor'] / 100:,.2f} of {b.amount_minor / 100:,.2f})."))
                        created += 1
    return created


# ---------------- approvals ----------------
def pick_policy(db: DbSession, t: m.Transaction) -> m.ApprovalPolicy | None:
    best = None
    for p in db.scalars(select(m.ApprovalPolicy).where(m.ApprovalPolicy.tenant_id == t.tenant_id, m.ApprovalPolicy.active.is_(True))):
        if t.amount_minor < p.min_minor or (p.max_minor is not None and t.amount_minor >= p.max_minor):
            continue
        if p.department_id and p.department_id != t.department_id:
            continue
        if p.project_id and p.project_id != t.project_id:
            continue
        specificity = (p.project_id is not None) * 2 + (p.department_id is not None)
        if best is None or specificity > best[0]:
            best = (specificity, p)
    return best[1] if best else None


def submit_for_approval(db: DbSession, ctx: Ctx, t: m.Transaction):
    pol = pick_policy(db, t)
    levels = list(pol.levels) if pol else ["finance"]
    for i, role in enumerate(levels, 1):
        db.add(m.ApprovalStep(tenant_id=t.tenant_id, transaction_id=t.id, level_no=i, role=role))
    t.status = "submitted"
    audit(db, ctx, "transaction", t.id, "submitted", {"policy": pol.name if pol else "default", "levels": levels})
    notify_approvers(db, t, levels[0])


def current_step(db: DbSession, txn_id: str) -> m.ApprovalStep | None:
    return db.scalar(select(m.ApprovalStep).where(m.ApprovalStep.transaction_id == txn_id, m.ApprovalStep.status == "pending")
                     .order_by(m.ApprovalStep.level_no))


def can_act_on_step(db: DbSession, ctx: Ctx, t: m.Transaction, step: m.ApprovalStep) -> bool:
    """Server-side rule: who may act on the step that is waiting?"""
    if t.created_by == ctx.membership.id:
        return False  # segregation of duties: nobody acts on their own claim
    if step.role == "project_manager":
        return (ctx.can("approve.project") and t.project_id in ctx.project_ids) or ctx.role == "org_admin"
    if step.role == "department_manager":
        return ctx.can("approve.department") and (t.department_id == ctx.membership.department_id or ctx.role == "org_admin")
    if step.role == "finance":
        return ctx.can("approve.finance")
    return False


def notify_approvers(db: DbSession, t: m.Transaction, role: str):
    mems = db.scalars(select(m.Membership).where(m.Membership.tenant_id == t.tenant_id, m.Membership.status == "active"))
    for mem in mems:
        hit = False
        if role == "project_manager" and mem.role == "project_manager":
            hit = db.scalar(select(m.ProjectAssignment.id).where(m.ProjectAssignment.membership_id == mem.id,
                                                                 m.ProjectAssignment.project_id == t.project_id)) is not None
        elif role == "department_manager" and mem.role == "department_manager":
            hit = mem.department_id == t.department_id
        elif role == "finance" and mem.role == "finance_manager":
            hit = True
        if hit:
            key = f"approval:{t.id}:{role}"
            if not db.scalar(select(m.Notification.id).where(m.Notification.tenant_id == t.tenant_id, m.Notification.user_id == mem.user_id,
                                                              m.Notification.dedupe_key == key)):
                db.add(m.Notification(tenant_id=t.tenant_id, user_id=mem.user_id, kind="approval", dedupe_key=key,
                                      title="Expense waiting for your approval",
                                      body=f"{t.description} - {t.amount_minor / 100:,.2f}"))


def route_after_pm_chain(db: DbSession, t: m.Transaction):
    nxt = current_step(db, t.id)
    if nxt is None:
        t.status = "verified"
    else:
        t.status = "pm_approved" if nxt.role == "finance" else "submitted"
        notify_approvers(db, t, nxt.role)
