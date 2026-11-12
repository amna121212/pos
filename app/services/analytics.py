"""Deterministic sales and stock figures for a later explanation layer.

These functions do not call Grok and do not invent numbers. They aggregate
rows already stored in retail_pos_db. Historical patterns are synthetic.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import extract, func, select

from app import db
from app.intelligence_models import (
    AiAnalysisRun,
    AiRecommendation,
    ProductPerformanceSnapshot,
    RecommendationFeedback,
)
from app.inventory_models import BranchStock, InventoryItem, StockMovement
from app.models import Branch, Business, BusinessUser, Product
from app.money import money, quantity
from app.operations_models import SalesReturn, SalesReturnLine
from app.order_models import OrderItem, RestaurantOrder
from app.services.audit import write_audit
from app.services.recipes import recipe_requirements

HISTORY_DATASET = "SYNTHETIC_HISTORY_V1"
CONSUMPTION_TYPES = ("recipe_consumption", "retail_sale", "exchange_issue")


def _paid_filter(business_id):
    return (
        RestaurantOrder.business_id == business_id,
        RestaurantOrder.status == "paid",
        RestaurantOrder.dataset_code == HISTORY_DATASET,
    )


def top_products(business_id, *, limit=10):
    """Highest quantity paid items in the synthetic history."""
    rows = db.session.execute(
        select(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity).label("qty"),
            func.sum(OrderItem.line_total).label("revenue"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(RestaurantOrder, RestaurantOrder.id == OrderItem.order_id)
        .where(*_paid_filter(business_id))
        .group_by(Product.id, Product.name)
        .order_by(func.sum(OrderItem.quantity).desc(), Product.name)
        .limit(limit)
    ).all()
    return [
        {"product_id": row.id, "name": row.name, "qty": quantity(row.qty), "line_revenue": money(row.revenue)}
        for row in rows
    ]


def branch_comparison(business_id):
    """Paid-order revenue, average order value and order count by branch."""
    rows = db.session.execute(
        select(
            Branch.id,
            Branch.code,
            Branch.name,
            func.count(RestaurantOrder.id).label("orders"),
            func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total).label("net_sales"),
        )
        .join(RestaurantOrder, RestaurantOrder.branch_id == Branch.id)
        .where(*_paid_filter(business_id))
        .group_by(Branch.id, Branch.code, Branch.name)
        .order_by(Branch.code)
    ).all()
    result = []
    for row in rows:
        orders = int(row.orders or 0)
        net_sales = money(row.net_sales or 0)
        average = money(net_sales / orders) if orders else money(0)
        result.append(
            {
                "branch_id": row.id,
                "code": row.code,
                "name": row.name,
                "orders": orders,
                "net_sales": net_sales,
                "average_order_value": average,
            }
        )
    return result


def busiest_hours(business_id):
    """Paid order counts by hour in Asia/Karachi."""
    hour = extract("hour", func.timezone("Asia/Karachi", RestaurantOrder.created_at))
    rows = db.session.execute(
        select(hour.label("hour"), func.count(RestaurantOrder.id))
        .where(*_paid_filter(business_id))
        .group_by(hour)
        .order_by(hour)
    ).all()
    return [{"hour": int(row.hour), "orders": int(row[1])} for row in rows]


def busiest_weekdays(business_id):
    """PostgreSQL DOW: 0 is Sunday. Counts are paid synthetic orders."""
    weekday = extract("dow", func.timezone("Asia/Karachi", RestaurantOrder.created_at))
    rows = db.session.execute(
        select(weekday.label("weekday"), func.count(RestaurantOrder.id))
        .where(*_paid_filter(business_id))
        .group_by(weekday)
        .order_by(weekday)
    ).all()
    return [{"weekday": int(row.weekday), "orders": int(row[1])} for row in rows]


def monthly_net_sales(business_id):
    month = func.date_trunc("month", func.timezone("Asia/Karachi", RestaurantOrder.created_at))
    rows = db.session.execute(
        select(month.label("month"), func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total))
        .where(*_paid_filter(business_id))
        .group_by(month)
        .order_by(month)
    ).all()
    return [{"month": row.month.date(), "net_sales": money(row[1] or 0)} for row in rows]


def branch_monthly_summary(business_id):
    """Main reporting query used by the performance check."""
    month = func.date_trunc("month", func.timezone("Asia/Karachi", RestaurantOrder.created_at))
    rows = db.session.execute(
        select(
            Branch.code,
            month.label("month"),
            func.count(RestaurantOrder.id),
            func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total),
        )
        .join(RestaurantOrder, RestaurantOrder.branch_id == Branch.id)
        .where(*_paid_filter(business_id))
        .group_by(Branch.code, month)
        .order_by(Branch.code, month)
    ).all()
    return [
        {"branch": row.code, "month": row.month.date(), "orders": int(row[2]), "net_sales": money(row[3] or 0)}
        for row in rows
    ]


def slow_products(business_id, *, limit=10):
    """Catalog products with the lowest paid quantity, including zeros."""
    sold = (
        select(OrderItem.product_id, func.sum(OrderItem.quantity).label("qty"))
        .join(RestaurantOrder, RestaurantOrder.id == OrderItem.order_id)
        .where(*_paid_filter(business_id))
        .group_by(OrderItem.product_id)
        .subquery()
    )
    rows = db.session.execute(
        select(Product.id, Product.name, func.coalesce(sold.c.qty, 0))
        .outerjoin(sold, sold.c.product_id == Product.id)
        .where(Product.business_id == business_id, Product.is_active.is_(True))
        .order_by(func.coalesce(sold.c.qty, 0), Product.name)
        .limit(limit)
    ).all()
    return [{"product_id": row[0], "name": row[1], "qty": quantity(row[2])} for row in rows]


def unit_cost_map(business_id):
    """Recipe roll-up when a recipe exists, otherwise the product's base cost."""
    products = db.session.scalars(select(Product).where(Product.business_id == business_id)).all()
    requirements = recipe_requirements([product.id for product in products])
    item_ids = {item_id for lines in requirements.values() for item_id, _qty, _kind in lines}
    costs = {}
    if item_ids:
        for item in db.session.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids))).all():
            costs[item.id] = money(item.standard_cost)
    result = {}
    for product in products:
        lines = requirements.get(product.id)
        if lines:
            result[product.id] = money(sum((costs[item_id] * qty for item_id, qty, _kind in lines), money(0)))
        else:
            result[product.id] = money(product.base_cost)
    return result


