import csv
import io
from collections import defaultdict
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from .. import ai
from .. import models as m
from ..core import COUNTED, Ctx, audit, effective_entitlements, fmt, get_db, require, require_module, tenant_ctx, to_minor
from ..ledger import (CREDIT, T, account_balances, allocations, budget_status, month_bounds, totals, visible_budgets, visible_filter)
from .txn import TxIn, _store, create_txn, ser

router = APIRouter(prefix="/api/v1", tags=["insight"])


def default_period(db, ctx) -> str:
    latest = db.scalar(select(T.date).where(visible_filter(ctx), T.status.in_(COUNTED)).order_by(T.date.desc()).limit(1))
    cur = date.today().strftime("%Y-%m")
    if latest and not db.scalar(select(T.id).where(visible_filter(ctx), T.status.in_(COUNTED), T.date >= month_bounds(cur)[0]).limit(1)):
        return latest.strftime("%Y-%m")
    return cur


def prev_period(p: str) -> str:
    y, mo = int(p[:4]), int(p[5:])
    return f"{y - 1}-12" if mo == 1 else f"{y}-{mo - 1:02d}"


def cat_rollup(db, ctx):
    cats = {c.id: c for c in db.scalars(select(m.Category).where(m.Category.tenant_id == ctx.tenant.id))}
    def top(cid):
        c = cats.get(cid)
        return cats[c.parent_id] if c and c.parent_id in cats else c
    return cats, top


# ---------------- dashboard ----------------
@router.get("/dashboard")
def dashboard(period: str | None = None, ctx: Ctx = Depends(tenant_ctx), db=Depends(get_db)):
    period = period or default_period(db, ctx)
    s, e = month_bounds(period)
    ent = effective_entitlements(db, ctx.tenant)
    widgets = ctx.tenant.config.get("dashboard_widgets", [])
    cats, top = cat_rollup(db, ctx)
    out = {"period": period, "widgets": [], "data": {}}
    tot = totals(db, ctx, s, e)
    prev = totals(db, ctx, *month_bounds(prev_period(period)))
    bal = account_balances(db, ctx.tenant.id)
    accts = {a.id: a for a in db.scalars(select(m.Account).where(m.Account.tenant_id == ctx.tenant.id))}
    available = sum(v for k, v in bal.items() if accts[k].type != "credit_card" and accts[k].status == "active")
    d = out["data"]
    if "kpis" in widgets:
        d["kpis"] = {**tot, "previous": prev, "available_balance": available if ctx.can("scope.all") else None,
                     "credit_outstanding": -sum(v for k, v in bal.items() if accts[k].type == "credit_card") if ctx.can("scope.all") else None}
    rows = list(allocations(db, ctx, s, e))
    if "category_spend" in widgets:
        agg = defaultdict(int)
        for t, _, _, a in rows:
            c = top(t.category_id)
            agg[(c.name, c.color) if c else ("Uncategorised", "#999999")] += a
        d["category_spend"] = [{"name": k[0], "color": k[1], "amount_minor": v} for k, v in sorted(agg.items(), key=lambda x: -x[1]) if v]
    if "department_spend" in widgets:
        names = {x.id: x.name for x in db.scalars(select(m.Department).where(m.Department.tenant_id == ctx.tenant.id))}
        agg = defaultdict(int)
        for _, dep, _, a in rows:
            agg[names.get(dep, "Unassigned")] += a
        d["department_spend"] = [{"name": k, "amount_minor": v} for k, v in sorted(agg.items(), key=lambda x: -x[1])]
    if "project_spend" in widgets:
        names = {x.id: x.name for x in db.scalars(select(m.Project).where(m.Project.tenant_id == ctx.tenant.id))}
        agg = defaultdict(int)
        for _, _, p, a in rows:
            agg[names.get(p, "No project")] += a
        d["project_spend"] = [{"name": k, "amount_minor": v} for k, v in sorted(agg.items(), key=lambda x: -x[1])]
    if "trend" in widgets:
        daily = defaultdict(int)
        for t, _, _, a in rows:
            daily[t.date.day] += a
        monthly = []
        p = period
        for _ in range(4):
            tt = totals(db, ctx, *month_bounds(p))
            monthly.append({"period": p, "income": tt["income"], "expense": tt["expense"]})
            p = prev_period(p)
        d["trend"] = {"daily": [{"day": k, "amount_minor": v} for k, v in sorted(daily.items())], "monthly": list(reversed(monthly))}
    if "recent" in widgets:
        d["recent"] = [ser(t) for t in db.scalars(select(T).where(visible_filter(ctx), T.status.in_(COUNTED)).order_by(T.date.desc(), T.seq.desc()).limit(8))]
    if "budgets" in widgets:
        d["budgets"] = [budget_status(db, ctx, b) for b in visible_budgets(db, ctx, period)][:8]
    if "pending" in widgets:
        q = select(T).where(visible_filter(ctx), T.status.in_(("submitted", "pm_approved", "verified")))
        pend = list(db.scalars(q))
        d["pending"] = {"approvals": sum(t.status in ("submitted", "pm_approved") for t in pend), "reimbursements": sum(t.status == "verified" for t in pend),
                        "amount_minor": sum(t.amount_minor for t in pend)}
    if "goals" in widgets:
        d["goals"] = [{"name": g.name, "target_minor": g.target_minor, "saved_minor": g.saved_minor} for g in db.scalars(select(m.SavingsGoal).where(m.SavingsGoal.tenant_id == ctx.tenant.id))]
    if "insights" in widgets and ent["ai_insights"]["enabled"] and ctx.can("ai.use"):
        d["insights"] = ai.insights(db, ctx)[:3]
    if "growth" in widgets and ent["growth_spend"]["enabled"] and ctx.can("growth.read"):
        d["growth"] = growth_rows(db, ctx, period)["rows"][:5]
    out["widgets"] = [w for w in widgets if w in d]
    return out


