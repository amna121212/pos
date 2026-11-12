"""Restaurants and their branches.

The super admin sees every tenant here and can open any branch in one click.
Everyone else sees only the businesses they hold a membership for, and only the
branches their membership allows.
"""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select

from app import db
from app.models import Branch, BusinessUser, Product, User
from app.order_models import RestaurantOrder
from app.platform_models import BranchOperatingHour, BusinessSetting, BusinessSubscription, SubscriptionPlan
from app.security import business_required, context, login_required, select_business, select_branch
from app.services.audit import write_audit

bp = Blueprint("restaurants", __name__, url_prefix="/restaurants")

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _counts(business_ids):
    """One query per measure, grouped by business, instead of per-business queries."""
    if not business_ids:
        return {}, {}, {}, {}
    branches = dict(
        db.session.execute(
            select(Branch.business_id, func.count(Branch.id))
            .where(Branch.business_id.in_(business_ids))
            .group_by(Branch.business_id)
        ).all()
    )
    products = dict(
        db.session.execute(
            select(Product.business_id, func.count(Product.id))
            .where(Product.business_id.in_(business_ids), Product.is_active.is_(True))
            .group_by(Product.business_id)
        ).all()
    )
    people = dict(
        db.session.execute(
            select(BusinessUser.business_id, func.count(BusinessUser.id))
            .where(BusinessUser.business_id.in_(business_ids))
            .group_by(BusinessUser.business_id)
        ).all()
    )
    return branches, products, people


def _hourly(branch_ids):
    """Opening hours per branch, collapsed to one readable line where possible."""
    if not branch_ids:
        return {}
    rows = db.session.scalars(
        select(BranchOperatingHour)
        .where(BranchOperatingHour.branch_id.in_(branch_ids))
        .order_by(BranchOperatingHour.branch_id, BranchOperatingHour.weekday)
    ).all()
    grouped = {}
    for row in rows:
        grouped.setdefault(row.branch_id, []).append(row)
    summary = {}
    for branch_id, hours in grouped.items():
        closed = [hour.weekday for hour in hours if hour.is_closed]
        open_days = [hour for hour in hours if not hour.is_closed]
        if not open_days:
            summary[branch_id] = "Closed all week"
            continue
        windows = {(hour.opens_at.strftime("%H:%M"), hour.closes_at.strftime("%H:%M")) for hour in open_days}
        if len(windows) == 1 and not closed:
            start, end = windows.pop()
            summary[branch_id] = f"Daily {start}–{end}"
        else:
            summary[branch_id] = f"{len(open_days)} of 7 days open"
    return summary


@bp.get("")
@business_required
def index():
    ctx = context()
    search = (request.args.get("q") or "").strip().lower()

    businesses = list(ctx.businesses)
    if search:
        businesses = [
            business
            for business in businesses
            if search in business.name.lower()
            or search in business.city.lower()
            or search in business.business_type.lower()
        ]

    business_ids = [business.id for business in businesses]
    branches, products, people = _counts(business_ids)

    branch_rows = {
        business.id: []
        for business in businesses
    }
    allowed = set(ctx.allowed_branch_ids)
    if business_ids:
        for branch in db.session.scalars(
            select(Branch).where(Branch.business_id.in_(business_ids)).order_by(Branch.business_id, Branch.code)
        ).all():
            # A branch-pinned manager must not be shown branches they cannot open:
            # a button that always answers 403 is worse than no button.
            if ctx.is_platform_admin or branch.id in allowed:
                branch_rows[branch.business_id].append(branch)

    hours = _hourly([branch.id for branch in sum(branch_rows.values(), [])])
    settings = {
        row.business_id: row
        for row in db.session.scalars(
            select(BusinessSetting).where(BusinessSetting.business_id.in_(business_ids or [0]))
        ).all()
    }
    plans = {
        row.business_id: (row, plan)
        for row, plan in db.session.execute(
            select(BusinessSubscription, SubscriptionPlan)
            .join(SubscriptionPlan, SubscriptionPlan.id == BusinessSubscription.plan_id)
            .where(BusinessSubscription.business_id.in_(business_ids or [0]))
        ).all()
    }
    since = datetime.now(timezone.utc) - timedelta(days=30)
    branch_orders = dict(
        db.session.execute(
            select(RestaurantOrder.branch_id, func.count(RestaurantOrder.id))
            .where(
                RestaurantOrder.business_id.in_(business_ids or [0]),
                RestaurantOrder.status == "paid",
                RestaurantOrder.created_at >= since,
            )
            .group_by(RestaurantOrder.branch_id)
        ).all()
    )

    rows = []
    for business in businesses:
        rows.append(
            {
                "business": business,
                "branches": branch_rows.get(business.id, []),
                "branch_count": branches.get(business.id, 0),
                "product_count": products.get(business.id, 0),
                "people": people.get(business.id, 0),
                "settings": settings.get(business.id),
                "subscription": plans.get(business.id),
                "selected": business.id == ctx.business_id,
            }
        )

    return render_template(
        "restaurants/index.html",
        rows=rows,
        search=search,
        hours=hours,
        branch_orders=branch_orders,
        current_business_id=ctx.business_id,
        current_branch_id=ctx.branch_id,
        can_open_any=ctx.is_platform_admin,
    )


