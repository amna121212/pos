"""The landing page: today's trading, what needs attention, and links into detail."""
from datetime import datetime, timedelta

from flask import Blueprint, render_template
from sqlalchemy import func, select

from app import db
from app.models import BranchProduct, Business, Product
from app.order_models import KitchenTicket, RestaurantOrder
from app.security import business_required, context
from app.services import reporting
from app.services.reporting import Filters, make_period
from app.timeutil import PAKISTAN

bp = Blueprint("dashboard", __name__)


@bp.get("/")
@business_required
def index():
    ctx = context()
    business_id = ctx.business_id
    scope = ctx.allowed_branch_ids
    today = datetime.now(PAKISTAN).date()

    period = make_period(today, today)
    filters = Filters(business_id=business_id, branch_ids=scope, limit=8)

    summary = reporting.today_summary(business_id, scope)
    payments = reporting.payment_breakdown(filters, period)
    top_products = reporting.product_performance(filters, period)
    low = reporting.low_stock(business_id, ctx.branch_id, limit=6) if ctx.branch_id else []
    recent = reporting.recent_orders(business_id, scope, limit=8)
    branches = reporting.branch_comparison(filters, period) if len(ctx.branches) > 1 else []

    last_week = make_period(today - timedelta(days=6), today)
    week_series = reporting.sales_series(
        Filters(business_id=business_id, branch_ids=scope), last_week, "day"
    )
    week_total = sum((row["net_sales"] for row in week_series), 0)

    kitchen_queue = int(
        db.session.scalar(
            select(func.count())
            .select_from(KitchenTicket)
            .join(RestaurantOrder, RestaurantOrder.id == KitchenTicket.order_id)
            .where(
                RestaurantOrder.business_id == business_id,
                RestaurantOrder.branch_id.in_(scope),
                KitchenTicket.status.in_(("queued", "preparing", "ready")),
            )
        )
        or 0
    )
    product_count = int(
        db.session.scalar(
            select(func.count())
            .select_from(BranchProduct)
            .join(Product, Product.id == BranchProduct.product_id)
            .where(
                BranchProduct.business_id == business_id,
                BranchProduct.branch_id == ctx.branch_id,
                Product.is_active.is_(True),
            )
        )
        or 0
    ) if ctx.branch_id else 0

    return render_template(
        "dashboard/index.html",
        today=today,
        summary=summary,
        payments=payments,
        top_products=top_products,
        low_stock=low,
        recent=recent,
        branches=branches,
        week_series=week_series,
        week_total=week_total,
        kitchen_queue=kitchen_queue,
        product_count=product_count,
    )