# ---------------- reports ----------------
def money_cols(*i):
    return list(i)


def build_report(db, ctx, name: str, period: str) -> dict:
    s, e = month_bounds(period)
    cats, top = cat_rollup(db, ctx)
    rows = list(allocations(db, ctx, s, e))
    if name == "monthly":
        r, p = [], period
        for _ in range(6):
            t = totals(db, ctx, *month_bounds(p))
            r.append([p, t["income"], t["expense"], t["savings"]])
            p = prev_period(p)
        return {"title": "Monthly income and expense", "columns": ["Month", "Income", "Expenses", "Difference"], "money": [1, 2, 3], "rows": list(reversed(r))}
    if name in ("category", "comparison"):
        cur, prv = defaultdict(int), defaultdict(int)
        for t, _, _, a in rows:
            cur[top(t.category_id).name if top(t.category_id) else "Uncategorised"] += a
        for t, _, _, a in allocations(db, ctx, *month_bounds(prev_period(period))):
            prv[top(t.category_id).name if top(t.category_id) else "Uncategorised"] += a
        names = sorted(set(cur) | set(prv), key=lambda n: -cur.get(n, 0))
        if name == "category":
            tot = sum(cur.values()) or 1
            return {"title": f"Category-wise expenses, {period}", "columns": ["Category", "Amount", "Share %"], "money": [1],
                    "rows": [[n, cur[n], round(cur[n] / tot * 100, 1)] for n in names if cur.get(n)]}
        return {"title": f"Monthly comparison, {prev_period(period)} vs {period}", "columns": ["Category", "Previous", "This month", "Change"], "money": [1, 2, 3],
                "rows": [[n, prv.get(n, 0), cur.get(n, 0), cur.get(n, 0) - prv.get(n, 0)] for n in names]}
    if name == "account":
        bal = account_balances(db, ctx.tenant.id)
        if not ctx.can("scope.all"):
            raise HTTPException(403, "You do not have permission for this report")
        return {"title": "Account-wise balances", "columns": ["Account", "Type", "Balance"], "money": [2],
                "rows": [[a.name, a.type, bal[a.id]] for a in db.scalars(select(m.Account).where(m.Account.tenant_id == ctx.tenant.id))]}
    if name in ("member", "contributions"):
        users = {mm.id: u.name for mm, u in db.execute(select(m.Membership, m.User).join(m.User, m.User.id == m.Membership.user_id).where(m.Membership.tenant_id == ctx.tenant.id))}
        splits = defaultdict(list)
        for sp in db.scalars(select(m.TransactionSplit).where(m.TransactionSplit.tenant_id == ctx.tenant.id)):
            splits[sp.transaction_id].append(sp)
        spent, shared_share, earned = defaultdict(int), defaultdict(int), defaultdict(int)
        for t in db.scalars(select(T).where(visible_filter(ctx), T.status.in_(COUNTED), T.date >= s, T.date < e)):
            if t.type == "income":
                earned[users.get(t.member_id, "Unassigned")] += t.amount_minor
            elif t.type in ("expense",) + CREDIT:
                sign = -1 if t.type in CREDIT else 1
                parts = [(sp.member_id or t.member_id, sp.amount_minor) for sp in splits.get(t.id, [])] or [(t.member_id, t.amount_minor)]
                for mb, amt in parts:
                    spent[users.get(mb, "Shared / unassigned")] += sign * amt
                    if t.shared:
                        shared_share[users.get(mb, "Shared / unassigned")] += sign * amt
        if name == "member":
            return {"title": f"Expenses by member, {period} (shared expenses use their allocation)", "columns": ["Member", "Amount"], "money": [1],
                    "rows": [[k, v] for k, v in sorted(spent.items(), key=lambda x: -x[1])]}
        names = sorted(set(earned) | set(shared_share))
        return {"title": f"Family contributions, {period}: income recorded vs share of shared expenses", "columns": ["Member", "Income contributed", "Share of shared expenses", "Difference"], "money": [1, 2, 3],
                "rows": [[n, earned.get(n, 0), shared_share.get(n, 0), earned.get(n, 0) - shared_share.get(n, 0)] for n in names]}
    if name in ("department", "project"):
        model = m.Department if name == "department" else m.Project
        names = {x.id: x.name for x in db.scalars(select(model).where(model.tenant_id == ctx.tenant.id))}
        agg = defaultdict(int)
        for _, dep, prj, a in rows:
            agg[names.get(dep if name == "department" else prj, "Unassigned")] += a
        bud = {}
        for b in visible_budgets(db, ctx, period):
            if b.scope == name:
                bud[names.get(b.scope_id)] = b.amount_minor
        return {"title": f"{name.title()} expenditure, {period}", "columns": [name.title(), "Actual", "Budget", "Variance"], "money": [1, 2, 3],
                "rows": [[k, v, bud.get(k), (bud[k] - v) if k in bud else None] for k, v in sorted(agg.items(), key=lambda x: -x[1])]}
    if name == "budget_vs_actual":
        return {"title": f"Budget vs actual, {period}", "columns": ["Budget", "Budgeted", "Actual", "Variance", "Used %"], "money": [1, 2, 3],
                "rows": [[x["name"], x["budget_minor"], x["actual_minor"], x["variance_minor"], x["utilization"]] for x in (budget_status(db, ctx, b) for b in visible_budgets(db, ctx, period))]}
    if name == "reimbursement":
        users = {mm.id: u.name for mm, u in db.execute(select(m.Membership, m.User).join(m.User, m.User.id == m.Membership.user_id).where(m.Membership.tenant_id == ctx.tenant.id))}
        agg = defaultdict(lambda: [0, 0])
        for t in db.scalars(select(T).where(visible_filter(ctx), T.reimbursable.is_(True))):
            agg[users.get(t.created_by, "?")][1 if t.status == "paid" else 0] += t.amount_minor if t.status in ("paid", "submitted", "pm_approved", "verified") else 0
        return {"title": "Employee reimbursements", "columns": ["Employee", "Pending", "Paid"], "money": [1, 2], "rows": [[k, v[0], v[1]] for k, v in agg.items()]}
    raise HTTPException(404, "Unknown report")


