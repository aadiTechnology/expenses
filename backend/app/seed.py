"""Deterministic, idempotent demo seed with stable IDs. Everything is synthetic and flagged sample/is_demo.
Usage:  python -m app.seed [--reset]      (refuses to run when SPENDOS_ENV=production)"""
import sys
from datetime import date

from sqlalchemy import delete, select

from . import models as m
from .core import ENV, SessionLocal, Ctx, ROLE_PERMISSIONS, engine, hash_password
from .ledger import evaluate_budget_alerts
from .main import ensure_catalogue, init_db
from .templates import TEMPLATES, add_growth_dimensions, apply_template

DEMO_PASSWORD = "SpendOS@Demo26"  # disposable, demo-only; documented in docs/demo/DEMO_ACCESS.md
DOMAIN = "@spendos.demo.test"
PERSONAL_ID, BUSINESS_ID = "ten_personal_demo", "ten_aadi_demo"
D = lambda mo, day: date(2026, mo, day)  # noqa: E731
R = lambda rupees: int(round(rupees * 100))  # noqa: E731


def reset(db):
    for tid in (PERSONAL_ID, BUSINESS_ID):
        for tbl in reversed(m.Base.metadata.sorted_tables):
            if "tenant_id" in tbl.c:
                db.execute(delete(tbl).where(tbl.c.tenant_id == tid))
        db.execute(delete(m.Tenant).where(m.Tenant.id == tid))
    ids = [u.id for u in db.scalars(select(m.User).where(m.User.email.like("%" + DOMAIN)))]
    db.execute(delete(m.Session).where(m.Session.user_id.in_(ids)))
    db.execute(delete(m.PasswordReset).where(m.PasswordReset.user_id.in_(ids)))
    db.execute(delete(m.User).where(m.User.id.in_(ids)))
    db.commit()


def user(db, key, name, email=None, platform=False):
    email = (email or key) + DOMAIN
    u = m.User(id=f"usr_{key.replace('.', '_')}", email=email, name=name, password_hash=hash_password(DEMO_PASSWORD), is_platform_admin=platform)
    db.add(u)
    return u


class Seeder:
    def __init__(self, db, tenant):
        self.db, self.t, self.n = db, tenant, 0
        self.cat = {c.name: c for c in db.scalars(select(m.Category).where(m.Category.tenant_id == tenant.id))}

    def tx(self, mo, day, typ, rupees, cat=None, desc="", acct=None, by=None, member=None, shared=False, to=None, status="posted", sub=None,
           merchant=None, dept=None, proj=None, dims=None, reimbursable=False, refund_of=None, notes=None, tid=None):
        self.n += 1
        c = self.cat.get(cat) if cat else None
        s = self.cat.get(sub) if sub else None
        t = m.Transaction(id=tid or f"txn_{self.t.id[4:8]}_{self.n:03d}", tenant_id=self.t.id, seq=self.n, date=D(mo, day), type=typ, amount_minor=R(rupees),
                          currency="INR", category_id=c.id if c else None, subcategory_id=s.id if s else None, description=desc, merchant=merchant,
                          account_id=acct, to_account_id=to, created_by=by, member_id=member or by, shared=shared, department_id=dept, project_id=proj,
                          dimensions=dims or {}, status=status, reimbursable=reimbursable, refund_of_id=refund_of, notes=notes, sample=True)
        self.db.add(t)
        self.db.flush()  # children (splits, approval steps) reference this row
        return t