def estimated_profit_leaders(business_id, *, limit=10):
    """Gross profit uses line revenue minus estimated unit cost. Order-level discounts are not reallocated here."""
    costs = unit_cost_map(business_id)
    leaders = []
    for row in top_products(business_id, limit=1000):
        cost = money(costs.get(row["product_id"], 0) * row["qty"])
        leaders.append({**row, "estimated_cost": cost, "estimated_gross_profit": money(row["line_revenue"] - cost)})
    leaders.sort(key=lambda row: (-row["estimated_gross_profit"], row["name"]))
    return leaders[:limit]


def reorder_suggestion(*, business_id, branch_id, item_id, history_days, lead_time_days):
    """Suggested reorder from average outflow, lead time and a 50 percent safety factor.

    safety stock = average daily outflow * lead time * 0.5
    reorder point = average daily outflow * lead time + safety stock
    suggested quantity = reorder point - on hand, when that is positive
    """
    if history_days <= 0:
        raise ValueError("history_days must be positive")
    outflow = db.session.scalar(
        select(func.coalesce(func.sum(-StockMovement.delta_qty), 0)).where(
            StockMovement.business_id == business_id,
            StockMovement.branch_id == branch_id,
            StockMovement.item_id == item_id,
            StockMovement.movement_type.in_(CONSUMPTION_TYPES),
            StockMovement.delta_qty < 0,
        )
    )
    on_hand_value = db.session.scalar(
        select(BranchStock.quantity).where(BranchStock.branch_id == branch_id, BranchStock.item_id == item_id)
    )
    on_hand = quantity(on_hand_value or 0)
    daily = quantity(Decimal(outflow or 0) / Decimal(history_days))
    lead = Decimal(lead_time_days)
    safety = quantity(daily * lead * Decimal("0.5"))
    reorder_point = quantity(daily * lead + safety)
    suggested = quantity(reorder_point - on_hand)
    if suggested < 0:
        suggested = quantity(0)
    return {
        "average_daily_demand": daily,
        "lead_time_days": int(lead_time_days),
        "safety_stock": safety,
        "reorder_point": reorder_point,
        "on_hand": on_hand,
        "suggested_reorder_qty": suggested,
        "stockout_risk": on_hand < reorder_point,
    }


