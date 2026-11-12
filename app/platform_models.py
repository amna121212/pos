"""Platform, tenancy configuration, roles and tax rules.

These tables sit beside the Phase 1 master data. A restaurant still lives in
one shared database; business_id is what keeps tenants apart.
"""
from app import db
from app.timeutil import utcnow


class SubscriptionPlan(db.Model):
    """Sellable POS plan. Fees are coursework demo amounts in PKR."""

    __tablename__ = "subscription_plans"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    name = db.Column(db.String(80), nullable=False)
    monthly_fee_pkr = db.Column(db.Numeric(12, 2), nullable=False)
    max_branches = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(240), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    __table_args__ = (
        db.CheckConstraint("monthly_fee_pkr >= 0", name="ck_plan_fee_nonnegative"),
        db.CheckConstraint("max_branches > 0", name="ck_plan_branches_positive"),
    )


class BusinessSubscription(db.Model):
    """The current plan for one business. Plan changes update this row and write an audit event."""

    __tablename__ = "business_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, unique=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    started_on = db.Column(db.Date, nullable=False)
    notes = db.Column(db.String(240))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        db.CheckConstraint("status IN ('trial','active','past_due','cancelled')", name="ck_subscription_status"),
    )


class BusinessSetting(db.Model):
    """Per-tenant currency, timezone, trading start and margin guardrail."""

    __tablename__ = "business_settings"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, unique=True)
    currency_code = db.Column(db.String(3), nullable=False, default="PKR")
    timezone_name = db.Column(db.String(64), nullable=False, default="Asia/Karachi")
    # Fictional operating start used by the synthetic history. Distinct from businesses.created_at.
    trading_since = db.Column(db.Date, nullable=False)
    receipt_header = db.Column(db.String(160), nullable=False)
    receipt_footer = db.Column(db.String(240), nullable=False)
    allow_negative_stock = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    min_gross_margin_pct = db.Column(db.Numeric(5, 2), nullable=False, default=15)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        db.CheckConstraint("currency_code = 'PKR'", name="ck_settings_currency_pkr"),
        db.CheckConstraint("min_gross_margin_pct >= 0 AND min_gross_margin_pct < 100", name="ck_settings_margin"),
    )


class BranchOperatingHour(db.Model):
    """Weekly opening hours for one branch. weekday 0 is Monday."""

    __tablename__ = "branch_operating_hours"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    weekday = db.Column(db.Integer, nullable=False)
    opens_at = db.Column(db.Time, nullable=False)
    closes_at = db.Column(db.Time, nullable=False)
    is_closed = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    __table_args__ = (
        db.UniqueConstraint("branch_id", "weekday", name="uq_branch_weekday_hours"),
        db.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_weekday_range"),
        db.CheckConstraint("is_closed OR opens_at < closes_at", name="ck_hours_order"),
    )


class Role(db.Model):
    """Named job role. business_users.role stores the same code."""

    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), nullable=False, unique=True)
    label = db.Column(db.String(80), nullable=False)
    scope = db.Column(db.String(20), nullable=False)
    __table_args__ = (
        db.CheckConstraint("scope IN ('platform','business','branch')", name="ck_role_scope"),
    )


class Permission(db.Model):
    """One action the server may allow, such as order.refund."""

    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), nullable=False, unique=True)
    label = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(240), nullable=False)


class RolePermission(db.Model):
    """Grants one permission to one role."""

    __tablename__ = "role_permissions"
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (
        db.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )


class TaxRule(db.Model):
    """Demo tax rate for a business. These rates are illustrative, not FBR advice."""

    __tablename__ = "tax_rules"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = db.Column(db.String(40), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    rate_percent = db.Column(db.Numeric(6, 3), nullable=False)
    applies_to = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    is_demo_rate = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    notes = db.Column(db.String(300), nullable=False)
    __table_args__ = (
        db.UniqueConstraint("business_id", "code", name="uq_tax_rule_business_code"),
        db.CheckConstraint("rate_percent >= 0 AND rate_percent < 100", name="ck_tax_rate_range"),
        db.CheckConstraint("applies_to IN ('menu_item','retail_item','all')", name="ck_tax_applies_to"),
    )
