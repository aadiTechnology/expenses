"""Global configuration templates. Applying one COPIES it into tenant rows, so later template edits
never overwrite a customer's configuration (PRD section 8)."""
from sqlalchemy.orm import Session as DbSession

from . import models as m

PERSONAL_CATS = [
    ("Household", ["Milk"], "home", "#8d6e63", "milk"), ("Groceries", ["Vegetables"], "shopping_basket", "#43a047", "grocery vegetable"),
    ("Food and Restaurants", [], "restaurant", "#ef6c00", "restaurant lunch dinner"), ("Transport", ["Petrol"], "directions_car", "#1e88e5", "petrol fuel taxi"),
    ("Healthcare", [], "medical_services", "#e53935", "doctor medicine hospital"), ("Education", [], "school", "#5e35b1", "school fees tuition"),
    ("Housing", [], "apartment", "#6d4c41", "rent"), ("Utilities", [], "bolt", "#fdd835", "electricity internet wifi"),
    ("Shopping", [], "local_mall", "#d81b60", "clothing cloth"), ("Entertainment", [], "movie", "#8e24aa", "movie"),
    ("Travel", [], "flight", "#00897b", "flight hotel train"), ("Insurance", [], "shield", "#546e7a", "insurance premium"),
    ("Loan Repayment", [], "account_balance", "#455a64", "emi loan"), ("Personal Care", [], "spa", "#ec407a", "salon"),
    ("Miscellaneous", [], "category", "#757575", ""),
]
PERSONAL_INCOME = [("Salary", "salary"), ("Other Income", "interest gift")]
BUSINESS_CATS = [
    ("Employee Costs", [], "groups", "#3949ab", "salary stipend"), ("Infrastructure", ["Cloud Hosting"], "cloud", "#1e88e5", "azure hosting vps server"),
    ("Software Subscriptions", [], "apps", "#8e24aa", "github subscription tools"), ("Marketing", [], "campaign", "#e53935", "ads advertising facebook google"),
    ("Travel", [], "flight", "#00897b", "client visit flight hotel cab"), ("Training", [], "school", "#5e35b1", "training materials"),
    ("Administration", ["Office Expenses"], "business", "#6d4c41", "office rent stationery"), ("Equipment", [], "laptop", "#546e7a", "laptop accessories"),
    ("Professional Services", [], "gavel", "#455a64", "legal audit consultant"), ("Maintenance", [], "build", "#795548", "repair maintenance"),
    ("Utilities", [], "bolt", "#fdd835", "electricity internet"), ("Client Expenses", [], "handshake", "#ef6c00", "client"),
    ("Other Expenses", [], "category", "#757575", ""),
]
BUSINESS_INCOME = [("Client Revenue", "client invoice"), ("Internship Revenue", "internship fee"), ("Product Revenue", "subscription product")]

TEMPLATES = {
    "personal": {"edition": "personal", "label": "Personal / Family", "terminology": {"member": "Family member", "group": "Household"},
                 "dashboard_widgets": ["kpis", "category_spend", "trend", "recent", "budgets", "insights", "goals"],
                 "features": ["family", "goals", "accounts"], "mandatory_fields": []},
    "it_company": {"edition": "business", "label": "IT Company", "terminology": {"member": "Employee", "group": "Department"},
                   "dashboard_widgets": ["kpis", "department_spend", "project_spend", "pending", "budgets", "category_spend", "trend", "insights", "growth"],
                   "features": ["departments", "projects", "approvals", "reimbursements"], "mandatory_fields": ["project"]},
    "education": {"edition": "business", "label": "Education (branches & school operations)", "terminology": {"member": "Staff", "group": "Branch"},
                  "dashboard_widgets": ["kpis", "department_spend", "pending", "budgets", "category_spend", "trend", "insights"],
                  "features": ["departments", "approvals", "reimbursements"], "mandatory_fields": []},
}


def apply_template(db: DbSession, tenant: m.Tenant, template_code: str, with_growth_dims: bool = False):
    tpl = TEMPLATES[template_code]
    tenant.template_code = template_code
    tenant.config = {k: tpl[k] for k in ("terminology", "dashboard_widgets", "features", "mandatory_fields")} | {"template_label": tpl["label"]}
    personal = tpl["edition"] == "personal"
    for name, subs, icon, color, kw in (PERSONAL_CATS if personal else BUSINESS_CATS):
        c = m.Category(tenant_id=tenant.id, name=name, kind="expense", icon=icon, color=color, keywords=kw.split())
        db.add(c)
        db.flush()
        for s in subs:
            db.add(m.Category(tenant_id=tenant.id, name=s, parent_id=c.id, kind="expense", icon=icon, color=color))
    for name, kw in (PERSONAL_INCOME if personal else BUSINESS_INCOME):
        db.add(m.Category(tenant_id=tenant.id, name=name, kind="income", icon="payments", color="#2e7d32", keywords=kw.split()))
    db.add(m.Account(tenant_id=tenant.id, name="Cash" if personal else "Petty Cash", type="cash" if personal else "petty_cash", currency=tenant.currency))
    if template_code == "it_company":
        db.add(m.ApprovalPolicy(tenant_id=tenant.id, name="Small claims: Finance only", min_minor=0, max_minor=100000, levels=["finance"]))
        db.add(m.ApprovalPolicy(tenant_id=tenant.id, name="Standard: Project Manager then Finance", min_minor=100000, levels=["project_manager", "finance"]))
    elif template_code == "education":
        db.add(m.ApprovalPolicy(tenant_id=tenant.id, name="Department Manager then Finance", min_minor=0, levels=["department_manager", "finance"]))
    if with_growth_dims:
        add_growth_dimensions(db, tenant)


def add_growth_dimensions(db: DbSession, tenant: m.Tenant):
    for key, name in (("campaign", "Campaign"), ("channel", "Channel")):
        db.add(m.Dimension(tenant_id=tenant.id, key=key, name=name, pillar="P2"))