def seed_personal(db):
    t = m.Tenant(id=PERSONAL_ID, name="Rahul Sharma - Household (SAMPLE DATA)", edition="personal", plan_code="personal_free", template_code="personal", is_demo=True)
    db.add(t)
    db.flush()
    apply_template(db, t, "personal")
    for a in db.scalars(select(m.Account).where(m.Account.tenant_id == t.id)):
        db.delete(a)
    db.flush()
    people = [("rahul.sharma", "Rahul Sharma", "owner"), ("priya.sharma", "Priya Sharma", "family_member"),
              ("aarav.sharma", "Aarav Sharma", "family_member"), ("sunita.sharma", "Sunita Sharma", "family_viewer")]
    mem = {}
    for key, name, role in people:
        u = user(db, key, name)
        db.flush()
        mm = m.Membership(id=f"mem_p_{key.split('.')[0]}", user_id=u.id, tenant_id=t.id, role=role, title={"owner": "Owner", "family_member": "Family member", "family_viewer": "Family viewer"}[role])
        db.add(mm)
        mem[key.split(".")[0]] = mm.id
    accts = {}
    for key, name, typ, opening in [("cash", "Cash in Hand", "cash", 5000), ("bank", "HDFC Savings", "bank", 60000), ("upi", "PhonePe UPI", "upi", 3000),
                                    ("card", "HDFC Credit Card", "credit_card", 0), ("wallet", "Paytm Wallet", "wallet", 500)]:
        a = m.Account(id=f"acc_p_{key}", tenant_id=t.id, name=name, type=typ, currency="INR", opening_minor=R(opening))
        db.add(a)
        accts[key] = a.id
    db.flush()
    S = Seeder(db, t)
    A, M = accts, mem
    r, p, a_, s_ = M["rahul"], M["priya"], M["aarav"], M["sunita"]
    # September (previous month) so comparisons and recurring detection have history
    S.tx(9, 15, "income", 65000, "Salary", "Monthly salary", A["bank"], r)
    S.tx(9, 18, "expense", 15000, "Housing", "House rent", A["bank"], r, shared=True)
    S.tx(9, 4, "expense", 1380, "Utilities", "Electricity bill", A["bank"], r, shared=True)
    S.tx(9, 11, "expense", 999, "Utilities", "Internet bill", A["card"], r, shared=True)
    S.tx(9, 25, "expense", 3000, "Groceries", "Groceries", A["upi"], p, shared=True)
    S.tx(9, 22, "expense", 650, "Transport", "Petrol", A["cash"], r, sub="Petrol")
    S.tx(9, 29, "expense", 499, "Entertainment", "OTT subscription", A["card"], r, shared=True)
    S.tx(9, 6, "expense", 5000, "Education", "School fees", A["bank"], r, shared=True)
    # October: the 15 PRD sample transactions first
    t7 = S.tx(10, 6, "expense", 600, "Healthcare", "Doctor consultation", A["upi"], r)
    t8 = S.tx(10, 7, "expense", 850, "Healthcare", "Medicines", A["upi"], r)
    t11 = S.tx(10, 13, "expense", 2400, "Shopping", "Clothing", A["card"], p)
    S.tx(10, 1, "expense", 250, "Groceries", "Vegetables", A["cash"], r, shared=True, sub="Vegetables")
    S.tx(10, 1, "expense", 60, "Household", "Milk", A["cash"], r, shared=True, sub="Milk")
    S.tx(10, 2, "expense", 500, "Transport", "Petrol", A["cash"], r, sub="Petrol")
    S.tx(10, 3, "expense", 1850, "Groceries", "Grocery shopping", A["upi"], p, shared=True)
    S.tx(10, 4, "expense", 1450, "Utilities", "Electricity bill", A["bank"], r, shared=True)
    fees_t = S.tx(10, 5, "expense", 5000, "Education", "School fees", A["bank"], r, shared=True, member=a_)
    S.tx(10, 9, "expense", 900, "Food and Restaurants", "Restaurant", A["card"], p, shared=True)
    S.tx(10, 11, "expense", 999, "Utilities", "Internet bill", A["card"], r, shared=True)
    S.tx(10, 15, "income", 65000, "Salary", "Monthly salary", A["bank"], r)
    rent_t = S.tx(10, 18, "expense", 15000, "Housing", "House rent", A["bank"], r, shared=True)
    S.tx(10, 20, "expense", 700, "Transport", "Petrol", A["upi"], r, sub="Petrol")
    groc_t = S.tx(10, 25, "expense", 2100, "Groceries", "Groceries", A["upi"], p, shared=True)
    # additional: cash, UPI, card, family, refunds, transfers
    S.tx(10, 2, "transfer", 3000, desc="Cash withdrawal", acct=A["bank"], to=A["cash"], by=r)
    S.tx(10, 3, "expense", 180, "Groceries", "Vegetables", A["cash"], p, shared=True, sub="Vegetables")
    S.tx(10, 4, "expense", 120, "Household", "Milk", A["cash"], r, shared=True, sub="Milk")
    S.tx(10, 5, "expense", 120, "Transport", "Auto fare to tuition", A["cash"], a_)
    S.tx(10, 6, "expense", 150, "Food and Restaurants", "Ice cream", A["wallet"], a_)
    S.tx(10, 7, "expense", 800, "Entertainment", "Movie tickets", A["card"], r, shared=True)
    S.tx(10, 8, "expense", 599, "Utilities", "Mobile recharge", A["upi"], p)
    S.tx(10, 8, "expense", 220, "Groceries", "Vegetables", A["cash"], p, shared=True, sub="Vegetables")
    S.tx(10, 9, "transfer", 5000, desc="Top up UPI", acct=A["bank"], to=A["upi"], by=r)
    S.tx(10, 10, "refund", 150, "Healthcare", "Medicine returned - refund", A["upi"], r, refund_of=t8.id)
    S.tx(10, 10, "expense", 350, "Personal Care", "Haircut", A["cash"], r)
    S.tx(10, 12, "expense", 420, "Education", "Notebooks and stationery", A["upi"], p, shared=True, member=a_)
    S.tx(10, 12, "expense", 60, "Household", "Milk", A["cash"], r, shared=True, sub="Milk")
    S.tx(10, 14, "transfer", 4500, desc="Credit card bill payment", acct=A["bank"], to=A["card"], by=r)
    S.tx(10, 14, "refund", 800, "Shopping", "Clothing return - refund", A["card"], p, refund_of=t11.id)
    S.tx(10, 15, "expense", 3200, "Insurance", "Term insurance premium", A["bank"], r)
    S.tx(10, 15, "expense", 8000, "Loan Repayment", "Home loan EMI", A["bank"], r, shared=True)
    S.tx(10, 16, "expense", 260, "Groceries", "Vegetables", A["cash"], p, shared=True, sub="Vegetables")
    S.tx(10, 16, "expense", 380, "Travel", "Taxi", A["upi"], p)
    S.tx(10, 17, "expense", 1300, "Food and Restaurants", "Dinner out", A["card"], r, shared=True)
    S.tx(10, 17, "income", 320, "Other Income", "Savings interest", A["bank"], r)
    S.tx(10, 18, "transfer", 500, desc="Pocket money to wallet", acct=A["cash"], to=A["wallet"], by=r)
    S.tx(10, 19, "expense", 1750, "Shopping", "Festival sweets and decor", A["card"], p, shared=True)
    S.tx(10, 20, "expense", 1200, "Healthcare", "Dental check-up", A["upi"], p, shared=True, member=s_)
    S.tx(10, 21, "expense", 900, "Miscellaneous", "Gift for colleague", A["cash"], r)
    S.tx(10, 22, "expense", 650, "Education", "Books", A["upi"], a_)
    S.tx(10, 22, "expense", 60, "Household", "Milk", A["cash"], r, shared=True, sub="Milk")
    S.tx(10, 23, "expense", 540, "Travel", "Cab to airport", A["upi"], r)
    S.tx(10, 24, "expense", 240, "Groceries", "Vegetables", A["cash"], p, shared=True, sub="Vegetables")
    S.tx(10, 25, "expense", 980, "Household", "Cooking gas refill", A["upi"], p, shared=True)
    S.tx(10, 26, "expense", 420, "Food and Restaurants", "Snacks", A["wallet"], a_)
    S.tx(10, 27, "income", 4000, "Other Income", "Freelance work", A["bank"], r)
    S.tx(10, 28, "expense", 700, "Healthcare", "Medicines for Sunita", A["upi"], p, shared=True, member=s_)
    S.tx(10, 28, "reimbursement", 400, "Healthcare", "Insurer reimbursement - doctor visit", A["bank"], r, refund_of=t7.id)
    S.tx(10, 29, "expense", 499, "Entertainment", "OTT subscription", A["card"], r, shared=True)
    S.tx(10, 30, "expense", 230, "Groceries", "Vegetables", A["cash"], p, shared=True, sub="Vegetables")
    S.tx(10, 31, "transfer", 2000, desc="Top up UPI", acct=A["bank"], to=A["upi"], by=r)
    # who bears each shared expense (allocations must add up to the full amount)
    for n, tx_, parts in (("rent", rent_t, ((r, 10000), (p, 5000))), ("fees", fees_t, ((r, 3000), (p, 2000))), ("groc", groc_t, ((r, 1000), (p, 1100)))):
        for who, amt in parts:
            db.add(m.TransactionSplit(id=f"spl_p_{n}_{who[-5:]}", tenant_id=t.id, transaction_id=tx_.id, member_id=who, amount_minor=R(amt)))
    cat = lambda n: S.cat[n].id  # noqa: E731
    for name, scope, sid, amt in [("Household budget", "overall", None, 60000), ("Groceries", "category", cat("Groceries"), 6000), ("Transport", "category", cat("Transport"), 2000),
                                  ("Food and Restaurants", "category", cat("Food and Restaurants"), 3000), ("Utilities", "category", cat("Utilities"), 3500),
                                  ("Shopping", "category", cat("Shopping"), 4000), ("Healthcare", "category", cat("Healthcare"), 3000), ("Education", "category", cat("Education"), 6000),
                                  ("Entertainment", "category", cat("Entertainment"), 1500)]:
        db.add(m.Budget(id=f"bud_p_{name[:8].lower().replace(' ', '_')}", tenant_id=t.id, name=name, scope=scope, scope_id=sid, period="2026-10", amount_minor=R(amt)))
    for i, (n, tg, sv, dt) in enumerate([("Emergency fund", 200000, 85000, D(12, 31)), ("Family vacation", 60000, 22000, D(5, 1)), ("New laptop for Aarav", 70000, 30000, D(3, 1))]):
        db.add(m.SavingsGoal(id=f"goal_p_{i}", tenant_id=t.id, name=n, target_minor=R(tg), saved_minor=R(sv), target_date=dt))
    for n, amt, day, c in [("House rent", 15000, 18, "Housing"), ("Internet bill", 999, 11, "Utilities"), ("OTT subscription", 499, 29, "Entertainment")]:
        db.add(m.Recurring(tenant_id=t.id, description=n, amount_minor=R(amt), day_of_month=day, category_id=cat(c)))
    db.flush()
    return t, mem[("rahul")]


