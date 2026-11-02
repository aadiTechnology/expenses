from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from .. import models as m
from ..core import Ctx, audit, fmt, get_db, require, require_module, tenant_ctx, to_minor
from ..ledger import account_balances, budget_status, evaluate_budget_alerts, visible_budgets

router = APIRouter(prefix="/api/v1", tags=["configuration"])


def one(db, model, ctx, id_):
    o = db.scalar(select(model).where(model.id == id_, model.tenant_id == ctx.tenant.id))
    if not o:
        raise HTTPException(404, "Not found")
    return o


# ---------------- accounts ----------------
class AccountIn(BaseModel):
    name: str
    type: str
    opening: str | float = 0
    status: str = "active"


@router.get("/accounts")
def accounts(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    bal = account_balances(db, ctx.tenant.id)
    return [{"id": a.id, "name": a.name, "type": a.type, "currency": a.currency, "status": a.status, "opening_minor": a.opening_minor,
             "balance_minor": bal.get(a.id, 0)} for a in db.scalars(select(m.Account).where(m.Account.tenant_id == ctx.tenant.id).order_by(m.Account.name))
            if ctx.can("account.manage") or ctx.tenant.edition == "personal" or a.status == "active"]


@router.post("/accounts")
def add_account(b: AccountIn, ctx: Ctx = Depends(require("account.manage")), db=Depends(get_db)):
    if b.type not in ("cash", "bank", "upi", "credit_card", "wallet", "petty_cash", "other"):
        raise HTTPException(422, "Unknown account type")
    opening = to_minor(b.opening) if str(b.opening) not in ("0", "0.0", "") else 0
    a = m.Account(tenant_id=ctx.tenant.id, name=b.name.strip(), type=b.type, currency=ctx.tenant.currency, opening_minor=opening)
    db.add(a)
    db.flush()
    audit(db, ctx, "account", a.id, "created", {"name": a.name})
    db.commit()
    return {"id": a.id}


@router.patch("/accounts/{aid}")
def edit_account(aid: str, b: AccountIn, ctx: Ctx = Depends(require("account.manage")), db=Depends(get_db)):
    a = one(db, m.Account, ctx, aid)
    a.name, a.status = b.name.strip(), b.status
    audit(db, ctx, "account", aid, "updated", {"status": b.status})
    db.commit()
    return {"ok": True}


# ---------------- categories ----------------
class CategoryIn(BaseModel):
    name: str
    kind: str = "expense"
    parent_id: str | None = None
    icon: str = "label"
    color: str = "#5c6bc0"
    active: bool = True
    required_fields: list[str] = []


@router.get("/categories")
def categories(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    return [{"id": c.id, "name": c.name, "kind": c.kind, "parent_id": c.parent_id, "icon": c.icon, "color": c.color, "active": c.active,
             "required_fields": c.required_fields or []} for c in db.scalars(select(m.Category).where(m.Category.tenant_id == ctx.tenant.id).order_by(m.Category.name))]


@router.post("/categories")
def add_category(b: CategoryIn, ctx: Ctx = Depends(require("config.manage")), db=Depends(get_db)):
    if b.kind not in ("expense", "income", "both"):
        raise HTTPException(422, "Kind must be expense, income or both")
    if db.scalar(select(m.Category.id).where(m.Category.tenant_id == ctx.tenant.id, m.Category.name == b.name.strip(), m.Category.parent_id == b.parent_id)):
        raise HTTPException(409, "A category with this name already exists")
    c = m.Category(tenant_id=ctx.tenant.id, **b.model_dump(exclude={"name"}), name=b.name.strip())
    db.add(c)
    db.flush()
    audit(db, ctx, "category", c.id, "created", {"name": c.name})
    db.commit()
    return {"id": c.id}


@router.patch("/categories/{cid}")
def edit_category(cid: str, b: CategoryIn, ctx: Ctx = Depends(require("config.manage")), db=Depends(get_db)):
    c = one(db, m.Category, ctx, cid)
    for k, v in b.model_dump(exclude={"parent_id"}).items():
        setattr(c, k, v)
    audit(db, ctx, "category", cid, "updated", b.model_dump())
    db.commit()
    return {"ok": True}


# ---------------- departments, projects, cost centres ----------------
class NameIn(BaseModel):
    name: str
    department_id: str | None = None
    active: bool = True


@router.get("/departments")
def departments(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    return [{"id": d.id, "name": d.name, "active": d.active} for d in db.scalars(select(m.Department).where(m.Department.tenant_id == ctx.tenant.id).order_by(m.Department.name))]


@router.post("/departments")
def add_department(b: NameIn, ctx: Ctx = Depends(require("config.manage")), db=Depends(get_db)):
    d = m.Department(tenant_id=ctx.tenant.id, name=b.name.strip())
    db.add(d)
    db.flush()
    audit(db, ctx, "department", d.id, "created", {"name": d.name})
    db.commit()
    return {"id": d.id}


@router.get("/projects")
def projects(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    q = select(m.Project).where(m.Project.tenant_id == ctx.tenant.id).order_by(m.Project.name)
    return [{"id": p.id, "name": p.name, "department_id": p.department_id, "active": p.active} for p in db.scalars(q)]


@router.post("/projects")
def add_project(b: NameIn, ctx: Ctx = Depends(require("config.manage")), db=Depends(get_db)):
    p = m.Project(tenant_id=ctx.tenant.id, name=b.name.strip(), department_id=b.department_id)
    db.add(p)
    db.flush()
    audit(db, ctx, "project", p.id, "created", {"name": p.name})
    db.commit()
    return {"id": p.id}


@router.patch("/projects/{pid}")
def edit_project(pid: str, b: NameIn, ctx: Ctx = Depends(require("config.manage")), db=Depends(get_db)):
    p = one(db, m.Project, ctx, pid)
    p.name, p.active = b.name.strip(), b.active
    audit(db, ctx, "project", pid, "updated", b.model_dump())
    db.commit()
    return {"ok": True}


# ---------------- growth dimensions (Pillar 2) ----------------
class DimIn(BaseModel):
    key: str
    name: str
    required: bool = False


class ValueIn(BaseModel):
    name: str


@router.get("/dimensions")
def dimensions(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    from ..core import effective_entitlements
    if not effective_entitlements(db, ctx.tenant).get("growth_dimensions", {}).get("enabled"):
        return []
    out = []
    for d in db.scalars(select(m.Dimension).where(m.Dimension.tenant_id == ctx.tenant.id, m.Dimension.active.is_(True))):
        vals = db.scalars(select(m.DimensionValue).where(m.DimensionValue.dimension_id == d.id, m.DimensionValue.active.is_(True)).order_by(m.DimensionValue.name))
        out.append({"id": d.id, "key": d.key, "name": d.name, "required": d.required, "values": [{"id": v.id, "name": v.name} for v in vals]})
    return out


@router.post("/dimensions")
def add_dimension(b: DimIn, ctx: Ctx = Depends(require_module("growth_dimensions")), db=Depends(get_db)):
    if "config.manage" not in ctx.perms:
        raise HTTPException(403, "You do not have permission for this action")
    d = m.Dimension(tenant_id=ctx.tenant.id, key=b.key.strip().lower(), name=b.name.strip(), required=b.required, pillar="P2")
    db.add(d)
    db.flush()
    audit(db, ctx, "dimension", d.id, "created", {"name": d.name, "required": d.required})
    db.commit()
    return {"id": d.id}


@router.post("/dimensions/{did}/values")
def add_value(did: str, b: ValueIn, ctx: Ctx = Depends(require_module("growth_dimensions")), db=Depends(get_db)):
    if "config.manage" not in ctx.perms:
        raise HTTPException(403, "You do not have permission for this action")
    d = one(db, m.Dimension, ctx, did)
    v = m.DimensionValue(tenant_id=ctx.tenant.id, dimension_id=d.id, name=b.name.strip())
    db.add(v)
    db.flush()
    audit(db, ctx, "dimension_value", v.id, "created", {"dimension": d.name, "name": v.name})
    db.commit()
    return {"id": v.id}


@router.delete("/dimensions/values/{vid}")
def disable_value(vid: str, ctx: Ctx = Depends(require_module("growth_dimensions")), db=Depends(get_db)):
    if "config.manage" not in ctx.perms:
        raise HTTPException(403, "You do not have permission for this action")
    v = one(db, m.DimensionValue, ctx, vid)
    v.active = False
    audit(db, ctx, "dimension_value", vid, "disabled", {"name": v.name})
    db.commit()
    return {"ok": True}


# ---------------- budgets ----------------
class BudgetIn(BaseModel):
    name: str
    scope: str
    scope_id: str | None = None
    dimension_id: str | None = None
    period: str
    amount: str | float
    thresholds: list[int] = [50, 75, 90, 100]


@router.get("/budgets")
def budgets(period: str | None = None, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    return [budget_status(db, ctx, b) for b in visible_budgets(db, ctx, period)]


@router.post("/budgets")
def add_budget(b: BudgetIn, ctx: Ctx = Depends(require("budget.manage")), db=Depends(get_db)):
    if b.scope not in ("overall", "department", "project", "category", "dimension"):
        raise HTTPException(422, "Unknown budget scope")
    if len(b.period) != 7 or b.period[4] != "-":
        raise HTTPException(422, "Period must look like 2026-10")
    if b.scope == "dimension":
        from ..core import effective_entitlements
        if not effective_entitlements(db, ctx.tenant).get("growth_spend", {}).get("enabled"):
            raise HTTPException(403, detail={"code": "ENTITLEMENT_DENIED", "message": "This feature is not available for your subscription."})
    if any(not (1 <= t <= 200) for t in b.thresholds):
        raise HTTPException(422, "Thresholds are percentages between 1 and 200")
    row = m.Budget(tenant_id=ctx.tenant.id, name=b.name.strip(), scope=b.scope, scope_id=b.scope_id, dimension_id=b.dimension_id, period=b.period,
                   amount_minor=to_minor(b.amount), thresholds=sorted(set(b.thresholds)))
    db.add(row)
    db.flush()
    audit(db, ctx, "budget", row.id, "created", {"name": row.name, "amount": fmt(row.amount_minor), "period": row.period})
    evaluate_budget_alerts(db, ctx.tenant, lambda: ctx)
    db.commit()
    return {"id": row.id}


@router.delete("/budgets/{bid}")
def del_budget(bid: str, ctx: Ctx = Depends(require("budget.manage")), db=Depends(get_db)):
    row = one(db, m.Budget, ctx, bid)
    audit(db, ctx, "budget", bid, "deleted", {"name": row.name})
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------------- savings goals ----------------
class GoalIn(BaseModel):
    name: str
    target: str | float
    saved: str | float = 0
    target_date: date | None = None


@router.get("/goals")
def goals(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    return [{"id": g.id, "name": g.name, "target_minor": g.target_minor, "saved_minor": g.saved_minor, "target_date": g.target_date.isoformat() if g.target_date else None}
            for g in db.scalars(select(m.SavingsGoal).where(m.SavingsGoal.tenant_id == ctx.tenant.id))]


@router.post("/goals")
def add_goal(b: GoalIn, ctx: Ctx = Depends(require("goals.manage")), db=Depends(get_db)):
    g = m.SavingsGoal(tenant_id=ctx.tenant.id, name=b.name.strip(), target_minor=to_minor(b.target),
                      saved_minor=to_minor(b.saved) if str(b.saved) not in ("0", "") else 0, target_date=b.target_date)
    db.add(g)
    db.flush()
    audit(db, ctx, "goal", g.id, "created", {"name": g.name})
    db.commit()
    return {"id": g.id}


# ---------------- approval policies, audit ----------------
@router.get("/policies")
def policies(ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    return [{"id": p.id, "name": p.name, "min_minor": p.min_minor, "max_minor": p.max_minor, "levels": p.levels, "department_id": p.department_id,
             "project_id": p.project_id} for p in db.scalars(select(m.ApprovalPolicy).where(m.ApprovalPolicy.tenant_id == ctx.tenant.id))]


class PolicyIn(BaseModel):
    name: str
    min_amount: str | float = 0
    max_amount: str | float | None = None
    levels: list[str]
    department_id: str | None = None
    project_id: str | None = None


@router.post("/policies")
def add_policy(b: PolicyIn, ctx: Ctx = Depends(require("config.manage")), db=Depends(get_db)):
    if not b.levels or any(l not in ("project_manager", "department_manager", "finance") for l in b.levels):
        raise HTTPException(422, "Levels must be project_manager, department_manager or finance")
    p = m.ApprovalPolicy(tenant_id=ctx.tenant.id, name=b.name, min_minor=to_minor(b.min_amount) if str(b.min_amount) not in ("0", "") else 0,
                         max_minor=to_minor(b.max_amount) if b.max_amount else None, levels=b.levels, department_id=b.department_id, project_id=b.project_id)
    db.add(p)
    db.flush()
    audit(db, ctx, "policy", p.id, "created", {"name": b.name, "levels": b.levels})
    db.commit()
    return {"id": p.id}


@router.get("/audit")
def audit_log(entity: str | None = None, limit: int = 100, ctx: Ctx = Depends(require("audit.read")), db=Depends(get_db)):
    q = select(m.AuditEvent).where(m.AuditEvent.tenant_id == ctx.tenant.id).order_by(m.AuditEvent.at.desc()).limit(min(limit, 500))
    if entity:
        q = q.where(m.AuditEvent.entity == entity)
    return [{"id": a.id, "at": a.at.isoformat(), "actor": a.actor_name, "entity": a.entity, "entity_id": a.entity_id, "action": a.action, "detail": a.detail}
            for a in db.scalars(q)]
