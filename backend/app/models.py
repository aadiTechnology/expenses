"""SpendOS data model. One shared transaction engine; industry differences live in configuration
rows (categories, dimensions, policies, budgets, tenant.config), never in industry-specific tables.
Money is stored as integer minor units (paise) so no floating point ever touches a stored amount."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


def pk(prefix: str):
    return mapped_column(String(40), primary_key=True, default=lambda: uid(prefix))


def tenant_fk():
    return mapped_column(String(40), ForeignKey("tenants.id"), index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = pk("usr_")
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Session(Base):
    __tablename__ = "sessions"
    jti: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    token: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = pk("ten_")
    name: Mapped[str] = mapped_column(String(200))
    edition: Mapped[str] = mapped_column(String(20))  # personal | business
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    plan_code: Mapped[str] = mapped_column(String(40))
    template_code: Mapped[str] = mapped_column(String(40))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # tenant copy of the template
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id"),)
    id: Mapped[str] = pk("mem_")
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id"), index=True)
    tenant_id: Mapped[str] = tenant_fk()
    role: Mapped[str] = mapped_column(String(40))
    department_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    notif_prefs: Mapped[dict] = mapped_column(JSON, default=dict)


class ProjectAssignment(Base):
    __tablename__ = "project_assignments"
    id: Mapped[str] = pk("pas_")
    tenant_id: Mapped[str] = tenant_fk()
    membership_id: Mapped[str] = mapped_column(String(40), ForeignKey("memberships.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    is_manager: Mapped[bool] = mapped_column(Boolean, default=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    permission: Mapped[str] = mapped_column(String(60))


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[str] = pk("dep_")
    tenant_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = pk("prj_")
    tenant_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120))
    department_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CostCentre(Base):
    __tablename__ = "cost_centres"
    id: Mapped[str] = pk("cc_")
    tenant_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120))


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = pk("acc_")
    tenant_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))  # cash|bank|upi|credit_card|wallet|petty_cash|other
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    opening_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[str] = pk("cat_")
    tenant_id: Mapped[str] = tenant_fk()
    parent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), default="expense")  # expense|income|both
    icon: Mapped[str] = mapped_column(String(40), default="label")
    color: Mapped[str] = mapped_column(String(9), default="#5c6bc0")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    required_fields: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["project","description"]
    keywords: Mapped[list] = mapped_column(JSON, default=list)  # used by AI suggestion


class Dimension(Base):
    """Configurable business dimension such as campaign, channel or initiative (FR-15)."""
    __tablename__ = "dimensions"
    id: Mapped[str] = pk("dim_")
    tenant_id: Mapped[str] = tenant_fk()
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    pillar: Mapped[str | None] = mapped_column(String(4), nullable=True)


class DimensionValue(Base):
    __tablename__ = "dimension_values"
    id: Mapped[str] = pk("dv_")
    tenant_id: Mapped[str] = tenant_fk()
    dimension_id: Mapped[str] = mapped_column(String(40), ForeignKey("dimensions.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = pk("txn_")
    tenant_id: Mapped[str] = tenant_fk()
    seq: Mapped[int] = mapped_column(Integer, default=0)
    date: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[str] = mapped_column(String(14))  # income|expense|transfer|refund|reimbursement
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    category_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    subcategory_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    to_account_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # membership id
    member_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # whose expense
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    cost_centre_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    department_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)  # {dimension_id: value_id}
    status: Mapped[str] = mapped_column(String(14), default="posted", index=True)
    reimbursable: Mapped[bool] = mapped_column(Boolean, default=False)
    refund_of_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recurring_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # provenance, kept apart from the values
    sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"
    id: Mapped[str] = pk("spl_")
    tenant_id: Mapped[str] = tenant_fk()
    transaction_id: Mapped[str] = mapped_column(String(40), ForeignKey("transactions.id"), index=True)
    department_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    member_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # family allocation of a shared expense
    amount_minor: Mapped[int] = mapped_column(BigInteger)


class Attachment(Base):
    __tablename__ = "transaction_attachments"
    id: Mapped[str] = pk("att_")
    tenant_id: Mapped[str] = tenant_fk()
    transaction_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(400))
    uploaded_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ApprovalPolicy(Base):
    __tablename__ = "approval_policies"
    id: Mapped[str] = pk("pol_")
    tenant_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(120))
    min_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    max_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    levels: Mapped[list] = mapped_column(JSON, default=list)  # ["project_manager","finance"]
    department_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ApprovalStep(Base):
    __tablename__ = "approval_instances"
    id: Mapped[str] = pk("stp_")
    tenant_id: Mapped[str] = tenant_fk()
    transaction_id: Mapped[str] = mapped_column(String(40), ForeignKey("transactions.id"), index=True)
    level_no: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|approved|rejected
    acted_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(400), nullable=True)


class Reimbursement(Base):
    __tablename__ = "reimbursement_records"
    id: Mapped[str] = pk("rei_")
    tenant_id: Mapped[str] = tenant_fk()
    transaction_id: Mapped[str] = mapped_column(String(40), ForeignKey("transactions.id"), unique=True)
    employee_membership_id: Mapped[str] = mapped_column(String(40))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|paid
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_account_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    paid_by: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[str] = pk("bud_")
    tenant_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(160))
    scope: Mapped[str] = mapped_column(String(14))  # overall|department|project|category|dimension
    scope_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dimension_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    thresholds: Mapped[list] = mapped_column(JSON, default=lambda: [50, 75, 90, 100])


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    id: Mapped[str] = pk("goal_")
    tenant_id: Mapped[str] = tenant_fk()
    name: Mapped[str] = mapped_column(String(160))
    target_minor: Mapped[int] = mapped_column(BigInteger)
    saved_minor: Mapped[int] = mapped_column(BigInteger, default=0)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Recurring(Base):
    __tablename__ = "recurring_transactions"
    id: Mapped[str] = pk("rec_")
    tenant_id: Mapped[str] = tenant_fk()
    description: Mapped[str] = mapped_column(String(200))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    day_of_month: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "dedupe_key"),)
    id: Mapped[str] = pk("ntf_")
    tenant_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500), default="")
    dedupe_key: Mapped[str] = mapped_column(String(120))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = pk("aud_")
    tenant_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AiExtraction(Base):
    """Provenance for AI-suggested values. Suggestions never become transactions without confirmation."""
    __tablename__ = "ai_extractions"
    id: Mapped[str] = pk("ext_")
    tenant_id: Mapped[str] = tenant_fk()
    user_id: Mapped[str] = mapped_column(String(40))
    source_type: Mapped[str] = mapped_column(String(20))  # voice|receipt|register
    source_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    attachment_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    items: Mapped[list] = mapped_column(JSON, default=list)
    engine: Mapped[str] = mapped_column(String(60), default="rules-v1")
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|confirmed|discarded
    created_txn_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class InsightReview(Base):
    """Acknowledge / dismiss state of an advisory insight or anomaly flag, with who and when."""
    __tablename__ = "insight_reviews"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)
    id: Mapped[str] = pk("rev_")
    tenant_id: Mapped[str] = tenant_fk()
    key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(14))  # acknowledged|dismissed
    by_user_id: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = pk("imp_")
    tenant_id: Mapped[str] = tenant_fk()
    kind: Mapped[str] = mapped_column(String(20))  # growth_metrics
    source: Mapped[str] = mapped_column(String(120))
    period: Mapped[str] = mapped_column(String(7))
    currency: Mapped[str] = mapped_column(String(3))
    attribution_method: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(12))  # imported|rejected
    rows_ok: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class GrowthMetric(Base):
    __tablename__ = "growth_metrics"
    id: Mapped[str] = pk("gm_")
    tenant_id: Mapped[str] = tenant_fk()
    batch_id: Mapped[str] = mapped_column(String(40), ForeignKey("import_batches.id"), index=True)
    campaign_value_id: Mapped[str] = mapped_column(String(40))
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    leads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# --- product catalogue and entitlements (FR-13, FR-14) -------------------------------------------
class Module(Base):
    __tablename__ = "modules"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300), default="")
    primary_pillar: Mapped[str] = mapped_column(String(2))  # P1|P2|P3
    secondary_pillar: Mapped[str | None] = mapped_column(String(2), nullable=True)
    priority: Mapped[str] = mapped_column(String(2), default="P0")
    lifecycle: Mapped[str] = mapped_column(String(14), default="active")
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    entitlement_key: Mapped[str] = mapped_column(String(60))


class Plan(Base):
    __tablename__ = "subscription_plans"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    edition: Mapped[str] = mapped_column(String(20))
    price_note: Mapped[str] = mapped_column(String(120), default="")


class PlanModule(Base):
    __tablename__ = "plan_modules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_code: Mapped[str] = mapped_column(String(40), index=True)
    module_code: Mapped[str] = mapped_column(String(40))


class TenantEntitlement(Base):
    """Explicit override on top of the plan (enable, disable, or time-limited)."""
    __tablename__ = "feature_entitlements"
    __table_args__ = (UniqueConstraint("tenant_id", "module_code"),)
    id: Mapped[str] = pk("ent_")
    tenant_id: Mapped[str] = tenant_fk()
    module_code: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
