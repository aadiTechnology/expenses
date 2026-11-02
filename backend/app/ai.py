"""Assistive AI layer (engine "rules-v1"): deterministic parsing and analytics. No external model or OCR
provider is configured (PRD DEC-04). Everything here only SUGGESTS; nothing is posted without a human
confirming it, and every query goes through the same visibility filter as the ordinary API (FR-19)."""
import re
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import models as m
from .core import COUNTED, Ctx
from .ledger import CREDIT, T, allocations, month_bounds, totals, visible_filter

ENGINE = "rules-v1 (rule-based, no external AI provider)"
NUM = r"(\d[\d,]*(?:\.\d{1,2})?)"
KEYWORDS = {
    "vegetable": "Vegetables", "milk": "Milk", "petrol": "Petrol", "fuel": "Petrol", "grocery": "Groceries", "groceries": "Groceries",
    "electricity": "Utilities", "internet": "Utilities", "wifi": "Utilities", "doctor": "Healthcare", "medicine": "Healthcare",
    "school": "Education", "fees": "Education", "restaurant": "Food and Restaurants", "lunch": "Food and Restaurants",
    "dinner": "Food and Restaurants", "rent": "Housing", "cloth": "Shopping", "movie": "Entertainment", "taxi": "Travel",
    "flight": "Travel", "hotel": "Travel", "cab": "Travel", "train": "Travel", "azure": "Infrastructure", "hosting": "Infrastructure",
    "github": "Software Subscriptions", "subscription": "Software Subscriptions", "ads": "Marketing", "advertising": "Marketing",
    "laptop": "Equipment", "stationery": "Office Expenses", "training": "Training", "salary": "Employee Costs",
}


def _cat_index(db: DbSession, tenant_id: str):
    return {c.name.lower(): c for c in db.scalars(select(m.Category).where(m.Category.tenant_id == tenant_id, m.Category.active.is_(True)))}


def suggest_category(db: DbSession, tenant_id: str, text: str):
    """Returns the TOP-LEVEL category (subcategories roll up into their parent) and a confidence."""
    idx = _cat_index(db, tenant_id)
    by_id = {c.id: c for c in idx.values()}
    top = lambda c: by_id.get(c.parent_id, c) if c.parent_id else c  # noqa: E731
    low = text.lower()
    for name, c in idx.items():
        if name in low:
            return top(c), 0.92
    for kw, target in KEYWORDS.items():
        if kw in low and target.lower() in idx:
            return top(idx[target.lower()]), 0.9
    return None, 0.4


def _date_from(text: str, today: date):
    low = text.lower()
    if "yesterday" in low:
        return today - timedelta(days=1), True
    if "today" in low:
        return today, True
    mm = re.search(r"(\d{4}-\d{2}-\d{2})", low)
    if mm:
        return date.fromisoformat(mm.group(1)), True
    return today, False


def parse_text(db: DbSession, tenant_id: str, text: str, today: date | None = None, source: str = "voice") -> list[dict]:
    """'Today vegetables 250, milk 60 and petrol 500.' -> three reviewable suggestions."""
    today = today or date.today()
    when, explicit = _date_from(text, today)
    chunks = [c.strip() for c in re.split(r",|\band\b|;|\n", text, flags=re.I) if c.strip()]
    items = []
    for ch in chunks:
        am = re.search(NUM, ch.replace("₹", " "))
        if not am:
            continue
        amount = am.group(1).replace(",", "")
        desc = re.sub(r"\b(today|yesterday|rs\.?|rupees|inr|on|for|spent|paid)\b|₹|" + re.escape(am.group(1)), " ", ch, flags=re.I)
        desc = re.sub(r"\d{4}-\d{2}-\d{2}", " ", desc)
        desc = " ".join(desc.split()).strip(" -:") or "Expense"
        income = bool(re.search(r"salary|received|income|credited", ch, re.I))
        cat, conf = suggest_category(db, tenant_id, desc)
        if income:
            cat = _cat_index(db, tenant_id).get("income") or _cat_index(db, tenant_id).get("salary") or cat
        conf = round(conf * (1.0 if explicit else 0.95), 2)
        items.append({"date": when.isoformat(), "description": desc.capitalize(), "amount": amount,
                      "type": "income" if income else "expense", "category_id": cat.id if cat else None,
                      "category_name": cat.name if cat else None, "confidence": conf, "needs_review": conf < 0.75 or cat is None,
                      "source": source, "account_id": None})
    return items