@router.get("/reports/{name}")
def report(name: str, period: str | None = None, format: str = "json", ctx: Ctx = Depends(require("report.read")), db=Depends(get_db)):
    period = period or default_period(db, ctx)
    r = build_report(db, ctx, name, period)
    r["period"] = period
    if format == "json":
        return r
    money = set(r.get("money", []))
    f = lambda i, v: ("" if v is None else fmt(v) if i in money else v)  # noqa: E731
    if format == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(r["columns"])
        for row in r["rows"]:
            w.writerow([f(i, v) for i, v in enumerate(row)])
        return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={name}-{period}.csv"})
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    buf = io.BytesIO()
    st = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    data = [r["columns"]] + [[str(f(i, v)) for i, v in enumerate(row)] for row in r["rows"]]
    tb = Table(data, repeatRows=1)
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3949ab")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]))
    doc.build([Paragraph(r["title"], st["Title"]), Paragraph(f"{ctx.tenant.name} - generated {datetime.now():%Y-%m-%d} - illustrative demo data" if ctx.tenant.is_demo else ctx.tenant.name, st["Normal"]), Spacer(1, 12), tb])
    return Response(buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={name}-{period}.pdf"})


# ---------------- AI ----------------
class ParseIn(BaseModel):
    text: str
    source: str = "voice"
    today: date | None = None  # the person's own local date, so "today" is right in any timezone


def _dups(db, ctx, items):
    for it in items:
        try:
            d = ai.find_duplicate(db, ctx.tenant.id, date.fromisoformat(it["date"]), to_minor(it["amount"]), it["description"], it.get("merchant")) if it.get("amount") else None
        except Exception:
            d = None
        it["duplicate_of"] = d.id if d else None
    return items


@router.post("/ai/parse")
def ai_parse(b: ParseIn, ctx: Ctx = Depends(require_module("ai_capture")), db=Depends(get_db)):
    if not ctx.can("ai.use"):
        raise HTTPException(403, "You do not have permission for this action")
    items = _dups(db, ctx, ai.parse_text(db, ctx.tenant.id, b.text, today=b.today, source="register" if b.source == "register" else "voice"))
    ext = m.AiExtraction(tenant_id=ctx.tenant.id, user_id=ctx.user.id, source_type=b.source, source_ref=b.text[:290], items=items)
    db.add(ext)
    db.flush()
    audit(db, ctx, "ai_extraction", ext.id, "suggested", {"source": b.source, "items": len(items)})
    db.commit()
    return {"extraction_id": ext.id, "engine": ai.ENGINE, "items": items, "notice": "AI suggestions - review each line before saving. Nothing has been recorded yet."}


@router.post("/ai/receipt")
async def ai_receipt(file: UploadFile = File(...), ctx: Ctx = Depends(require_module("ai_capture")), db=Depends(get_db)):
    if not ctx.can("ai.use"):
        raise HTTPException(403, "You do not have permission for this action")
    att = await _store(db, ctx, file)
    items = _dups(db, ctx, ai.extract_receipt(db, ctx.tenant.id, att["filename"], att.pop("_data")))
    ext = m.AiExtraction(tenant_id=ctx.tenant.id, user_id=ctx.user.id, source_type="receipt", source_ref=att["filename"], attachment_id=att["id"], items=items)
    db.add(ext)
    db.flush()
    audit(db, ctx, "ai_extraction", ext.id, "suggested", {"source": "receipt", "file": att["filename"]})
    db.commit()
    return {"extraction_id": ext.id, "engine": ai.ENGINE, "attachment_id": att["id"], "items": items, "notice": "Simulated extraction - confirm every value."}


class ConfirmIn(BaseModel):
    items: list[dict]
    account_id: str | None = None


@router.post("/ai/extractions/{eid}/confirm")
def ai_confirm(eid: str, b: ConfirmIn, ctx: Ctx = Depends(require_module("ai_capture")), db=Depends(get_db)):
    ext = db.scalar(select(m.AiExtraction).where(m.AiExtraction.id == eid, m.AiExtraction.tenant_id == ctx.tenant.id, m.AiExtraction.user_id == ctx.user.id))
    if not ext or ext.status != "pending":
        raise HTTPException(404, "Extraction not found or already handled")
    created = []
    for it in b.items:
        if not it.get("include", True):
            continue
        if it.get("needs_review") and not it.get("reviewed"):
            raise HTTPException(422, f"'{it.get('description')}' is low confidence - review and tick it before saving")
        body = TxIn(date=date.fromisoformat(it["date"]), type=it.get("type", "expense"), amount=it["amount"], category_id=it.get("category_id"),
                    description=it.get("description", ""), merchant=it.get("merchant"), account_id=it.get("account_id") or b.account_id,
                    project_id=it.get("project_id"), allow_duplicate=bool(it.get("allow_duplicate")),
                    ai={"extraction_id": ext.id, "engine": ai.ENGINE, "source": ext.source_type, "confidence": it.get("confidence"),
                        "attachment_id": ext.attachment_id, "confirmed_by": ctx.user.id, "confirmed_at": datetime.utcnow().isoformat()})
        res = create_txn(body, ctx, db)
        created.append(res["id"])
        if ext.attachment_id:
            att = db.get(m.Attachment, ext.attachment_id)
            if att and not att.transaction_id:
                att.transaction_id = res["id"]
    ext.status, ext.created_txn_ids = "confirmed", created
    audit(db, ctx, "ai_extraction", eid, "confirmed", {"created": len(created)})
    db.commit()
    return {"created": created}


@router.post("/ai/extractions/{eid}/discard")
def ai_discard(eid: str, ctx: Ctx = Depends(require_module("ai_capture")), db=Depends(get_db)):
    ext = db.scalar(select(m.AiExtraction).where(m.AiExtraction.id == eid, m.AiExtraction.tenant_id == ctx.tenant.id, m.AiExtraction.user_id == ctx.user.id))
    if ext:
        ext.status = "discarded"
        audit(db, ctx, "ai_extraction", eid, "discarded", {})
        db.commit()
    return {"ok": True}


@router.get("/ai/insights")
def ai_insights(ctx: Ctx = Depends(require_module("ai_insights")), db=Depends(get_db)):
    if not ctx.can("ai.use"):
        raise HTTPException(403, "You do not have permission for this action")
    items = ai.insights(db, ctx)
    if not effective_entitlements(db, ctx.tenant)["ai_anomaly"]["enabled"]:
        items = [i for i in items if i["kind"] != "anomaly"]
    if not effective_entitlements(db, ctx.tenant)["ai_forecast"]["enabled"]:
        items = [i for i in items if i["kind"] != "estimate"]
    names = {t.id: t for t in db.scalars(select(T).where(visible_filter(ctx), T.id.in_([r for i in items for r in i["refs"]] or ["-"])))}
    for i in items:
        i["supporting"] = [ser(names[r]) for r in i["refs"] if r in names]
    return {"items": items, "engine": ai.ENGINE}


class ReviewIn(BaseModel):
    status: str


@router.post("/ai/insights/{key:path}/review")
def ai_review(key: str, b: ReviewIn, ctx: Ctx = Depends(require_module("ai_insights")), db=Depends(get_db)):
    if b.status not in ("acknowledged", "dismissed"):
        raise HTTPException(422, "Status must be acknowledged or dismissed")
    if not any(i["key"] == key for i in ai.insights(db, ctx)):
        raise HTTPException(404, "Insight not found")  # cannot review what you cannot see
    r = db.scalar(select(m.InsightReview).where(m.InsightReview.tenant_id == ctx.tenant.id, m.InsightReview.key == key))
    if r:
        r.status, r.by_user_id, r.at = b.status, ctx.user.id, datetime.utcnow()
    else:
        db.add(m.InsightReview(tenant_id=ctx.tenant.id, key=key, status=b.status, by_user_id=ctx.user.id))
    audit(db, ctx, "insight", None, b.status, {"key": key})
    db.commit()
    return {"ok": True}


class AskIn(BaseModel):
    question: str


@router.post("/ai/ask")
def ai_ask(b: AskIn, ctx: Ctx = Depends(require_module("ai_insights")), db=Depends(get_db)):
    if not ctx.can("ai.use"):
        raise HTTPException(403, "You do not have permission for this action")
    r = ai.answer(db, ctx, b.question)
    r["citations"] = [ser(t) for t in db.scalars(select(T).where(visible_filter(ctx), T.id.in_(r["refs"] or ["-"])))]
    r["engine"] = ai.ENGINE
    audit(db, ctx, "ai_query", None, "asked", {"question": b.question[:200]})
    db.commit()
    return r


# ---------------- Marketing & sales spend (Pillar 2) ----------------
def growth_rows(db, ctx, period: str, dimension_key: str = "campaign", filters: dict | None = None) -> dict:
    filters = filters or {}
    dim = db.scalar(select(m.Dimension).where(m.Dimension.tenant_id == ctx.tenant.id, m.Dimension.key == dimension_key))
    if not dim:
        return {"rows": [], "untagged_minor": 0, "total_minor": 0, "notes": []}
    s, e = month_bounds(period)
    values = {v.id: v.name for v in db.scalars(select(m.DimensionValue).where(m.DimensionValue.dimension_id == dim.id))}
    agg = defaultdict(int)
    untagged = 0
    mkt = db.scalar(select(m.Category.id).where(m.Category.tenant_id == ctx.tenant.id, m.Category.name == "Marketing"))
    for t, dep, prj, a in allocations(db, ctx, s, e):
        if filters.get("department_id") and dep != filters["department_id"]:
            continue
        if filters.get("project_id") and prj != filters["project_id"]:
            continue
        if filters.get("category_id") and t.category_id != filters["category_id"]:
            continue
        v = (t.dimensions or {}).get(dim.id)
        if v:
            agg[v] += a
        elif t.category_id == mkt:
            untagged += a
    budgets = {b.scope_id: b for b in db.scalars(select(m.Budget).where(m.Budget.tenant_id == ctx.tenant.id, m.Budget.scope == "dimension", m.Budget.dimension_id == dim.id, m.Budget.period == period))}
    mets = {}
    for gm, bt in db.execute(select(m.GrowthMetric, m.ImportBatch).join(m.ImportBatch, m.ImportBatch.id == m.GrowthMetric.batch_id)
                             .where(m.GrowthMetric.tenant_id == ctx.tenant.id, m.ImportBatch.period == period, m.ImportBatch.status == "imported")):
        mets[gm.campaign_value_id] = (gm, bt)
    rows = []
    for vid in sorted(set(agg) | set(budgets), key=lambda x: -agg.get(x, 0)):
        b = budgets.get(vid)
        row = {"value_id": vid, "name": values.get(vid, "?"), "actual_minor": agg.get(vid, 0), "budget_minor": b.amount_minor if b else None,
               "variance_minor": (b.amount_minor - agg.get(vid, 0)) if b else None, "utilization": round(agg.get(vid, 0) / b.amount_minor * 100, 1) if b else None,
               "leads": None, "customers": None, "cost_per_lead_minor": None, "cac_minor": None, "roi_pct": None, "metric_note": "Unavailable - no lead/customer data imported for this period",
               "source": None}
        if vid in mets:
            gm, bt = mets[vid]
            row.update(leads=gm.leads, customers=gm.customers, source=f"{bt.source}, imported {bt.created_at:%Y-%m-%d}, {bt.currency}, attribution: {bt.attribution_method}")
            parts = []
            if gm.leads:
                row["cost_per_lead_minor"] = round(agg.get(vid, 0) / gm.leads)
            else:
                parts.append("cost per lead needs lead count")
            if gm.customers:
                row["cac_minor"] = round(agg.get(vid, 0) / gm.customers)
            else:
                parts.append("CAC needs customer count")
            if gm.revenue_minor and agg.get(vid, 0):
                row["roi_pct"] = round((gm.revenue_minor - agg[vid]) / agg[vid] * 100, 1)
            else:
                parts.append("ROI needs attributed revenue")
            row["metric_note"] = "; ".join(parts) or f"Estimated using imported data and the stated attribution method ({bt.attribution_method})"
        rows.append(row)
    return {"rows": rows, "untagged_minor": untagged, "total_minor": sum(agg.values()) + untagged, "tagged_minor": sum(agg.values()),
            "dimension": {"id": dim.id, "name": dim.name}, "period": period,
            "notes": ["CAC, cost per lead and ROI appear only when imported lead/customer/revenue data exists; they are estimates tied to the attribution method shown."]}


@router.get("/growth/spend")
def growth_spend(period: str | None = None, dimension: str = "campaign", department_id: str | None = None, project_id: str | None = None,
                 category_id: str | None = None, format: str = "json", ctx: Ctx = Depends(require_module("growth_spend")), db=Depends(get_db)):
    if not ctx.can("growth.read"):
        raise HTTPException(403, "You do not have permission for this action")
    period = period or default_period(db, ctx)
    r = growth_rows(db, ctx, period, dimension, dict(department_id=department_id, project_id=project_id, category_id=category_id))
    if format == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["name", "actual", "budget", "variance", "utilization_pct", "leads", "customers", "cost_per_lead", "cac", "note"])
        for x in r["rows"]:
            w.writerow([x["name"], fmt(x["actual_minor"]), fmt(x["budget_minor"]) if x["budget_minor"] else "", fmt(x["variance_minor"]) if x["variance_minor"] is not None else "",
                        x["utilization"] if x["utilization"] is not None else "", x["leads"] or "", x["customers"] or "",
                        fmt(x["cost_per_lead_minor"]) if x["cost_per_lead_minor"] else "unavailable", fmt(x["cac_minor"]) if x["cac_minor"] else "unavailable", x["metric_note"]])
        return Response(out.getvalue(), media_type="text/csv")
    return r


