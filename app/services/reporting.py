"""Deterministic report aggregates, calculated in PostgreSQL.

Every figure on the reports page comes from these functions. They take an explicit
business, a list of permitted branch ids and a UTC period, and they never fall back
to a default range: an empty period returns zeros and empty lists, which the page
renders as an honest empty state.

Revenue conventions used throughout:

* **gross**  = `restaurant_orders.grand_total` (what the guest paid, tax included)
* **net**    = `grand_total - tax_total` (takings excluding tax)
* **paid**   = orders whose status is `paid`; cancelled, held and part-paid orders
  are counted separately and never mixed into sales.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import extract, func, select

from app import db
from app.inventory_models import (
    BranchStock,
    GoodsReceipt,
    InventoryItem,
    StockMovement,
    SupplierPurchaseItem,
    SupplierPurchaseOrder,
)
from app.models import Branch, Category, PaymentMethod, Product, Supplier, User
from app.money import money, quantity
from app.operations_models import CashierShift, SalesReturn
from app.order_models import KitchenTicket, OrderItem, OrderPayment, RestaurantOrder
from app.timeutil import PAKISTAN

DEMO_DATASET = "SYNTHETIC_HISTORY_V1"
LIVE_DATASET = "APPLICATION_GENERATED"
CONSUMPTION_TYPES = ("recipe_consumption", "retail_sale", "exchange_issue")
SALES_STATUSES = ("paid",)
OPEN_STATUSES = ("open", "held", "partially_paid")


@dataclass
class Period:
    """A reporting window as local dates plus the UTC instants used in queries."""

    start_date: date
    end_date: date
    start: datetime
    end: datetime
    label: str = ""

    def previous(self):
        span = (self.end - self.start)
        return Period(
            start_date=self.start_date - timedelta(days=span.days),
            end_date=self.start_date - timedelta(days=1),
            start=self.start - span,
            end=self.start,
            label="Previous period",
        )

    def days(self):
        return max((self.end_date - self.start_date).days + 1, 1)


def period_bounds(start_date, end_date):
    """Local Pakistan dates to the UTC instants a query should use."""
    start = datetime.combine(start_date, time.min, tzinfo=PAKISTAN)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=PAKISTAN)
    return start, end


def make_period(start_date, end_date, label=""):
    start, end = period_bounds(start_date, end_date)
    return Period(start_date=start_date, end_date=end_date, start=start, end=end, label=label)


def pakistan_month(column):
    return func.date_trunc("month", func.timezone("Asia/Karachi", column))


def pakistan_week(column):
    return func.date_trunc("week", func.timezone("Asia/Karachi", column))


def pakistan_day(column):
    return func.date_trunc("day", func.timezone("Asia/Karachi", column))


@dataclass
class Filters:
    """One reporting request. `branch_ids` is already limited to what the user may read."""

    business_id: int
    branch_ids: list = field(default_factory=list)
    statuses: tuple = SALES_STATUSES
    category_id: int | None = None
    payment_method_id: int | None = None
    employee_id: int | None = None
    supplier_id: int | None = None
    limit: int = 15

    def conditions(self, period):
        """Filters shared by every order-based report."""
        rows = [
            RestaurantOrder.business_id == self.business_id,
            RestaurantOrder.created_at >= period.start,
            RestaurantOrder.created_at < period.end,
        ]
        if self.branch_ids:
            rows.append(RestaurantOrder.branch_id.in_(self.branch_ids))
        if self.statuses:
            rows.append(RestaurantOrder.status.in_(self.statuses))
        if self.category_id:
            # Restrict to orders that contain a line in this category. `Product` must
            # live inside the subquery, otherwise it leaks into the outer FROM.
            rows.append(
                RestaurantOrder.id.in_(
                    select(OrderItem.order_id)
                    .join(Product, Product.id == OrderItem.product_id)
                    .where(Product.category_id == self.category_id)
                )
            )
        if self.payment_method_id:
            rows.append(
                RestaurantOrder.id.in_(
                    select(OrderPayment.order_id).where(
                        OrderPayment.payment_method_id == self.payment_method_id,
                        OrderPayment.status == "captured",
                    )
                )
            )
        if self.employee_id:
            rows.append(
                RestaurantOrder.cashier_shift_id.in_(
                    select(CashierShift.id).where(CashierShift.user_id == self.employee_id)
                )
            )
        return rows


# --------------------------------------------------------------------- sales


def sales_overview(filters, period):
    """Headline totals for the period, with the previous period for comparison."""
    current = _totals(filters, period)
    previous = _totals(filters, period.previous())
    return {"current": current, "previous": previous, "deltas": _deltas(current, previous)}


def _totals(filters, period):
    conditions = filters.conditions(period)
    row = db.session.execute(
        select(
            func.count(RestaurantOrder.id),
            func.coalesce(func.sum(RestaurantOrder.grand_total), 0),
            func.coalesce(func.sum(RestaurantOrder.tax_total), 0),
            func.coalesce(func.sum(RestaurantOrder.discount_total), 0),
        ).where(*conditions)
    ).one()
    orders = int(row[0] or 0)
    gross = money(row[1] or 0)
    tax = money(row[2] or 0)
    discount = money(row[3] or 0)
    net = money(gross - tax)
    items = int(
        db.session.scalar(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .select_from(OrderItem)
            .join(RestaurantOrder, RestaurantOrder.id == OrderItem.order_id)
            .where(*conditions)
        )
        or 0
    )
    return {
        "orders": orders,
        "gross": gross,
        "net_sales": net,
        "tax": tax,
        "discount": discount,
        "average_order_value": money(net / orders) if orders else money(0),
        "items_sold": items,
        "items_per_order": round(items / orders, 2) if orders else 0,
    }


def _deltas(current, previous):
    result = {}
    for key in ("orders", "gross", "net_sales", "average_order_value", "items_sold"):
        before = previous.get(key) or 0
        now = current.get(key) or 0
        if float(before) == 0:
            result[key] = None
        else:
            result[key] = round((float(now) - float(before)) / float(before) * 100, 1)
    return result


def sales_series(filters, period, group="day"):
    """Aggregated takings by day, week or month. Never returns individual orders."""
    bucket = {"day": pakistan_day, "week": pakistan_week, "month": pakistan_month}.get(
        group, pakistan_day
    )(RestaurantOrder.created_at)
    rows = db.session.execute(
        select(
            bucket.label("bucket"),
            func.count(RestaurantOrder.id),
            func.coalesce(func.sum(RestaurantOrder.grand_total), 0),
            func.coalesce(func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total), 0),
        )
        .where(*filters.conditions(period))
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    return [
        {
            "period": row.bucket.date().isoformat(),
            "label": _series_label(row.bucket.date(), group),
            "orders": int(row[1]),
            "gross": money(row[2]),
            "net_sales": money(row[3]),
        }
        for row in rows
    ]


def _series_label(value, group):
    if group == "month":
        return value.strftime("%b %Y")
    if group == "week":
        return "w/c " + value.strftime("%d %b")
    return value.strftime("%d %b")


def branch_comparison(filters, period):
    rows = db.session.execute(
        select(
            Branch.id,
            Branch.code,
            Branch.name,
            func.count(RestaurantOrder.id),
            func.coalesce(func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total), 0),
            func.coalesce(func.sum(RestaurantOrder.grand_total), 0),
        )
        .join(RestaurantOrder, RestaurantOrder.branch_id == Branch.id)
        .where(*filters.conditions(period))
        .group_by(Branch.id, Branch.code, Branch.name)
        .order_by(func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total).desc())
    ).all()
    result = []
    for row in rows:
        orders = int(row[3] or 0)
        net = money(row[4] or 0)
        result.append(
            {
                "branch_id": row[0],
                "code": row[1],
                "name": row[2],
                "orders": orders,
                "net_sales": net,
                "gross": money(row[5] or 0),
                "average_order_value": money(net / orders) if orders else money(0),
            }
        )
    return result


def product_performance(filters, period):
    conditions = filters.conditions(period)
    if filters.category_id:
        # Line-level tables narrow to the chosen category, not just to orders that
        # happen to contain it, so "BBQ" shows BBQ items rather than the whole basket.
        conditions.append(Product.category_id == filters.category_id)
    rows = db.session.execute(
        select(
            Product.id,
            Product.name,
            Product.sku,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.line_total), 0),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(RestaurantOrder, RestaurantOrder.id == OrderItem.order_id)
        .where(*conditions)
        .group_by(Product.id, Product.name, Product.sku)
        .order_by(func.sum(OrderItem.line_total).desc())
        .limit(filters.limit)
    ).all()
    return [
        {
            "product_id": row[0],
            "name": row[1],
            "sku": row[2],
            "quantity": quantity(row[3]),
            "revenue": money(row[4]),
        }
        for row in rows
    ]


def category_performance(filters, period):
    conditions = filters.conditions(period)
    if filters.category_id:
        conditions.append(Category.id == filters.category_id)
    rows = db.session.execute(
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.line_total), 0),
        )
        .join(Product, Product.category_id == Category.id)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(RestaurantOrder, RestaurantOrder.id == OrderItem.order_id)
        .where(*conditions)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(OrderItem.line_total).desc())
    ).all()
    return [
        {
            "category_id": row[0],
            "name": row[1],
            "quantity": quantity(row[2]),
            "revenue": money(row[3]),
        }
        for row in rows
    ]


def payment_breakdown(filters, period):
    rows = db.session.execute(
        select(
            PaymentMethod.id,
            PaymentMethod.label,
            func.count(OrderPayment.id),
            func.coalesce(func.sum(OrderPayment.amount), 0),
        )
        .join(OrderPayment, OrderPayment.payment_method_id == PaymentMethod.id)
        .join(RestaurantOrder, RestaurantOrder.id == OrderPayment.order_id)
        .where(
            OrderPayment.status == "captured",
            OrderPayment.payment_method_id == (filters.payment_method_id or PaymentMethod.id),
            *filters.conditions(period),
        )
        .group_by(PaymentMethod.id, PaymentMethod.label)
        .order_by(func.sum(OrderPayment.amount).desc())
    ).all()
    total = sum((money(row[3]) for row in rows), money(0))
    return [
        {
            "payment_method_id": row[0],
            "label": row[1],
            "payments": int(row[2]),
            "amount": money(row[3]),
            "share": round(float(money(row[3])) / float(total) * 100, 1) if total else 0,
        }
        for row in rows
    ]


def status_mix(filters, period):
    """Counts by status for every order in the period, ignoring the paid-only filter."""
    unscoped = Filters(**{**filters.__dict__, "statuses": ()})
    rows = db.session.execute(
        select(RestaurantOrder.status, func.count(RestaurantOrder.id), func.coalesce(func.sum(RestaurantOrder.grand_total), 0))
        .where(*unscoped.conditions(period))
        .group_by(RestaurantOrder.status)
        .order_by(func.count(RestaurantOrder.id).desc())
    ).all()
    return [
        {"status": row[0], "orders": int(row[1]), "value": money(row[2])} for row in rows
    ]


def cancelled_and_refunded(filters, period):
    """Cancelled and voided tickets, plus posted refunds and exchanges."""
    cancelled_filters = Filters(**{**filters.__dict__, "statuses": ("cancelled", "voided")})
    cancelled = db.session.execute(
        select(
            func.count(RestaurantOrder.id),
            func.coalesce(func.sum(RestaurantOrder.grand_total), 0),
        ).where(*cancelled_filters.conditions(period))
    ).one()
    hold_filters = Filters(**{**filters.__dict__, "statuses": ("held", "partially_paid", "open")})
    open_rows = db.session.execute(
        select(RestaurantOrder.status, func.count(RestaurantOrder.id), func.coalesce(func.sum(RestaurantOrder.grand_total), 0))
        .where(*hold_filters.conditions(period))
        .group_by(RestaurantOrder.status)
    ).all()

    return_conditions = [
        SalesReturn.business_id == filters.business_id,
        SalesReturn.status == "posted",
        SalesReturn.created_at >= period.start,
        SalesReturn.created_at < period.end,
    ]
    if filters.branch_ids:
        return_conditions.append(SalesReturn.branch_id.in_(filters.branch_ids))
    refunds = db.session.execute(
        select(
            SalesReturn.return_type,
            func.count(SalesReturn.id),
            func.coalesce(func.sum(SalesReturn.refund_amount), 0),
        )
        .where(*return_conditions)
        .group_by(SalesReturn.return_type)
    ).all()
    recent_returns = db.session.execute(
        select(SalesReturn.return_number, SalesReturn.return_type, SalesReturn.refund_amount, SalesReturn.created_at, SalesReturn.reason)
        .where(*return_conditions)
        .order_by(SalesReturn.created_at.desc())
        .limit(filters.limit)
    ).all()

    return {
        "cancelled_orders": int(cancelled[0] or 0),
        "cancelled_value": money(cancelled[1] or 0),
        "unsettled": [
            {"status": row[0], "orders": int(row[1]), "value": money(row[2])} for row in open_rows
        ],
        "returns": [
            {"return_type": row[0], "count": int(row[1]), "amount": money(row[2])} for row in refunds
        ],
        "recent_returns": [
            {
                "return_number": row[0],
                "return_type": row[1],
                "amount": money(row[2]),
                "created_at": row[3].isoformat(),
                "reason": row[4],
            }
            for row in recent_returns
        ],
    }


def cashier_performance(filters, period):
    rows = db.session.execute(
        select(
            User.id,
            User.display_name,
            Branch.code,
            func.count(RestaurantOrder.id),
            func.coalesce(func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total), 0),
            func.coalesce(func.sum(RestaurantOrder.discount_total), 0),
        )
        .join(CashierShift, CashierShift.id == RestaurantOrder.cashier_shift_id)
        .join(User, User.id == CashierShift.user_id)
        .join(Branch, Branch.id == RestaurantOrder.branch_id)
        .where(*filters.conditions(period))
        .group_by(User.id, User.display_name, Branch.code)
        .order_by(func.sum(RestaurantOrder.grand_total - RestaurantOrder.tax_total).desc())
        .limit(filters.limit)
    ).all()
    result = []
    for row in rows:
        orders = int(row[3] or 0)
        net = money(row[4] or 0)
        result.append(
            {
                "user_id": row[0],
                "name": row[1],
                "branch": row[2],
                "orders": orders,
                "net_sales": net,
                "discounts": money(row[5] or 0),
                "average_order_value": money(net / orders) if orders else money(0),
            }
        )
    return result


def discount_analysis(filters, period):
    conditions = filters.conditions(period)
    totals = db.session.execute(
        select(
            func.count(RestaurantOrder.id),
            func.coalesce(func.sum(RestaurantOrder.discount_total), 0),
            func.coalesce(func.avg(RestaurantOrder.discount_total), 0),
        ).where(*conditions, RestaurantOrder.discount_total > 0)
    ).one()
    rows = db.session.execute(
        select(
            RestaurantOrder.discount_total,
            RestaurantOrder.order_number,
            RestaurantOrder.created_at,
            Branch.code,
        )
        .join(Branch, Branch.id == RestaurantOrder.branch_id)
        .where(*conditions, RestaurantOrder.discount_total > 0)
        .order_by(RestaurantOrder.discount_total.desc())
        .limit(filters.limit)
    ).all()
    return {
        "discounted_orders": int(totals[0] or 0),
        "total_discount": money(totals[1] or 0),
        "average_discount": money(totals[2] or 0),
        "top_discounts": [
            {
                "order_number": row[1],
                "amount": money(row[0]),
                "created_at": row[2].isoformat(),
                "branch": row[3],
            }
            for row in rows
        ],
    }


def stock_consumption(filters, period):
    """What the period actually consumed, by movement type and by item."""
    conditions = [
        StockMovement.business_id == filters.business_id,
        StockMovement.created_at >= period.start,
        StockMovement.created_at < period.end,
    ]
    if filters.branch_ids:
        conditions.append(StockMovement.branch_id.in_(filters.branch_ids))
    by_type = db.session.execute(
        select(StockMovement.movement_type, func.count(StockMovement.id), func.coalesce(func.sum(StockMovement.delta_qty), 0))
        .where(*conditions)
        .group_by(StockMovement.movement_type)
        .order_by(func.count(StockMovement.id).desc())
    ).all()
    by_item = db.session.execute(
        select(
            InventoryItem.name,
            InventoryItem.sku,
            InventoryItem.unit,
            func.coalesce(func.sum(StockMovement.delta_qty), 0),
        )
        .join(StockMovement, StockMovement.item_id == InventoryItem.id)
        .where(*conditions, StockMovement.movement_type.in_(CONSUMPTION_TYPES))
        .group_by(InventoryItem.id, InventoryItem.name, InventoryItem.sku, InventoryItem.unit)
        .order_by(func.sum(StockMovement.delta_qty).asc())
        .limit(filters.limit)
    ).all()
    return {
        "by_type": [
            {"movement_type": row[0], "movements": int(row[1]), "delta": quantity(row[2])}
            for row in by_type
        ],
        "top_consumed": [
            {"name": row[0], "sku": row[1], "unit": row[2], "delta": quantity(row[3])}
            for row in by_item
        ],
    }


def low_stock(business_id, branch_id, limit=50):
    """On-hand stock at or below the reorder level. Not period-bound."""
    if not branch_id:
        return []
    rows = db.session.execute(
        select(
            InventoryItem.sku,
            InventoryItem.name,
            InventoryItem.unit,
            BranchStock.quantity,
            InventoryItem.reorder_level,
        )
        .join(BranchStock, BranchStock.item_id == InventoryItem.id)
        .where(
            BranchStock.business_id == business_id,
            BranchStock.branch_id == branch_id,
            BranchStock.quantity <= InventoryItem.reorder_level,
        )
        .order_by((BranchStock.quantity - InventoryItem.reorder_level).asc())
        .limit(limit)
    ).all()
    return [
        {
            "sku": row[0],
            "name": row[1],
            "unit": row[2],
            "quantity": quantity(row[3]),
            "reorder_level": quantity(row[4]),
        }
        for row in rows
    ]


def purchase_report(filters, period):
    """Purchase orders raised and goods received in the period, with supplier totals."""
    conditions = [
        SupplierPurchaseOrder.business_id == filters.business_id,
        SupplierPurchaseOrder.created_at >= period.start,
        SupplierPurchaseOrder.created_at < period.end,
    ]
    if filters.branch_ids:
        conditions.append(SupplierPurchaseOrder.branch_id.in_(filters.branch_ids))
    if filters.supplier_id:
        conditions.append(SupplierPurchaseOrder.supplier_id == filters.supplier_id)

    by_supplier = db.session.execute(
        select(
            Supplier.id,
            Supplier.name,
            func.count(SupplierPurchaseOrder.id),
            func.coalesce(
                func.sum(SupplierPurchaseItem.qty_ordered * SupplierPurchaseItem.unit_cost), 0
            ),
        )
        .join(SupplierPurchaseOrder, SupplierPurchaseOrder.supplier_id == Supplier.id)
        .join(SupplierPurchaseItem, SupplierPurchaseItem.purchase_order_id == SupplierPurchaseOrder.id)
        .where(*conditions)
        .group_by(Supplier.id, Supplier.name)
        .order_by(func.sum(SupplierPurchaseItem.qty_ordered * SupplierPurchaseItem.unit_cost).desc())
        .limit(filters.limit)
    ).all()

    recent = db.session.execute(
        select(
            SupplierPurchaseOrder.po_number,
            Supplier.name,
            SupplierPurchaseOrder.status,
            SupplierPurchaseOrder.created_at,
            func.coalesce(
                func.sum(SupplierPurchaseItem.qty_ordered * SupplierPurchaseItem.unit_cost), 0
            ),
        )
        .join(Supplier, Supplier.id == SupplierPurchaseOrder.supplier_id)
        .join(SupplierPurchaseItem, SupplierPurchaseItem.purchase_order_id == SupplierPurchaseOrder.id)
        .where(*conditions)
        .group_by(
            SupplierPurchaseOrder.id,
            SupplierPurchaseOrder.po_number,
            Supplier.name,
            SupplierPurchaseOrder.status,
            SupplierPurchaseOrder.created_at,
        )
        .order_by(SupplierPurchaseOrder.created_at.desc())
        .limit(filters.limit)
    ).all()

    receipt_conditions = [
        GoodsReceipt.business_id == filters.business_id,
        GoodsReceipt.received_at >= period.start,
        GoodsReceipt.received_at < period.end,
    ]
    if filters.branch_ids:
        receipt_conditions.append(GoodsReceipt.branch_id.in_(filters.branch_ids))
    received = int(
        db.session.scalar(
            select(func.count()).select_from(GoodsReceipt).where(*receipt_conditions)
        )
        or 0
    )
    return {
        "received_count": received,
        "by_supplier": [
            {"supplier_id": row[0], "name": row[1], "orders": int(row[2]), "value": money(row[3])}
            for row in by_supplier
        ],
        "recent": [
            {
                "po_number": row[0],
                "supplier": row[1],
                "status": row[2],
                "created_at": row[3].isoformat(),
                "value": money(row[4]),
            }
            for row in recent
        ],
    }


def operational_summary(filters, period):
    conditions = filters.conditions(period)
    by_type = db.session.execute(
        select(
            RestaurantOrder.order_type,
            func.count(RestaurantOrder.id),
            func.coalesce(func.sum(RestaurantOrder.grand_total), 0),
        )
        .where(*conditions)
        .group_by(RestaurantOrder.order_type)
        .order_by(func.count(RestaurantOrder.id).desc())
    ).all()
    hours = db.session.execute(
        select(
            extract("hour", func.timezone("Asia/Karachi", RestaurantOrder.created_at)).label("hour"),
            func.count(RestaurantOrder.id),
        )
        .where(*conditions)
        .group_by("hour")
        .order_by("hour")
    ).all()
    weekdays = db.session.execute(
        select(
            extract("dow", func.timezone("Asia/Karachi", RestaurantOrder.created_at)).label("dow"),
            func.count(RestaurantOrder.id),
        )
        .where(*conditions)
        .group_by("dow")
        .order_by("dow")
    ).all()
    kitchen = int(
        db.session.scalar(
            select(func.count())
            .select_from(KitchenTicket)
            .join(RestaurantOrder, RestaurantOrder.id == KitchenTicket.order_id)
            .where(*conditions)
        )
        or 0
    )
    names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return {
        "by_order_type": [
            {"order_type": row[0], "orders": int(row[1]), "gross": money(row[2])} for row in by_type
        ],
        "by_hour": [{"hour": int(row[0]), "orders": int(row[1])} for row in hours],
        "by_weekday": [{"weekday": names[int(row[0])], "orders": int(row[1])} for row in weekdays],
        "kitchen_tickets": kitchen,
    }


def dataset_split(filters, period):
    """How much of the period is generated history and how much was keyed in here."""
    rows = db.session.execute(
        select(func.coalesce(RestaurantOrder.dataset_code, "UNKNOWN"), func.count(RestaurantOrder.id))
        .where(*filters.conditions(period))
        .group_by(RestaurantOrder.dataset_code)
    ).all()
    split = {row[0]: int(row[1]) for row in rows}
    demo = split.get(DEMO_DATASET, 0)
    live = split.get(LIVE_DATASET, 0)
    return {"synthetic": demo, "live": live, "other": sum(split.values()) - demo - live}


# ------------------------------------------------------------ dashboard views


def today_summary(business_id, branch_ids):
    today = datetime.now(PAKISTAN).date()
    period = make_period(today, today)
    filters = Filters(business_id=business_id, branch_ids=branch_ids)
    totals = _totals(filters, period)
    totals["date"] = today
    unpaused = Filters(business_id=business_id, branch_ids=branch_ids, statuses=())
    totals["active_orders"] = int(
        db.session.scalar(
            select(func.count())
            .select_from(RestaurantOrder)
            .where(*unpaused.conditions(period), RestaurantOrder.status.in_(OPEN_STATUSES))
        )
        or 0
    )
    totals["completed_orders"] = totals["orders"]
    totals["cancelled_orders"] = int(
        db.session.scalar(
            select(func.count())
            .select_from(RestaurantOrder)
            .where(*unpaused.conditions(period), RestaurantOrder.status == "cancelled")
        )
        or 0
    )
    return totals


def recent_orders(business_id, branch_ids, limit=8, statuses=None):
    conditions = [RestaurantOrder.business_id == business_id]
    if branch_ids:
        conditions.append(RestaurantOrder.branch_id.in_(branch_ids))
    if statuses:
        conditions.append(RestaurantOrder.status.in_(statuses))
    return list(
        db.session.scalars(
            select(RestaurantOrder)
            .where(*conditions)
            .order_by(RestaurantOrder.created_at.desc())
            .limit(limit)
        ).all()
    )


def branch_sales(business_id, branch_ids, start, end):
    period = Period(
        start_date=start.date(),
        end_date=(end - timedelta(seconds=1)).date(),
        start=start,
        end=end,
    )
    filters = Filters(business_id=business_id, branch_ids=branch_ids)
    return branch_comparison(filters, period)