@bp.post("/open")
@login_required
def open():
    """Switch to a restaurant, and optionally straight to one of its branches."""
    ctx = context()
    business_id = request.form.get("business_id", type=int)
    branch_id = request.form.get("branch_id", type=int)
    if not business_id:
        abort(400)

    business = select_business(business_id)
    if ctx.is_platform_admin:
        write_audit(
            action="switch_business",
            entity_type="business",
            entity_id=business.id,
            business_id=business.id,
            actor_user_id=ctx.user.id,
            message=f"Super admin opened {business.name} from the restaurant list",
        )

    if branch_id:
        # select_branch re-checks the id against the new business scope.
        select_branch(branch_id)
        if ctx.is_platform_admin:
            branch = db.session.get(Branch, branch_id)
            write_audit(
                action="switch_branch",
                entity_type="branch",
                entity_id=branch.id,
                business_id=business.id,
                branch_id=branch.id,
                actor_user_id=ctx.user.id,
                message=f"Super admin opened branch {branch.code}",
            )
        db.session.commit()
        flash(f"Working branch: {business.name} · {branch.name}", "info")
        return redirect(url_for("dashboard.index"))

    db.session.commit()
    flash(f"Working business: {business.name}", "info")
    return redirect(url_for("restaurants.index"))


@bp.get("/<int:business_id>")
@business_required
def detail(business_id):
    """One restaurant: its branches, hours and staffing."""
    ctx = context()
    if business_id not in [business.id for business in ctx.businesses]:
        abort(403, description="That restaurant is outside your access.")

    row = next(business for business in ctx.businesses if business.id == business_id)
    allowed = set(ctx.allowed_branch_ids)
    branches = [
        branch
        for branch in db.session.scalars(
            select(Branch).where(Branch.business_id == business_id).order_by(Branch.code)
        ).all()
        if ctx.is_platform_admin or branch.id in allowed
    ]
    hours = _hourly([branch.id for branch in branches])
    staff = db.session.execute(
        select(BusinessUser, User, Branch)
        .join(User, User.id == BusinessUser.user_id)
        .outerjoin(Branch, Branch.id == BusinessUser.branch_id)
        .where(BusinessUser.business_id == business_id)
        .order_by(User.display_name)
    ).all()
    settings = db.session.scalar(
        select(BusinessSetting).where(BusinessSetting.business_id == business_id)
    )
    return render_template(
        "restaurants/detail.html",
        business=row,
        branches=branches,
        hours=hours,
        staff=staff,
        settings=settings,
        current_business_id=ctx.business_id,
        current_branch_id=ctx.branch_id,
    )
