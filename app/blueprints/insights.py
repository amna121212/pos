"""Stored sales insight: deterministic snapshots and rule-written recommendations.

No language model is called. Every figure is a stored SQL aggregate over the
labelled dataset, and the page says which dataset that is.
"""
from flask import Blueprint, abort, flash, redirect, render_template, url_for
from sqlalchemy import func, select

from app import db
from app.intelligence_models import AiAnalysisRun, AiRecommendation, ProductPerformanceSnapshot
from app.models import Branch, Product
from app.security import branch_required, context, permission_required
from app.services import analytics

bp = Blueprint("insights", __name__, url_prefix="/insights")

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@bp.get("")
@permission_required("ai.view")
@branch_required
def index():
    ctx = context()
    run = db.session.scalar(
        select(AiAnalysisRun)
        .where(AiAnalysisRun.business_id == ctx.business_id)
        .order_by(AiAnalysisRun.id.desc())
        .limit(1)
    )

    recommendations = []
    leaders = []
    if run is not None:
        recommendations = sorted(
            db.session.scalars(
                select(AiRecommendation).where(AiRecommendation.run_id == run.id)
            ).all(),
            key=lambda row: PRIORITY_ORDER.get(row.priority, 9),
        )
        rows = db.session.execute(
            select(
                Product.name,
                Product.sku,
                func.sum(ProductPerformanceSnapshot.qty_sold).label("qty"),
                func.sum(ProductPerformanceSnapshot.revenue).label("revenue"),
                func.sum(ProductPerformanceSnapshot.estimated_gross_profit).label("profit"),
            )
            .join(Product, Product.id == ProductPerformanceSnapshot.product_id)
            .where(ProductPerformanceSnapshot.run_id == run.id)
            .group_by(Product.name, Product.sku)
            .order_by(func.sum(ProductPerformanceSnapshot.estimated_gross_profit).desc())
            .limit(10)
        ).all()
        leaders = [
            {"name": row[0], "sku": row[1], "qty": row[2], "revenue": row[3], "profit": row[4]}
            for row in rows
        ]

    return render_template(
        "insights/index.html",
        run=run,
        recommendations=recommendations,
        leaders=leaders,
        can_refresh=True,
    )


@bp.post("/refresh")
@permission_required("ai.view")
@branch_required
def refresh():
    ctx = context()
    start, end = analytics.history_bounds()
    try:
        analytics.refresh_snapshots(
            ctx.business,
            period_start=start,
            period_end=end,
            owner_user_id=ctx.user.id,
        )
        db.session.commit()
        flash("Analysis refreshed from stored transactions.", "success")
    except Exception:
        db.session.rollback()
        abort(500)
    return redirect(url_for("insights.index"))