def extract_receipt(db: DbSession, tenant_id: str, filename: str, data: bytes, today: date | None = None) -> list[dict]:
    """SIMULATED extraction: reads plain text embedded in the file (text PDFs) or hints in the filename.
    A real OCR provider replaces this function (DEC-04). Always returns low confidence for guesses."""
    today = today or date.today()
    blob = re.sub(rb"[^\x20-\x7e\n]", b" ", data[:200000]).decode("ascii", "ignore")
    text = blob + " " + filename.replace("_", " ")
    total = None
    for pat in (r"(?:grand\s+)?total[^\d]{0,20}" + NUM, r"amount[^\d]{0,20}" + NUM, r"(?:rs\.?|inr|₹)\s*" + NUM):
        mt = re.search(pat, text, re.I)
        if mt:
            total = mt.group(1).replace(",", "")
            break
    dm = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    merchant = None
    mm = re.search(r"(?:merchant|vendor|store)\s*[:\-]\s*([A-Za-z0-9 &.\']{3,40})", text, re.I)
    if mm:
        merchant = mm.group(1).strip()
    tax = re.search(r"(?:gst|tax)[^\d]{0,15}" + NUM, text, re.I)
    cat, conf = suggest_category(db, tenant_id, (merchant or "") + " " + text[:400])
    base = 0.85 if (total and dm and merchant) else 0.55 if total else 0.2
    return [{"date": dm.group(1) if dm else today.isoformat(), "description": f"Receipt - {merchant or filename}",
             "merchant": merchant, "amount": total, "tax": tax.group(1).replace(",", "") if tax else None, "type": "expense",
             "category_id": cat.id if cat else None, "category_name": cat.name if cat else None,
             "confidence": round(min(base, conf + 0.1) if cat else base * 0.8, 2),
             "needs_review": True, "source": "receipt", "account_id": None,
             "note": "Simulated extraction - no OCR provider is connected; check every field."}]


def find_duplicate(db: DbSession, tenant_id: str, d: date, amount_minor: int, description: str, merchant: str | None):
    key = (merchant or description or "").lower().strip()
    for t in db.scalars(select(T).where(T.tenant_id == tenant_id, T.date == d, T.amount_minor == amount_minor)):
        if key and key == (t.merchant or t.description or "").lower().strip():
            return t
    return None


