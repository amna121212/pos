"""Reports: one HTML shell plus a JSON API that every panel is rendered from.

The page never reloads to change a filter. The browser holds the filter state in
the query string, the shell renders it, and `GET /api/reports` returns the
aggregates for exactly that state. Navigating away and back, refreshing, or
bookmarking restores the same view because the URL is the source of truth.

A session copy of the last filter set is kept so clicking **Reports** in the
navigation reopens the view you were last looking at instead of resetting it.
"""
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException
from sqlalchemy import select

from app import db
from app.models import Branch, BusinessUser, Category, PaymentMethod, Supplier
from app.security import branch_required, context, permission_required
from app.services import reporting
from app.services.reporting import Filters, make_period

bp = Blueprint("reports", __name__, url_prefix="/reports")

SESSION_KEY = "report_filters"
MAX_SPAN_DAYS = 366
DEFAULT_SPAN_DAYS = 30
GRANULARITIES = ("day", "week", "month")
STATUS_CHOICES = {
    "paid": ("paid",),
    "settled": ("paid", "partially_paid"),
    "all": (),
}

ALL_SECTIONS = (
    "overview",
    "daily",
    "weekly",
    "monthly",
    "branches",
    "products",
    "categories",
    "payments",
    "cancelled",
    "cashiers",
    "stock",
    "low_stock",
    "purchases",
    "discounts",
    "operations",
    "provenance",
)

FILTER_KEYS = (
    "from",
    "to",
    "branch",
    "category",
    "payment",
    "employee",
    "supplier",
    "status",
    "group",
    "compare",
    "limit",
)


def _parse_date(value, fallback):
    if not value:
        return fallback
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return fallback