def _snapshot_figures(business_id):
    """Net ex-tax line revenue after proportional discounts, minus posted return amounts."""
    orders = db.session.execute(
        select(
            RestaurantOrder.id,
            RestaurantOrder.branch_id,
            RestaurantOrder.subtotal,
            RestaurantOrder.discount_total,
        ).where(*_paid_filter(business_id))
    ).all()
    order_info = {row.id: row for row in orders}
    items = db.session.execute(
        select(OrderItem.id, OrderItem.order_id, OrderItem.product_id, OrderItem.quantity, OrderItem.line_total).where(
            OrderItem.order_id.in_(order_info.keys()) if order_info else OrderItem.order_id == -1
        )
    ).all()
    figures = {}
    for item in items:
        order = order_info[item.order_id]
        subtotal = money(order.subtotal)
        if subtotal <= 0:
            continue
        net_line = money(money(item.line_total) / subtotal * (subtotal - money(order.discount_total)))
        key = (order.branch_id, item.product_id)
        bucket = figures.setdefault(key, {"qty": quantity(0), "revenue": money(0)})
        bucket["qty"] = quantity(bucket["qty"] + item.quantity)
        bucket["revenue"] = money(bucket["revenue"] + net_line)
    returns = db.session.execute(
        select(
            SalesReturn.branch_id,
            OrderItem.product_id,
            func.sum(SalesReturnLine.quantity),
            func.sum(SalesReturnLine.amount),
        )
        .join(SalesReturnLine, SalesReturnLine.sales_return_id == SalesReturn.id)
        .join(OrderItem, OrderItem.id == SalesReturnLine.order_item_id)
        .where(SalesReturn.business_id == business_id, SalesReturn.status == "posted")
        .group_by(SalesReturn.branch_id, OrderItem.product_id)
    ).all()
    for branch_id, product_id, qty, amount in returns:
        key = (branch_id, product_id)
        bucket = figures.setdefault(key, {"qty": quantity(0), "revenue": money(0)})
        bucket["qty"] = quantity(bucket["qty"] - (qty or 0))
        bucket["revenue"] = money(bucket["revenue"] - money(amount or 0))
    return figures


def refresh_snapshots(business, *, period_start, period_end, owner_user_id=None):
    """Store one reproducible snapshot run. A second call keeps the original rows."""
    run_code = f"SNAP-{business.slug}-HIST-V1"
    existing = db.session.scalar(select(AiAnalysisRun).where(AiAnalysisRun.run_code == run_code))
    if existing is not None:
        return existing
    run = AiAnalysisRun(
        business_id=business.id,
        run_code=run_code,
        engine="deterministic_sql",
        dataset_code=HISTORY_DATASET,
        period_start=period_start,
        period_end=period_end,
        status="complete",
        summary="Rule and SQL snapshot of the synthetic Lahore history. Not a live market finding.",
    )
    db.session.add(run)
    db.session.flush()
    costs = unit_cost_map(business.id)
    figures = _snapshot_figures(business.id)
    products = db.session.scalars(select(Product).where(Product.business_id == business.id, Product.is_active.is_(True))).all()
    branches = db.session.scalars(select(Branch).where(Branch.business_id == business.id).order_by(Branch.id)).all()
    for branch in branches:
        for product in products:
            bucket = figures.get((branch.id, product.id), {"qty": quantity(0), "revenue": money(0)})
            estimated_cost = money(costs[product.id] * bucket["qty"]) if bucket["qty"] > 0 else money(0)
            db.session.add(
                ProductPerformanceSnapshot(
                    run_id=run.id,
                    business_id=business.id,
                    branch_id=branch.id,
                    product_id=product.id,
                    period_start=period_start,
                    period_end=period_end,
                    qty_sold=bucket["qty"],
                    revenue=bucket["revenue"],
                    estimated_cost=estimated_cost,
                    estimated_gross_profit=money(bucket["revenue"] - estimated_cost),
                )
            )
    _add_recommendations(run, business, branches, owner_user_id)
    write_audit(
        action="snapshot",
        entity_type="ai_analysis_run",
        entity_id=run.id,
        business_id=business.id,
        message=f"Stored deterministic snapshot {run.run_code}",
    )
    return run