# ---------------- insights (facts vs estimates) ----------------
def insights(db: DbSession, ctx: Ctx, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    period = today.strftime("%Y-%m")
    # the demo data lives in October 2026; use the latest month that has data when the current month is empty
    latest = db.scalar(select(T.date).where(visible_filter(ctx), T.status.in_(COUNTED)).order_by(T.date.desc()).limit(1))
    if latest and not db.scalar(select(T.id).where(visible_filter(ctx), T.status.in_(COUNTED), T.date >= month_bounds(period)[0]).limit(1)):
        period = latest.strftime("%Y-%m")
    s, e = month_bounds(period)
    py, pm = (s.year - 1, 12) if s.month == 1 else (s.year, s.month - 1)
    ps, pe = month_bounds(f"{py}-{pm:02d}")
    cur, prev = totals(db, ctx, s, e), totals(db, ctx, ps, pe)
    if prev["expense"]:
        chg = (cur["expense"] - prev["expense"]) / prev["expense"] * 100
        out.append({"key": f"mom:{period}", "kind": "fact", "title": f"Spending {'rose' if chg > 0 else 'fell'} {abs(chg):.0f}% compared with last month",
                    "body": f"{period}: {cur['expense'] / 100:,.2f} vs {prev['expense'] / 100:,.2f} the month before (actual posted figures).", "refs": []})
    cats = defaultdict(int)
    names = {c.id: c for c in db.scalars(select(m.Category).where(m.Category.tenant_id == ctx.tenant.id))}
    for t, _, _, amt in allocations(db, ctx, s, e):
        if t.category_id:
            c = names.get(t.category_id)
            cats[(names[c.parent_id].name if c and c.parent_id in names else c.name) if c else "Uncategorised"] += amt
    if cats and cur["expense"]:
        top = sorted(cats.items(), key=lambda x: -x[1])[:3]
        share = top[0][1] / cur["expense"] * 100
        out.append({"key": f"top:{period}", "kind": "fact", "title": f"Highest spending: {top[0][0]} ({share:.0f}% of expenses)",
                    "body": "; ".join(f"{n} {v / 100:,.2f}" for n, v in top), "refs": []})
    # recurring: same merchant/description in >= 2 different months (aggregated in SQL)
    ym = func.extract("year", T.date) * 100 + func.extract("month", T.date)
    name = func.lower(func.coalesce(T.merchant, T.description))
    rec = [r[0] for r in db.execute(select(name).where(visible_filter(ctx), T.status.in_(COUNTED), T.type == "expense").group_by(name).having(func.count(func.distinct(ym)) >= 2))]
    if rec:
        out.append({"key": "recurring", "kind": "fact", "title": f"{len(rec)} recurring expense(s) detected",
                    "body": ", ".join(sorted(rec)[:6]) + " appear in more than one month.", "refs": []})
    # anomaly: amount > 3x the median of its category and above a floor (advisory only)
    by_cat = defaultdict(list)
    for tid, cid, amt, d, desc in db.execute(select(T.id, T.category_id, T.amount_minor, T.date, T.description).where(visible_filter(ctx), T.status.in_(COUNTED), T.type == "expense")):
        by_cat[cid].append((tid, amt, d, desc))
    for cid, ts in by_cat.items():
        if len(ts) < 5:
            continue
        med = median(a for _, a, _, _ in ts)
        for tid, amt, d, desc in ts:
            if amt > 3 * med and amt >= 100000 and s <= d < e:
                out.append({"key": f"anomaly:{tid}", "kind": "anomaly", "title": f"Unusual amount: {desc}",
                            "body": f"{amt / 100:,.2f} is more than 3x the typical {names[cid].name if cid in names else 'category'} amount ({med / 100:,.2f}). "
                                    "This is an advisory flag, not a finding of error or fraud.", "refs": [tid]})
    # forecast (estimate)
    if period == today.strftime("%Y-%m") and today.day > 3:
        days = (e - s).days
        proj = cur["expense"] / today.day * days
        out.append({"key": f"forecast:{period}", "kind": "estimate", "title": "Month-end spending forecast (estimate)",
                    "body": f"If spending continues at the current daily rate, expenses may reach about {proj / 100:,.2f}. Assumption: straight-line daily average. Not an actual balance.", "refs": []})
    else:
        bs = [b for b in db.scalars(select(m.Budget).where(m.Budget.tenant_id == ctx.tenant.id, m.Budget.period == period, m.Budget.scope == "overall"))]
        if bs and cur["expense"]:
            out.append({"key": f"budget:{period}", "kind": "estimate", "title": "Budget outlook (estimate)",
                        "body": f"Actual spending is {cur['expense'] / bs[0].amount_minor * 100:.0f}% of the {period} budget. Estimates are not posted figures.", "refs": []})
    reviewed = {r.key: r.status for r in db.scalars(select(m.InsightReview).where(m.InsightReview.tenant_id == ctx.tenant.id))}
    for i in out:
        i["review_status"] = reviewed.get(i["key"], "open")
        i["engine"] = ENGINE
    return out


# ---------------- natural-language questions (permission-aware) ----------------
def answer(db: DbSession, ctx: Ctx, question: str, today: date | None = None) -> dict:
    q = question.lower()
    latest = db.scalar(select(T.date).where(visible_filter(ctx), T.status.in_(COUNTED)).order_by(T.date.desc()).limit(1))
    ref = latest or (today or date.today())
    s, e = month_bounds(ref.strftime("%Y-%m"))
    mo = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)", q)
    if mo:
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
        s, e = month_bounds(f"{ref.year}-{months.index(mo.group(1)) + 1:02d}")
    label = s.strftime("%B %Y")
    projects = {p.name.lower(): p for p in db.scalars(select(m.Project).where(m.Project.tenant_id == ctx.tenant.id))}
    depts = {d.name.lower(): d for d in db.scalars(select(m.Department).where(m.Department.tenant_id == ctx.tenant.id))}
    cats = {c.name.lower(): c for c in db.scalars(select(m.Category).where(m.Category.tenant_id == ctx.tenant.id))}
    rows = list(allocations(db, ctx, s, e))
    cite = lambda ts: [t.id for t in ts][:5]  # noqa: E731
    for name, p in projects.items():
        if name in q:
            sel = [(t, a) for t, d, pr, a in rows if pr == p.id]
            if not sel:
                return {"answer": f"I found no spending on {p.name} that you are authorised to see in {label}.", "facts": [], "refs": [], "kind": "fact"}
            tot = sum(a for _, a in sel)
            return {"answer": f"{p.name} spending in {label}: {tot / 100:,.2f} across {len(sel)} transactions (visible to you).", "facts": [], "refs": cite([t for t, _ in sel]), "kind": "fact"}
    for name, d in depts.items():
        if name in q:
            sel = [(t, a) for t, dd, pr, a in rows if dd == d.id]
            if not sel:
                return {"answer": f"I found no spending for {d.name} that you are authorised to see in {label}.", "facts": [], "refs": [], "kind": "fact"}
            return {"answer": f"{d.name} spending in {label}: {sum(a for _, a in sel) / 100:,.2f} ({len(sel)} transactions).", "facts": [], "refs": cite([t for t, _ in sel]), "kind": "fact"}
    for name, c in cats.items():
        if name in q and len(name) > 3:
            ids = {c.id} | {x.id for x in cats.values() if x.parent_id == c.id}
            sel = [(t, a) for t, _, _, a in rows if t.category_id in ids]
            return {"answer": f"{c.name} in {label}: {sum(a for _, a in sel) / 100:,.2f} ({len(sel)} transactions).", "facts": [], "refs": cite([t for t, _ in sel]), "kind": "fact"}
    if "top" in q or "most" in q or "highest" in q or "categor" in q:
        agg = defaultdict(int)
        by_id = {c.id: c for c in cats.values()}
        for t, _, _, a in rows:
            c = by_id.get(t.category_id)
            agg[(by_id[c.parent_id].name if c and c.parent_id in by_id else c.name) if c else "Uncategorised"] += a
        top = sorted(agg.items(), key=lambda x: -x[1])[:5]
        return {"answer": f"Top categories in {label}: " + "; ".join(f"{n} {v / 100:,.2f}" for n, v in top) + ".", "facts": [], "refs": [], "kind": "fact"}
    if "pending" in q or "approval" in q:
        n = len(list(db.scalars(select(T.id).where(visible_filter(ctx), T.status.in_(("submitted", "pm_approved", "verified"))))))
        return {"answer": f"{n} expense(s) you can see are still moving through approval.", "facts": [], "refs": [], "kind": "fact"}
    if "save" in q or "income" in q or "total" in q or "spend" in q or "spent" in q:
        tt = totals(db, ctx, s, e)
        return {"answer": f"{label}: income {tt['income'] / 100:,.2f}, expenses {tt['expense'] / 100:,.2f}, difference {tt['savings'] / 100:,.2f} (based on the records you can access).", "facts": [], "refs": [], "kind": "fact"}
    return {"answer": "I can answer questions about spending by project, department or category, top categories, pending approvals and monthly totals - using only the records you are allowed to see.", "facts": [], "refs": [], "kind": "help"}