def _int_or_none(value):
    if value in (None, "", "all", "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy(value, default=True):
    if value in (None, ""):
        return default
    return str(value).lower() in ("1", "true", "yes", "on")


def _defaults(ctx):
    today = date.today()
    start = today - timedelta(days=DEFAULT_SPAN_DAYS - 1)
    return {
        "from": start.isoformat(),
        "to": today.isoformat(),
        # A branch-limited account reports on its own branch by default.
        "branch": str(ctx.branch_id) if len(ctx.allowed_branch_ids) == 1 else "all",
        "category": "",
        "payment": "",
        "employee": "",
        "supplier": "",
        "status": "paid",
        "group": "day",
        "compare": "1",
        "limit": "15",
    }


def resolve_filters(ctx):
    """Explicit query string, else the session copy, else defaults.

    Raises 403 for a branch or record that belongs to another tenant.
    """
    if any(key in request.args for key in FILTER_KEYS):
        raw = {key: request.args.get(key, "") for key in FILTER_KEYS}
        raw["branch"] = request.args.get("branch", "all") or "all"
    elif isinstance(session.get(SESSION_KEY), dict):
        raw = {key: session[SESSION_KEY].get(key, "") for key in FILTER_KEYS}
    else:
        raw = _defaults(ctx)

    today = date.today()
    start = _parse_date(raw.get("from"), today - timedelta(days=DEFAULT_SPAN_DAYS - 1))
    end = _parse_date(raw.get("to"), today)
    if start > end:
        start, end = end, start
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        start = end - timedelta(days=MAX_SPAN_DAYS - 1)

    business_id = ctx.business_id
    if business_id is None:
        abort(403, description="Choose a restaurant before opening reports.")

    branch_value = raw.get("branch") or "all"
    branch_id = None
    if branch_value not in ("all", ""):
        branch_id = _int_or_none(branch_value)
        if branch_id is None or branch_id not in ctx.allowed_branch_ids:
            abort(403, description="That branch is outside your access.")
        branch_ids = [branch_id]
    else:
        branch_ids = list(ctx.allowed_branch_ids)

    category_id = _int_or_none(raw.get("category"))
    if category_id is not None and db.session.scalar(
        select(Category.id).where(Category.id == category_id, Category.business_id == business_id)
    ) is None:
        abort(403, description="That category is outside your access.")

    payment_id = _int_or_none(raw.get("payment"))
    if payment_id is not None and db.session.scalar(
        select(PaymentMethod.id).where(
            PaymentMethod.id == payment_id, PaymentMethod.business_id == business_id
        )
    ) is None:
        abort(403, description="That payment method is outside your access.")

    supplier_id = _int_or_none(raw.get("supplier"))
    if supplier_id is not None and db.session.scalar(
        select(Supplier.id).where(Supplier.id == supplier_id, Supplier.business_id == business_id)
    ) is None:
        abort(403, description="That supplier is outside your access.")

    employee_id = _int_or_none(raw.get("employee"))
    if employee_id is not None and db.session.scalar(
        select(BusinessUser.id).where(
            BusinessUser.user_id == employee_id, BusinessUser.business_id == business_id
        )
    ) is None:
        abort(403, description="That employee is outside your access.")

    status_choice = raw.get("status") if raw.get("status") in STATUS_CHOICES else "paid"
    group = raw.get("group") if raw.get("group") in GRANULARITIES else "day"
    limit = _int_or_none(raw.get("limit")) or 15
    limit = max(5, min(limit, 50))

    resolved = {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "branch": branch_value if branch_id else "all",
        "category": str(category_id) if category_id else "",
        "payment": str(payment_id) if payment_id else "",
        "employee": str(employee_id) if employee_id else "",
        "supplier": str(supplier_id) if supplier_id else "",
        "status": status_choice,
        "group": group,
        "compare": "1" if _truthy(raw.get("compare"), True) else "0",
        "limit": str(limit),
    }
    session[SESSION_KEY] = resolved

    return {
        "raw": resolved,
        "business_id": business_id,
        "branch_ids": branch_ids,
        "branch_id": branch_id,
        "category_id": category_id,
        "payment_id": payment_id,
        "employee_id": employee_id,
        "supplier_id": supplier_id,
        "limit": limit,
        "group": group,
        "compare": resolved["compare"] == "1",
        "period": make_period(start, end),
        "filters": Filters(
            business_id=business_id,
            branch_ids=branch_ids,
            statuses=STATUS_CHOICES[status_choice],
            category_id=category_id,
            payment_method_id=payment_id,
            employee_id=employee_id,
            supplier_id=supplier_id,
            limit=limit,
        ),
    }


def _filter_labels(ctx, resolved):
    branch = db.session.get(Branch, resolved["branch_id"]) if resolved["branch_id"] else None
    category = (
        db.session.get(Category, resolved["category_id"]) if resolved["category_id"] else None
    )
    payment = (
        db.session.get(PaymentMethod, resolved["payment_id"]) if resolved["payment_id"] else None
    )
    supplier = (
        db.session.get(Supplier, resolved["supplier_id"]) if resolved["supplier_id"] else None
    )
    return {
        "business": ctx.business.name if ctx.business else "",
        "business_id": ctx.business_id,
        "branch": branch.name if branch else "All branches",
        "branch_code": branch.code if branch else "",
        "category": category.name if category else "All categories",
        "payment": payment.label if payment else "All methods",
        "supplier": supplier.name if supplier else "All suppliers",
        "period": f"{resolved['period'].start_date:%d %b %Y} – {resolved['period'].end_date:%d %b %Y}",
        "days": resolved["period"].days(),
    }


def build_sections(resolved, only=None):
    """Calculate every requested section from the same filter set."""
    wanted = [name for name in ALL_SECTIONS if only is None or name in only]
    filters = resolved["filters"]
    period = resolved["period"]
    data = {}

    if "overview" in wanted:
        data["overview"] = reporting.sales_overview(filters, period)
    if "daily" in wanted:
        data["daily"] = reporting.sales_series(filters, period, "day")
    if "weekly" in wanted:
        data["weekly"] = reporting.sales_series(filters, period, "week")
    if "monthly" in wanted:
        data["monthly"] = reporting.sales_series(filters, period, "month")
    if "branches" in wanted:
        data["branches"] = reporting.branch_comparison(filters, period)
    if "products" in wanted:
        data["products"] = reporting.product_performance(filters, period)
    if "categories" in wanted:
        data["categories"] = reporting.category_performance(filters, period)
    if "payments" in wanted:
        data["payments"] = reporting.payment_breakdown(filters, period)
    if "cancelled" in wanted:
        data["cancelled"] = reporting.cancelled_and_refunded(filters, period)
    if "cashiers" in wanted:
        data["cashiers"] = reporting.cashier_performance(filters, period)
    if "stock" in wanted:
        data["stock"] = reporting.stock_consumption(filters, period)
    if "low_stock" in wanted:
        data["low_stock"] = reporting.low_stock(
            resolved["business_id"], resolved["branch_id"] or (resolved["branch_ids"] or [None])[0]
        )
    if "purchases" in wanted:
        data["purchases"] = reporting.purchase_report(filters, period)
    if "discounts" in wanted:
        data["discounts"] = reporting.discount_analysis(filters, period)
    if "operations" in wanted:
        data["operations"] = reporting.operational_summary(filters, period)
    if "provenance" in wanted:
        data["provenance"] = reporting.dataset_split(filters, period)
        data["status_mix"] = reporting.status_mix(filters, period)
    return data


@bp.get("")
@permission_required("report.view")
@branch_required
def index():
    ctx = context()
    resolved = resolve_filters(ctx)
    options = {
        "businesses": ctx.businesses,
        "branches": ctx.branches,
        "categories": db.session.scalars(
            select(Category).where(Category.business_id == ctx.business_id).order_by(Category.name)
        ).all(),
        "payment_methods": db.session.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.business_id == ctx.business_id, PaymentMethod.enabled.is_(True))
            .order_by(PaymentMethod.label)
        ).all(),
        "employees": _employees(ctx.business_id),
        "suppliers": db.session.scalars(
            select(Supplier).where(Supplier.business_id == ctx.business_id).order_by(Supplier.name)
        ).all(),
        "statuses": list(STATUS_CHOICES.keys()),
        "granularities": GRANULARITIES,
    }
    return render_template(
        "reports/index.html",
        resolved=resolved,
        raw=resolved["raw"],
        options=options,
        labels=_filter_labels(ctx, resolved),
        sections=build_sections(resolved),
    )