@router.post("/growth/import")
async def growth_import(source: str = Form(...), period: str = Form(...), currency: str = Form(...), attribution_method: str = Form(...),
                        file: UploadFile = File(...), ctx: Ctx = Depends(require_module("growth_import")), db=Depends(get_db)):
    if not ctx.can("growth.manage"):
        raise HTTPException(403, "You do not have permission for this action")
    errors, parsed = [], []
    if currency != ctx.tenant.currency:
        errors.append({"row": 0, "message": f"Currency {currency} does not match the organization currency {ctx.tenant.currency}"})
    if len(period) != 7 or period[4] != "-":
        errors.append({"row": 0, "message": "Period must look like 2026-10"})
    if not attribution_method.strip():
        errors.append({"row": 0, "message": "Attribution method is required"})
    dim = db.scalar(select(m.Dimension).where(m.Dimension.tenant_id == ctx.tenant.id, m.Dimension.key == "campaign"))
    vals = {v.name.lower(): v.id for v in db.scalars(select(m.DimensionValue).where(m.DimensionValue.dimension_id == dim.id))} if dim else {}
    seen = set()
    text = (await file.read()).decode("utf-8-sig", "ignore")
    for i, r in enumerate(csv.DictReader(io.StringIO(text)), 2):
        vid = vals.get((r.get("campaign") or "").strip().lower())
        try:
            if not vid:
                raise ValueError(f"Unknown campaign '{r.get('campaign')}'")
            if vid in seen:
                raise ValueError("Duplicate campaign in file")
            if db.scalar(select(m.GrowthMetric.id).join(m.ImportBatch, m.ImportBatch.id == m.GrowthMetric.batch_id)
                         .where(m.GrowthMetric.campaign_value_id == vid, m.ImportBatch.period == period, m.ImportBatch.status == "imported", m.GrowthMetric.tenant_id == ctx.tenant.id)):
                raise ValueError("Metrics for this campaign and period were already imported")
            seen.add(vid)
            leads = int(r["leads"]) if r.get("leads") not in (None, "") else None
            cust = int(r["customers"]) if r.get("customers") not in (None, "") else None
            rev = to_minor(r["revenue"]) if r.get("revenue") not in (None, "") else None
            if (leads is not None and leads < 0) or (cust is not None and cust < 0):
                raise ValueError("Counts cannot be negative")
            parsed.append((vid, r.get("external_ref"), leads, cust, rev))
        except (ValueError, HTTPException) as ex:
            errors.append({"row": i, "message": str(getattr(ex, "detail", ex))})
    if not parsed and not errors:
        errors.append({"row": 0, "message": "The file has no data rows"})
    batch = m.ImportBatch(tenant_id=ctx.tenant.id, kind="growth_metrics", source=source, period=period, currency=currency, attribution_method=attribution_method,
                          status="rejected" if errors else "imported", rows_ok=0 if errors else len(parsed), errors=errors, created_by=ctx.user.id)
    db.add(batch)
    db.flush()
    if not errors:  # all-or-nothing: a partial import would give misleading metrics
        for vid, ref, leads, cust, rev in parsed:
            db.add(m.GrowthMetric(tenant_id=ctx.tenant.id, batch_id=batch.id, campaign_value_id=vid, external_ref=ref, leads=leads, customers=cust, revenue_minor=rev))
    audit(db, ctx, "import_batch", batch.id, batch.status, {"source": source, "period": period, "errors": len(errors)})
    db.commit()
    if errors:
        raise HTTPException(422, detail={"code": "IMPORT_REJECTED", "message": "Nothing was imported. Fix the rows below and upload again.", "errors": errors})
    return {"batch_id": batch.id, "rows": len(parsed)}