def _add_recommendations(run, business, branches, owner_user_id):
    slow = slow_products(business.id, limit=1)
    if slow:
        recommendation = AiRecommendation(
            run_id=run.id,
            business_id=business.id,
            product_id=slow[0]["product_id"],
            source="rule_engine",
            recommendation_code="slow_mover",
            title=f"Slow item: {slow[0]['name']}",
            detail=(
                f"Paid synthetic quantity is {slow[0]['qty']}. "
                "This is a planted catalog pattern, not evidence from a real restaurant."
            ),
            priority="low",
        )
        db.session.add(recommendation)
        db.session.flush()
        _feedback(recommendation.id, owner_user_id)
    leaders = top_products(business.id, limit=1)
    if leaders:
        recommendation = AiRecommendation(
            run_id=run.id,
            business_id=business.id,
            product_id=leaders[0]["product_id"],
            source="rule_engine",
            recommendation_code="keep_available",
            title=f"Protect stock for {leaders[0]['name']}",
            detail=(
                f"Highest paid quantity in the synthetic history ({leaders[0]['qty']}). "
                "Keep the recipe ingredients above the reorder point."
            ),
            priority="medium",
        )
        db.session.add(recommendation)
        db.session.flush()
        _feedback(recommendation.id, owner_user_id)
    comparison = branch_comparison(business.id)
    if len(comparison) >= 2:
        weakest = min(comparison, key=lambda row: row["average_order_value"])
        recommendation = AiRecommendation(
            run_id=run.id,
            business_id=business.id,
            branch_id=weakest["branch_id"],
            source="rule_engine",
            recommendation_code="branch_aov",
            title=f"Lower average ticket at {weakest['name']}",
            detail=(
                f"Synthetic average order value is PKR {weakest['average_order_value']}. "
                "Compare the branch mix before treating this as a real demand difference."
            ),
            priority="medium",
        )
        db.session.add(recommendation)
        db.session.flush()
        _feedback(recommendation.id, owner_user_id)
    for branch in branches:
        low = db.session.execute(
            select(InventoryItem).join(
                BranchStock,
                (BranchStock.item_id == InventoryItem.id) & (BranchStock.branch_id == branch.id),
            ).where(
                InventoryItem.business_id == business.id,
                BranchStock.quantity < InventoryItem.reorder_level,
            ).limit(1)
        ).scalar_one_or_none()
        if low is None:
            continue
        recommendation = AiRecommendation(
            run_id=run.id,
            business_id=business.id,
            branch_id=branch.id,
            source="rule_engine",
            recommendation_code="reorder",
            title=f"Reorder {low.name} at {branch.name}",
            detail="On-hand quantity is below the curated reorder level. Review the purchase suggestion before ordering.",
            priority="high",
        )
        db.session.add(recommendation)
        db.session.flush()
        _feedback(recommendation.id, owner_user_id)
        break


def _feedback(recommendation_id, user_id):
    db.session.add(
        RecommendationFeedback(
            recommendation_id=recommendation_id,
            user_id=user_id,
            decision="noted",
            note="Synthetic reviewer marked this rule output as noted. No external AI was called.",
        )
    )


def history_bounds():
    return date(2025, 5, 1), date(2026, 10, 31)


def business_by_slug(slug):
    return db.session.scalar(select(Business).where(Business.slug == slug))


def owner_id(business_id):
    return db.session.scalar(
        select(BusinessUser.user_id).where(
            BusinessUser.business_id == business_id,
            BusinessUser.role == "owner",
        )
    )
