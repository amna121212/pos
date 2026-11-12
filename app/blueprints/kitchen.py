"""Kitchen board: tickets for the branch and their item status."""
from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app import db
from app.models import Product
from app.order_models import KitchenTicket, KitchenTicketItem, OrderItem, OrderStatusEvent, RestaurantOrder
from app.security import branch_required, can, context
from app.timeutil import utcnow

bp = Blueprint("kitchen", __name__, url_prefix="/kitchen")

TICKET_STATUSES = ("queued", "preparing", "ready", "served")
ITEM_STATUSES = ("queued", "preparing", "ready", "served")


def _ticket_or_404(ticket_id, ctx):
    ticket = db.session.get(KitchenTicket, ticket_id)
    if ticket is None:
        abort(404)
    order = db.session.get(RestaurantOrder, ticket.order_id)
    if order is None or order.business_id != ctx.business_id:
        abort(404)
    if order.branch_id not in ctx.allowed_branch_ids:
        abort(403)
    return ticket, order


@bp.get("")
@branch_required
def index():
    ctx = context()
    show = request.args.get("show") or "active"
    now = utcnow()
    query = (
        select(KitchenTicket, RestaurantOrder)
        .join(RestaurantOrder, RestaurantOrder.id == KitchenTicket.order_id)
        .where(
            RestaurantOrder.business_id == ctx.business_id,
            RestaurantOrder.branch_id == ctx.branch_id,
        )
    )
    if show == "active":
        # Only the current shift. Historical demo tickets would bury a live order.
        query = query.where(
            KitchenTicket.status.in_(("queued", "preparing", "ready")),
            KitchenTicket.created_at >= now - timedelta(hours=18),
        )
    elif show in ("ready", "served"):
        query = query.where(
            KitchenTicket.status == show,
            KitchenTicket.created_at >= now - timedelta(days=7),
        )
    else:
        query = query.where(KitchenTicket.created_at >= now - timedelta(days=7))
    rows = db.session.execute(query.order_by(KitchenTicket.created_at).limit(40)).all()

    boards = []
    for ticket, order in rows:
        items = db.session.execute(
            select(KitchenTicketItem, OrderItem, Product)
            .join(OrderItem, OrderItem.id == KitchenTicketItem.order_item_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(KitchenTicketItem.kitchen_ticket_id == ticket.id)
            .order_by(KitchenTicketItem.id)
        ).all()
        boards.append({"ticket": ticket, "order": order, "items": items})

    return render_template(
        "kitchen/index.html",
        boards=boards,
        show=show,
        can_update=can("kitchen.update"),
        statuses=TICKET_STATUSES,
    )


@bp.post("/<int:ticket_id>/status")
@branch_required
def set_status(ticket_id):
    ctx = context()
    ticket, order = _ticket_or_404(ticket_id, ctx)
    if not can("kitchen.update"):
        abort(403)
    status = request.form.get("status")
    if status not in TICKET_STATUSES:
        abort(400)
    ticket.status = status
    for row in db.session.scalars(
        select(KitchenTicketItem).where(KitchenTicketItem.kitchen_ticket_id == ticket.id)
    ).all():
        if row.status != "served":
            row.status = status
    if status == "ready":
        db.session.add(
            OrderStatusEvent(
                order_id=order.id,
                old_status=order.status,
                new_status=order.status,
                message=f"Kitchen ticket {ticket.ticket_number} ready",
            )
        )
    db.session.commit()
    flash(f"{ticket.ticket_number} marked {status}.", "info")
    return redirect(url_for("kitchen.index", show=request.form.get("show") or "active"))


@bp.post("/items/<int:item_id>/status")
@branch_required
def set_item_status(item_id):
    ctx = context()
    row = db.session.get(KitchenTicketItem, item_id)
    if row is None:
        abort(404)
    _ticket_or_404(row.kitchen_ticket_id, ctx)
    if not can("kitchen.update"):
        abort(403)
    status = request.form.get("status")
    if status not in ITEM_STATUSES:
        abort(400)
    row.status = status
    db.session.commit()
    return redirect(url_for("kitchen.index", show=request.form.get("show") or "active"))
