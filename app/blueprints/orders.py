"""Order history, receipts, hold/resume, remaining payment and refunds."""
from decimal import Decimal

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select

from app import db
from app.models import PaymentMethod, Printer, Product
from app.numbering import next_return_number
from app.operations_models import PrintJob, SalesReturn, SalesReturnLine
from app.order_models import (
    OrderItem,
    OrderPayment,
    OrderStatusEvent,
    ReceiptRecord,
    RestaurantOrder,
)
from app.platform_models import BusinessSetting
from app.security import (
    branch_required,
    can,
    context,
    permission_required,
    require_branch_access,
)
from app.services.audit import write_audit
from app.services.errors import LifecycleError, PaymentError, StockPolicyError, TenantAccessError
from app.services.orders import capture_payment, captured_total, finalize_receipt, hold_order, resume_order
from app.services.recipes import post_recipe_consumption
from app.services.returns import create_posted_return
from app.timeutil import utcnow
from app.blueprints.helpers import page_args, parse_date, total_pages

bp = Blueprint("orders", __name__, url_prefix="/orders")

STATUSES = ("open", "held", "partially_paid", "paid", "cancelled", "voided")


@bp.get("")
@branch_required
def index():
    ctx = context()
    status = request.args.get("status") or ""
    search = (request.args.get("q") or "").strip()
    start = parse_date(request.args.get("start"))
    end = parse_date(request.args.get("end"))
    page, size, offset = page_args()

    conditions = [
        RestaurantOrder.business_id == ctx.business_id,
        RestaurantOrder.branch_id.in_(ctx.allowed_branch_ids),
    ]
    if status in STATUSES:
        conditions.append(RestaurantOrder.status == status)
    if search:
        conditions.append(RestaurantOrder.order_number.ilike(f"%{search}%"))
    if start:
        from app.services.reporting import period_bounds

        bounds_start, _ = period_bounds(start, start)
        conditions.append(RestaurantOrder.created_at >= bounds_start)
    if end:
        from app.services.reporting import period_bounds

        _, bounds_end = period_bounds(end, end)
        conditions.append(RestaurantOrder.created_at < bounds_end)

    total = int(db.session.scalar(select(func.count()).select_from(RestaurantOrder).where(*conditions)) or 0)
    orders = db.session.scalars(
        select(RestaurantOrder)
        .where(*conditions)
        .order_by(RestaurantOrder.created_at.desc())
        .limit(size)
        .offset(offset)
    ).all()
    return render_template(
        "orders/index.html",
        orders=orders,
        status=status,
        search=search,
        start=start,
        end=end,
        page=page,
        pages=total_pages(total, size),
        total=total,
        statuses=STATUSES,
    )


def _load_order(order_id, ctx):
    order = db.session.get(RestaurantOrder, order_id)
    if order is None or order.business_id != ctx.business_id:
        abort(404)
    require_branch_access(order.branch_id)
    return order


def _order_detail(order):
    items = db.session.execute(
        select(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.id)
    ).all()
    payments = db.session.execute(
        select(OrderPayment, PaymentMethod)
        .join(PaymentMethod, PaymentMethod.id == OrderPayment.payment_method_id)
        .where(OrderPayment.order_id == order.id)
        .order_by(OrderPayment.paid_at)
    ).all()
    events = db.session.scalars(
        select(OrderStatusEvent)
        .where(OrderStatusEvent.order_id == order.id)
        .order_by(OrderStatusEvent.created_at)
    ).all()
    receipt = db.session.scalar(select(ReceiptRecord).where(ReceiptRecord.order_id == order.id))
    returns = db.session.scalars(
        select(SalesReturn).where(SalesReturn.order_id == order.id).order_by(SalesReturn.id)
    ).all()
    return {
        "lines": items,
        "payments": payments,
        "events": events,
        "receipt": receipt,
        "returns": returns,
        "paid": captured_total(order.id),
        "due": order.grand_total - captured_total(order.id),
    }


@bp.get("/<int:order_id>")
@branch_required
def show(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    return render_template(
        "orders/show.html",
        order=order,
        detail=_order_detail(order),
        payment_methods=db.session.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.business_id == ctx.business_id, PaymentMethod.enabled.is_(True))
            .order_by(PaymentMethod.label)
        ).all(),
    )