@router.get("/growth/imports")
def growth_imports(ctx: Ctx = Depends(require_module("growth_spend")), db=Depends(get_db)):
    return [{"id": b.id, "source": b.source, "period": b.period, "currency": b.currency, "attribution_method": b.attribution_method, "status": b.status,
             "rows_ok": b.rows_ok, "errors": b.errors, "at": b.created_at.isoformat()} for b in db.scalars(select(m.ImportBatch).where(m.ImportBatch.tenant_id == ctx.tenant.id).order_by(m.ImportBatch.created_at.desc()))]


@router.get("/usage")
def usage(ctx: Ctx = Depends(require("audit.read")), db=Depends(get_db)):
    """Tenant-level adoption by pillar (FR-22): counts only, from this tenant's own data."""
    tx = list(db.scalars(select(T).where(T.tenant_id == ctx.tenant.id)))
    return {"P1_transactions": len(tx), "P1_approvals": len(list(db.scalars(select(m.ApprovalStep.id).where(m.ApprovalStep.tenant_id == ctx.tenant.id)))),
            "P2_growth_tagged": sum(1 for t in tx if t.dimensions), "P3_ai_assisted": sum(1 for t in tx if t.ai),
            "P3_ai_reviews": len(list(db.scalars(select(m.AiExtraction.id).where(m.AiExtraction.tenant_id == ctx.tenant.id))))}