def seed_business(db):
    t = m.Tenant(id=BUSINESS_ID, name="Aadi Technology (ILLUSTRATIVE DEMO)", edition="business", plan_code="business_growth", template_code="it_company", is_demo=True)
    db.add(t)
    db.flush()
    apply_template(db, t, "it_company", with_growth_dims=True)
    for a in db.scalars(select(m.Account).where(m.Account.tenant_id == t.id)):
        db.delete(a)
    db.flush()
    deps = {}
    for k, n in [("sw", "Software Development"), ("tr", "Training & Internship"), ("mk", "Digital Marketing"), ("pd", "Product Development"), ("ad", "Administration")]:
        db.add(m.Department(id=f"dep_a_{k}", tenant_id=t.id, name=n))
        deps[k] = f"dep_a_{k}"
    prj = {}
    for k, n, d in [("crm", "Multitenant CRM", "sw"), ("rite", "RITeSchool", "sw"), ("pre", "Preschool ERP", "pd"), ("aipf", "AI Product Factory", "pd"),
                    ("intern", "Internship Program", "tr"), ("ops", "Internal Operations", "ad")]:
        db.add(m.Project(id=f"prj_a_{k}", tenant_id=t.id, name=n, department_id=deps[d]))
        prj[k] = f"prj_a_{k}"
    db.add(m.CostCentre(id="cc_a_delivery", tenant_id=t.id, name="CC-Delivery"))
    db.add(m.CostCentre(id="cc_a_growth", tenant_id=t.id, name="CC-Growth"))
    people = [("anita.deshmukh", "Anita Deshmukh", "org_admin", "ad", [], "Organization Admin"),
              ("sanjay.kulkarni", "Sanjay Kulkarni", "finance_manager", "ad", [], "Finance Manager"),
              ("vikram.joshi", "Vikram Joshi", "department_manager", "sw", [], "Head of Software Development"),
              ("neha.kapoor", "Neha Kapoor", "department_manager", "mk", [], "Head of Digital Marketing"),
              ("rohit.patil", "Rohit Patil", "project_manager", "sw", ["crm", "aipf"], "Project Manager"),
              ("sneha.iyer", "Sneha Iyer", "project_manager", "pd", ["rite", "pre", "intern"], "Project Manager"),
              ("arjun.mehta", "Arjun Mehta", "employee", "sw", ["rite"], "Software Engineer"),
              ("meera.nair", "Meera Nair", "employee", "sw", ["crm"], "Software Engineer"),
              ("kiran.shah", "Kiran Shah", "employee", "pd", ["aipf"], "Product Engineer"),
              ("divya.rao", "Divya Rao", "employee", "mk", ["intern"], "Marketing Executive"),
              ("sameer.patil", "Sameer Patil", "employee", "tr", ["intern"], "Trainer"),
              ("ravi.menon", "Ravi Menon", "auditor", "ad", [], "External Auditor (read-only)")]
    mem = {}
    for key, name, role, d, projects, title in people:
        u = user(db, key, name)
        db.flush()
        short = key.split(".")[0]
        mm = m.Membership(id=f"mem_a_{short}", user_id=u.id, tenant_id=t.id, role=role, department_id=deps[d], title=title)
        db.add(mm)
        mem[short] = mm.id
        for p in projects:
            db.add(m.ProjectAssignment(id=f"pas_a_{short}_{p}", tenant_id=t.id, membership_id=mm.id, project_id=prj[p], is_manager=role == "project_manager"))
    A = {}
    for key, name, typ, opening in [("bank", "HDFC Current Account", "bank", 1000000), ("petty", "Petty Cash", "petty_cash", 20000), ("card", "Corporate Credit Card", "credit_card", 0)]:
        db.add(m.Account(id=f"acc_a_{key}", tenant_id=t.id, name=name, type=typ, currency="INR", opening_minor=R(opening)))
        A[key] = f"acc_a_{key}"
    # campaign + channel values
    dims = {x.key: x for x in db.scalars(select(m.Dimension).where(m.Dimension.tenant_id == t.id))}
    camp, chan = {}, {}
    for k, n in [("intake", "Internship Intake Oct"), ("rite", "RITeSchool Admissions Drive"), ("webinar", "AI Product Launch Webinar"), ("diwali", "Diwali Referral Offer")]:
        db.add(m.DimensionValue(id=f"dv_camp_{k}", tenant_id=t.id, dimension_id=dims["campaign"].id, name=n))
        camp[k] = f"dv_camp_{k}"
    for k, n in [("fb", "Facebook"), ("google", "Google"), ("linkedin", "LinkedIn"), ("content", "Content / Organic")]:
        db.add(m.DimensionValue(id=f"dv_chan_{k}", tenant_id=t.id, dimension_id=dims["channel"].id, name=n))
        chan[k] = f"dv_chan_{k}"
    db.flush()
    S = Seeder(db, t)
    ad, fin = mem["anita"], mem["sanjay"]
    cd, ch = dims["campaign"].id, dims["channel"].id

    def inc(day, rupees, cat, desc, proj=None, merchant=None):
        S.tx(10, day, "income", rupees, cat, desc, A["bank"], fin, merchant=merchant, dept=deps["ad"], proj=prj[proj] if proj else None)

    def exp(day, rupees, cat, desc, proj, dept, sub=None, by=None, acct="bank", dims_=None, **kw):
        return S.tx(10, day, "expense", rupees, cat, desc, A[acct], by or fin, sub=sub, dept=deps[dept], proj=prj[proj], dims=dims_, **kw)

    # income: 6,00,000 + 1,50,000 + 1,00,000 = 8,50,000
    inc(3, 300000, "Client Revenue", "Invoice - Sunrise Realty (CRM build)", "crm", "Sunrise Realty")
    inc(8, 180000, "Client Revenue", "Invoice - Greenfield School (RITeSchool)", "rite", "Greenfield School Trust")
    inc(14, 120000, "Client Revenue", "Invoice - LittleSteps Preschools (ERP)", "pre", "LittleSteps Preschools")
    inc(5, 90000, "Internship Revenue", "Internship fees - batch 14", "intern")
    inc(19, 60000, "Internship Revenue", "Internship fees - batch 15", "intern")
    inc(10, 60000, "Product Revenue", "AI Product Factory subscriptions", "aipf")
    inc(21, 40000, "Product Revenue", "RITeSchool SaaS subscriptions", "rite")
    # employee costs 3,00,000
    exp(1, 180000, "Employee Costs", "Employee salary", "ops", "ad")
    exp(1, 60000, "Employee Costs", "Developer salary", "crm", "sw")
    exp(1, 30000, "Employee Costs", "QA and support salary", "rite", "sw")
    exp(1, 30000, "Employee Costs", "Intern stipends", "intern", "tr")
    # cloud + infrastructure 35,000
    exp(4, 12000, "Infrastructure", "Azure hosting", "rite", "sw", sub="Cloud Hosting", merchant="Microsoft Azure")
    exp(4, 5000, "Infrastructure", "VPS hosting", "crm", "sw", sub="Cloud Hosting")
    exp(6, 8000, "Infrastructure", "AWS S3 backup storage", "pre", "pd", sub="Cloud Hosting", merchant="AWS")
    exp(6, 10000, "Infrastructure", "CDN and domains", "aipf", "pd")
    # software 25,000
    exp(5, 3000, "Software Subscriptions", "GitHub subscription", "crm", "sw", merchant="GitHub")
    exp(5, 8000, "Software Subscriptions", "AI tools subscription", "aipf", "pd")
    exp(5, 6000, "Software Subscriptions", "Design tools licence", "pre", "pd")
    exp(5, 8000, "Software Subscriptions", "Project tracking and chat", "ops", "ad")
    # marketing 40,000 (tagged with campaign + channel)
    exp(7, 15000, "Marketing", "Facebook advertising", "intern", "mk", dims_={cd: camp["intake"], ch: chan["fb"]}, merchant="Meta Ads")
    exp(9, 12000, "Marketing", "Google Ads - school admissions", "rite", "mk", dims_={cd: camp["rite"], ch: chan["google"]}, merchant="Google Ads")
    exp(11, 8000, "Marketing", "LinkedIn ads - webinar", "aipf", "mk", dims_={cd: camp["webinar"], ch: chan["linkedin"]})
    exp(12, 5000, "Marketing", "Content and design for intake", "intern", "mk", dims_={cd: camp["intake"], ch: chan["content"]})
    # office and administration 30,000 (rent allocated across three projects)
    rent = exp(2, 20000, "Administration", "Office rent", "ops", "ad", sub="Office Expenses")
    for pk, amt in (("ops", 10000), ("intern", 6000), ("aipf", 4000)):
        db.add(m.TransactionSplit(id=f"spl_rent_{pk}", tenant_id=t.id, transaction_id=rent.id, department_id=deps["ad"], project_id=prj[pk], amount_minor=R(amt)))
    exp(3, 6000, "Utilities", "Internet and electricity", "ops", "ad")
    exp(13, 4000, "Administration", "Stationery and printing", "ops", "ad", sub="Office Expenses")
    # travel 20,000 - four paid employee claims with approval history
    claims = [("txn_aadi_c1", 15, 2500, "Client visit - Greenfield School", "arjun", "rite", "sw", "sneha"),
              ("txn_aadi_c2", 16, 6000, "Client visit - Sunrise Realty, Pune", "meera", "crm", "sw", "rohit"),
              ("txn_aadi_c3", 17, 7500, "Conference travel - AI summit", "kiran", "aipf", "pd", "rohit"),
              ("txn_aadi_c4", 18, 4000, "Trainer travel - college workshop", "sameer", "intern", "tr", "sneha")]
    for tid, day, amt, desc, who, p, d, pm in claims:
        x = S.tx(10, day, "expense", amt, "Travel", desc, A["bank"], mem[who], status="paid", dept=deps[d], proj=prj[p], reimbursable=True, tid=tid)
        db.add(m.ApprovalStep(tenant_id=t.id, transaction_id=tid, level_no=1, role="project_manager", status="approved", acted_by=mem[pm], reason="Approved - within project plan"))
        db.add(m.ApprovalStep(tenant_id=t.id, transaction_id=tid, level_no=2, role="finance", status="approved", acted_by=fin, reason="Receipts verified"))
        db.add(m.Reimbursement(tenant_id=t.id, transaction_id=tid, employee_membership_id=mem[who], amount_minor=R(amt), status="paid", paid_account_id=A["bank"], paid_by=fin))
    # training 25,000
    exp(8, 5000, "Training", "Training materials", "intern", "tr")
    exp(9, 12000, "Training", "Certification courses", "ops", "sw")
    exp(20, 8000, "Training", "Workshop venue", "intern", "tr")
    # equipment and maintenance 15,000
    exp(10, 4000, "Equipment", "Laptop accessories", "ops", "ad")
    exp(22, 6000, "Maintenance", "Laptop repair", "ops", "ad")
    exp(23, 5000, "Maintenance", "AC servicing", "ops", "ad")
    # other 10,000
    exp(24, 4000, "Other Expenses", "Team lunch", "ops", "ad")
    exp(24, 1500, "Other Expenses", "Courier charges", "ops", "ad")
    exp(25, 2000, "Other Expenses", "Bank charges", "ops", "ad")
    exp(25, 2500, "Other Expenses", "Client gifts", "ops", "ad")
    # open claims (NOT in the monthly summary: they are not yet approved/paid)
    def claim(tid, day, amt, desc, who, p, d, status, steps, cat="Travel", reason=None):
        S.tx(10, day, "expense", amt, cat, desc, None, mem[who], status=status, dept=deps[d], proj=prj[p], reimbursable=True, tid=tid)
        for i, (role, st, by) in enumerate(steps, 1):
            db.add(m.ApprovalStep(tenant_id=t.id, transaction_id=tid, level_no=i, role=role, status=st, acted_by=mem[by] if by else None, reason=reason if st == "rejected" else None))
    claim("txn_aadi_p1", 28, 1800, "Client meeting cab fares", "arjun", "rite", "sw", "submitted", [("project_manager", "pending", None), ("finance", "pending", None)])
    claim("txn_aadi_p2", 29, 3200, "Online course for CRM team", "meera", "crm", "sw", "pm_approved", [("project_manager", "approved", "rohit"), ("finance", "pending", None)], cat="Training")
    claim("txn_aadi_p3", 30, 9000, "Event stall deposit", "divya", "intern", "mk", "submitted", [("project_manager", "pending", None), ("finance", "pending", None)], cat="Marketing")
    claim("txn_aadi_p4", 27, 2400, "Hackathon travel", "kiran", "aipf", "pd", "verified", [("project_manager", "approved", "rohit"), ("finance", "approved", "sanjay")])
    claim("txn_aadi_p5", 26, 600, "Team snacks", "sameer", "intern", "tr", "rejected", [("finance", "rejected", "sanjay")], cat="Other Expenses", reason="Not a reimbursable item under policy")
    for tid in ("txn_aadi_p1", "txn_aadi_p2", "txn_aadi_p3", "txn_aadi_p4", "txn_aadi_p5"):
        db.add(m.AuditEvent(tenant_id=t.id, actor_name="Seed", entity="transaction", entity_id=tid, action="submitted", detail={"note": "sample data"}))
    # budgets for October
    P = lambda k: prj[k]  # noqa: E731
    for name, scope, sid, amt, dim in [("Organization operating budget", "overall", None, 550000, None), ("Software Development", "department", deps["sw"], 200000, None),
                                       ("Digital Marketing", "department", deps["mk"], 50000, None), ("Administration", "department", deps["ad"], 260000, None),
                                       ("Multitenant CRM", "project", P("crm"), 90000, None), ("RITeSchool", "project", P("rite"), 60000, None),
                                       ("Internship Program", "project", P("intern"), 110000, None), ("AI Product Factory", "project", P("aipf"), 45000, None),
                                       ("Campaign: Internship Intake Oct", "dimension", camp["intake"], 25000, cd), ("Campaign: RITeSchool Admissions Drive", "dimension", camp["rite"], 15000, cd),
                                       ("Campaign: AI Product Launch Webinar", "dimension", camp["webinar"], 10000, cd)]:
        db.add(m.Budget(id="bud_a_" + name.lower().replace(" ", "_").replace(":", "")[:30], tenant_id=t.id, name=name, scope=scope, scope_id=sid, dimension_id=dim, period="2026-10", amount_minor=R(amt)))
    for i, (n, amt, day, c) in enumerate([("Azure hosting", 12000, 4, "Infrastructure"), ("Office rent", 20000, 2, "Administration"), ("GitHub subscription", 3000, 5, "Software Subscriptions")]):
        db.add(m.Recurring(id=f"rec_a_{i}", tenant_id=t.id, description=n, amount_minor=R(amt), day_of_month=day, category_id=S.cat[c].id))
    # imported growth data: leads/customers for two of the three campaigns (webinar has none -> shown as unavailable)
    b = m.ImportBatch(id="imp_a_oct", tenant_id=t.id, kind="growth_metrics", source="Manual CSV (sample)", period="2026-10", currency="INR", attribution_method="Last touch, self-reported", status="imported", rows_ok=2, created_by=db.get(m.Membership, fin).user_id)
    db.add(b)
    db.flush()
    db.add(m.GrowthMetric(id="gm_a_1", tenant_id=t.id, batch_id=b.id, campaign_value_id=camp["intake"], leads=120, customers=16))
    db.add(m.GrowthMetric(id="gm_a_2", tenant_id=t.id, batch_id=b.id, campaign_value_id=camp["rite"], leads=40, customers=None))
    db.flush()
    return t, mem


def run(do_reset=False):
    if ENV == "production":
        raise SystemExit("Refusing to seed a production environment")
    init_db()
    with SessionLocal() as db:
        if do_reset:
            reset(db)
        elif db.get(m.Tenant, PERSONAL_ID):
            print("Demo data already present - nothing to do (use --reset to rebuild).")
            return
        ensure_catalogue(db)
        db.add(m.User(id="usr_platform", email="platform.admin" + DOMAIN, name="Platform Admin", password_hash=hash_password(DEMO_PASSWORD), is_platform_admin=True)) \
            if not db.get(m.User, "usr_platform") else None
        pt, _ = seed_personal(db)
        bt, bm = seed_business(db)
        db.commit()
        for tenant, owner_mem in ((pt, "mem_p_rahul"), (bt, bm["anita"])):
            mem = db.get(m.Membership, owner_mem)
            ctx = Ctx(db.get(m.User, mem.user_id), tenant, mem, set(ROLE_PERMISSIONS[mem.role]), set(), db)
            evaluate_budget_alerts(db, tenant, lambda c=ctx: c)
        db.commit()
    print("Seeded: Rahul Sharma household (personal) and Aadi Technology (business).")


if __name__ == "__main__":
    run("--reset" in sys.argv)