def _employees(business_id):
    rows = db.session.execute(
        select(BusinessUser.user_id, BusinessUser.role)
        .where(BusinessUser.business_id == business_id)
        .order_by(BusinessUser.user_id)
    ).all()
    from app.models import User

    users = {
        user.id: user
        for user in db.session.scalars(
            select(User).where(User.id.in_([row[0] for row in rows] or [0]))
        ).all()
    }
    return [
        {"id": user_id, "name": users[user_id].display_name, "role": role}
        for user_id, role in rows
        if user_id in users
    ]


@bp.get("/api/data")
@permission_required("report.view")
@branch_required
def api_data():
    """Aggregates for one filter state. Every panel reads this response."""
    ctx = context()
    try:
        resolved = resolve_filters(ctx)
        only = request.args.get("sections")
        wanted = [name.strip() for name in only.split(",")] if only else None
        if wanted:
            unknown = [name for name in wanted if name not in ALL_SECTIONS]
            if unknown:
                abort(400, description="Unknown report section: " + ", ".join(unknown))
        payload = {
            "ok": True,
            "filters": resolved["raw"],
            "labels": _filter_labels(ctx, resolved),
            "period": {
                "from": resolved["raw"]["from"],
                "to": resolved["raw"]["to"],
                "days": resolved["period"].days(),
            },
            "sections": build_sections(resolved, wanted),
        }
        return jsonify(payload)
    except HTTPException:
        # 400/403 from filter validation must reach the client as themselves.
        raise
    except Exception as error:  # noqa: BLE001 - surfaced to the client, never hidden
        db.session.rollback()
        current_app.logger.exception("Report query failed")
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "The report query failed. The filters were not applied.",
                    "detail": type(error).__name__,
                }
            ),
            500,
        )


@bp.get("/api/options")
@permission_required("report.view")
@branch_required
def api_options():
    """Filter options for the active business, used after a context switch."""
    ctx = context()
    return jsonify(
        {
            "ok": True,
            "business_id": ctx.business_id,
            "business_name": ctx.business.name if ctx.business is not None else "",
            "branch_id": ctx.branch_id,
            "branches": [
                {"id": branch.id, "code": branch.code, "name": branch.name}
                for branch in ctx.branches
            ],
            "categories": [
                {"id": row.id, "name": row.name}
                for row in db.session.scalars(
                    select(Category)
                    .where(Category.business_id == ctx.business_id)
                    .order_by(Category.name)
                ).all()
            ],
            "payment_methods": [
                {"id": row.id, "label": row.label}
                for row in db.session.scalars(
                    select(PaymentMethod)
                    .where(
                        PaymentMethod.business_id == ctx.business_id,
                        PaymentMethod.enabled.is_(True),
                    )
                    .order_by(PaymentMethod.label)
                ).all()
            ],
            "employees": _employees(ctx.business_id),
            "suppliers": [
                {"id": row.id, "name": row.name}
                for row in db.session.scalars(
                    select(Supplier)
                    .where(Supplier.business_id == ctx.business_id)
                    .order_by(Supplier.name)
                ).all()
            ],
        }
    )