@bp.get("/<int:order_id>/receipt")
@branch_required
def receipt(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    detail = _order_detail(order)
    settings = db.session.scalar(
        select(BusinessSetting).where(BusinessSetting.business_id == ctx.business_id)
    )
    return render_template(
        "orders/receipt.html",
        order=order,
        detail=detail,
        settings=settings,
        branch=ctx.branch if ctx.branch and ctx.branch.id == order.branch_id else order_branch(order),
        business=ctx.business,
    )


def order_branch(order):
    from app.models import Branch

    return db.session.get(Branch, order.branch_id)


@bp.post("/<int:order_id>/receipt/print")
@branch_required
def print_receipt(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    receipt_row = db.session.scalar(select(ReceiptRecord).where(ReceiptRecord.order_id == order.id))
    if receipt_row is None:
        receipt_row = finalize_receipt(order.id, actor_business_id=ctx.business_id)
    printer = db.session.scalar(
        select(Printer).where(Printer.branch_id == order.branch_id, Printer.purpose == "receipt")
    )
    key = f"receipt:{receipt_row.id}:{int(utcnow().timestamp() // 1)}"
    job = PrintJob(
        business_id=ctx.business_id,
        branch_id=order.branch_id,
        printer_id=printer.id if printer is not None else None,
        job_type="receipt",
        status="sent",
        attempt_count=1,
        idempotency_key=key,
        related_receipt_id=receipt_row.id,
    )
    db.session.add(job)
    receipt_row.print_status = "sent"
    write_audit(
        action="print_receipt",
        entity_type="receipt_record",
        entity_id=receipt_row.id,
        business_id=ctx.business_id,
        branch_id=order.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Printed {receipt_row.receipt_number}",
    )
    db.session.commit()
    flash("Print job recorded. Use your browser print dialog for the paper copy.", "info")
    return redirect(url_for("orders.receipt", order_id=order.id))


@bp.post("/<int:order_id>/hold")
@branch_required
def hold(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    try:
        hold_order(order.id, actor_business_id=ctx.business_id)
        db.session.commit()
        flash(f"Order {order.order_number} held.", "info")
    except LifecycleError as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("orders.show", order_id=order.id))


@bp.post("/<int:order_id>/resume")
@branch_required
def resume(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    try:
        resume_order(order.id, actor_business_id=ctx.business_id)
        db.session.commit()
        flash(f"Order {order.order_number} reopened.", "info")
    except LifecycleError as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("orders.show", order_id=order.id))


@bp.post("/<int:order_id>/cancel")
@permission_required("order.void")
@branch_required
def cancel(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    if order.status == "paid":
        flash("A paid order is refunded, not cancelled. Use Refund.", "error")
        return redirect(url_for("orders.show", order_id=order.id))
    if order.status in ("cancelled", "voided"):
        flash("That order is already cancelled.", "warn")
        return redirect(url_for("orders.show", order_id=order.id))
    previous = order.status
    order.status = "cancelled"
    db.session.add(
        OrderStatusEvent(
            order_id=order.id,
            old_status=previous,
            new_status="cancelled",
            message=(request.form.get("reason") or "Cancelled at the till")[:200],
        )
    )
    write_audit(
        action="cancel_order",
        entity_type="restaurant_order",
        entity_id=order.id,
        business_id=ctx.business_id,
        branch_id=order.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Cancelled {order.order_number}",
    )
    db.session.commit()
    flash(f"Order {order.order_number} cancelled.", "info")
    return redirect(url_for("orders.show", order_id=order.id))


@bp.post("/<int:order_id>/pay")
@branch_required
def pay(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    try:
        amount = Decimal((request.form.get("amount") or "0").replace(",", "") or "0")
        method_id = request.form.get("payment_method_id", type=int)
        if not method_id:
            raise PaymentError("Choose a payment method.")
        capture_payment(
            order_id=order.id,
            payment_method_id=method_id,
            amount=amount,
            actor_business_id=ctx.business_id,
        )
        db.session.flush()
        if captured_total(order.id) >= order.grand_total and order.status != "paid":
            previous = order.status
            order.status = "paid"
            db.session.add(
                OrderStatusEvent(
                    order_id=order.id,
                    old_status=previous,
                    new_status="paid",
                    message="Balance settled",
                )
            )
            db.session.flush()
            post_recipe_consumption(order.id, actor_business_id=ctx.business_id)
            finalize_receipt(order.id, actor_business_id=ctx.business_id)
        db.session.commit()
        flash("Payment recorded.", "success")
    except (PaymentError, StockPolicyError, LifecycleError) as error:
        db.session.rollback()
        flash(str(error), "error")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Payment failed for order %s", order_id)
        flash("The payment could not be recorded.", "error")
    return redirect(url_for("orders.show", order_id=order.id))


@bp.post("/<int:order_id>/refund")
@permission_required("order.refund")
@branch_required
def refund(order_id):
    ctx = context()
    order = _load_order(order_id, ctx)
    if order.status != "paid":
        flash("Only a paid order can be refunded.", "error")
        return redirect(url_for("orders.show", order_id=order.id))
    try:
        items = {
            item.id: item
            for item in db.session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all()
        }
        lines = []
        for item_id in request.form.getlist("item_id"):
            try:
                key = int(item_id)
            except ValueError:
                continue
            item = items.get(key)
            if item is None:
                continue
            quantity = request.form.get(f"qty_{item.id}", type=int) or 0
            if quantity <= 0:
                continue
            quantity = min(quantity, item.quantity)
            amount = (Decimal(item.line_total) / Decimal(item.quantity) * quantity).quantize(Decimal("0.01"))
            lines.append({"order_item_id": item.id, "quantity": quantity, "amount": amount})
        if not lines:
            raise PaymentError("Select at least one item to refund.")
        method_id = request.form.get("payment_method_id", type=int)
        create_posted_return(
            order_id=order.id,
            actor_business_id=ctx.business_id,
            return_number=next_return_number(ctx.business_id),
            return_type="refund",
            reason=(request.form.get("reason") or "Customer refund")[:160],
            lines=lines,
            payment_method_id=method_id,
        )
        db.session.commit()
        flash("Refund posted and stock restored.", "success")
    except (PaymentError, LifecycleError, StockPolicyError, TenantAccessError) as error:
        db.session.rollback()
        flash(str(error), "error")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Refund failed for order %s", order_id)
        flash("The refund could not be posted.", "error")
    return redirect(url_for("orders.show", order_id=order.id))


@bp.get("/returns")
@branch_required
def returns():
    ctx = context()
    rows = db.session.execute(
        select(SalesReturn, RestaurantOrder)
        .join(RestaurantOrder, RestaurantOrder.id == SalesReturn.order_id)
        .where(
            SalesReturn.business_id == ctx.business_id,
            SalesReturn.branch_id.in_(ctx.allowed_branch_ids),
        )
        .order_by(SalesReturn.created_at.desc())
        .limit(100)
    ).all()
    return render_template("orders/returns.html", rows=rows)
