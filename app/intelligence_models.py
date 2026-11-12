"""Deterministic sales snapshots, rule-based recommendations and dataset provenance.

Grok is not called from these tables. A later feature can explain the numbers
that are already stored here. The engine column says who produced the row.
"""
from app import db
from app.timeutil import utcnow


class DatasetManifest(db.Model):
    """States where a dataset came from and whether generation has finished."""

    __tablename__ = "dataset_manifests"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), nullable=False, unique=True)
    category = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    source_note = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="recorded")
    generated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.CheckConstraint(
            "category IN ('MANUALLY_CURATED','PUBLIC_SOURCE','APPLICATION_GENERATED','SYNTHETIC_HISTORICAL')",
            name="ck_dataset_category",
        ),
        db.CheckConstraint("status IN ('recorded','running','complete')", name="ck_dataset_status"),
    )


class AiAnalysisRun(db.Model):
    """One reproducible analytics pass over a labelled dataset."""

    __tablename__ = "ai_analysis_runs"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    run_code = db.Column(db.String(60), nullable=False, unique=True)
    engine = db.Column(db.String(40), nullable=False)
    dataset_code = db.Column(db.String(60), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="complete")
    summary = db.Column(db.String(400), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.CheckConstraint("engine IN ('deterministic_sql','rule_engine')", name="ck_analysis_engine"),
        db.CheckConstraint("status IN ('running','complete','failed')", name="ck_analysis_status"),
        db.CheckConstraint("period_end >= period_start", name="ck_analysis_period"),
    )


class ProductPerformanceSnapshot(db.Model):
    """Branch-level product totals for one analysis run. Figures are estimates from the labelled dataset."""

    __tablename__ = "product_performance_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("ai_analysis_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    qty_sold = db.Column(db.Numeric(14, 3), nullable=False)
    revenue = db.Column(db.Numeric(14, 2), nullable=False)
    estimated_cost = db.Column(db.Numeric(14, 2), nullable=False)
    estimated_gross_profit = db.Column(db.Numeric(14, 2), nullable=False)
    __table_args__ = (
        db.UniqueConstraint("run_id", "branch_id", "product_id", name="uq_snapshot_run_branch_product"),
    )


class AiRecommendation(db.Model):
    """A rule-written suggestion. source is rule_engine until a later Grok explanation layer exists."""

    __tablename__ = "ai_recommendations"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("ai_analysis_runs.id", ondelete="RESTRICT"), nullable=False, index=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"))
    source = db.Column(db.String(40), nullable=False, default="rule_engine")
    recommendation_code = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(140), nullable=False)
    detail = db.Column(db.String(400), nullable=False)
    priority = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.CheckConstraint("source IN ('rule_engine')", name="ck_recommendation_source"),
        db.CheckConstraint("priority IN ('low','medium','high')", name="ck_recommendation_priority"),
    )


class RecommendationFeedback(db.Model):
    """A person's response to a stored recommendation. One row per recommendation in this demo."""

    __tablename__ = "recommendation_feedback"
    id = db.Column(db.Integer, primary_key=True)
    recommendation_id = db.Column(
        db.Integer, db.ForeignKey("ai_recommendations.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"))
    decision = db.Column(db.String(20), nullable=False)
    note = db.Column(db.String(240), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.CheckConstraint("decision IN ('accepted','dismissed','noted')", name="ck_feedback_decision"),
    )
