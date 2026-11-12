"""Supplier directory, purchase orders and goods received."""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import db
from app.inventory_models import (
    GoodsReceipt,
    SupplierPurchaseItem,
    SupplierPurchaseOrder,
)
from app.models import Supplier
from app.security import any_permission_required, branch_required, can, context, permission_required
from app.services.audit import write_audit

bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")

CITIES = ("Lahore", "Karachi", "Islamabad", "Faisalabad", "Multan", "Rawalpindi")


def _supplier_total(po_ids):
    """Purchase value per supplier, from the ordered quantity and unit cost."""
    if not po_ids:
        return {}
    rows = db.session.execute(
        select(
            SupplierPurchaseOrder.supplier_id,
            func.count(func.distinct(SupplierPurchaseOrder.id)),
            func.coalesce(func.sum(SupplierPurchaseItem.qty_ordered * SupplierPurchaseItem.unit_cost), 0),
        )
        .join(SupplierPurchaseItem, SupplierPurchaseItem.purchase_order_id == SupplierPurchaseOrder.id)
        .where(SupplierPurchaseOrder.id.in_(po_ids))
        .group_by(SupplierPurchaseOrder.supplier_id)
    ).all()
    return {row[0]: {"orders": int(row[1]), "value": row[2]} for row in rows}


@bp.get("")
@any_permission_required("inventory.purchase", "report.view")
@branch_required
def index():
    ctx = context()
    search = (request.args.get("q") or "").strip()
    query = select(Supplier).where(Supplier.business_id == ctx.business_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(Supplier.name.ilike(pattern) | Supplier.city.ilike(pattern))
    suppliers = db.session.scalars(query.order_by(Supplier.name)).all()

    totals = _supplier_total(
        db.session.scalars(
            select(SupplierPurchaseOrder.id).where(SupplierPurchaseOrder.business_id == ctx.business_id)
        ).all()
    )
    return render_template(
        "suppliers/index.html",
        suppliers=suppliers,
        totals=totals,
        search=search,
        can_manage=can("inventory.purchase"),
    )


def _form_values(supplier=None):
    if supplier is None:
        return {"name": "", "city": "Lahore", "lead_time_days": "2"}
    return {
        "name": supplier.name,
        "city": supplier.city,
        "lead_time_days": str(supplier.lead_time_days),
    }


def _validate(form):
    name = (form.get("name") or "").strip()
    if len(name) < 2:
        raise ValueError("Supplier name is required.")
    city = (form.get("city") or "Lahore").strip()
    if len(city) < 2:
        raise ValueError("City is required.")
    try:
        lead = int(str(form.get("lead_time_days") or "2").strip())
    except ValueError:
        raise ValueError("Lead time must be a whole number of days.")
    if lead < 0 or lead > 365:
        raise ValueError("Lead time must be between 0 and 365 days.")
    return name[:130], city[:80], lead


@bp.route("/new", methods=["GET", "POST"])
@permission_required("inventory.purchase")
@branch_required
def new():
    ctx = context()
    values = _form_values()
    if request.method == "POST":
        values = {key: request.form.get(key, "") for key in ("name", "city", "lead_time_days")}
        try:
            name, city, lead = _validate(request.form)
            supplier = Supplier(
                business_id=ctx.business_id,
                name=name,
                city=city,
                lead_time_days=lead,
                is_synthetic=False,
            )
            db.session.add(supplier)
            db.session.flush()
            write_audit(
                action="create_supplier",
                entity_type="supplier",
                entity_id=supplier.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Added supplier {name}",
            )
            db.session.commit()
            flash(f"{name} added.", "success")
            return redirect(url_for("suppliers.index"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("A supplier with that name already exists for this business.", "error")
    return render_template("suppliers/form.html", supplier=None, values=values, cities=CITIES)


@bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
@permission_required("inventory.purchase")
@branch_required
def edit(supplier_id):
    ctx = context()
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None or supplier.business_id != ctx.business_id:
        abort(404)
    values = _form_values(supplier)
    if request.method == "POST":
        values = {key: request.form.get(key, "") for key in ("name", "city", "lead_time_days")}
        try:
            name, city, lead = _validate(request.form)
            supplier.name = name
            supplier.city = city
            supplier.lead_time_days = lead
            write_audit(
                action="update_supplier",
                entity_type="supplier",
                entity_id=supplier.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Updated supplier {name}",
            )
            db.session.commit()
            flash("Supplier saved.", "success")
            return redirect(url_for("suppliers.detail", supplier_id=supplier.id))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("Another supplier already uses that name.", "error")
    return render_template("suppliers/form.html", supplier=supplier, values=values, cities=CITIES)


@bp.get("/<int:supplier_id>")
@any_permission_required("inventory.purchase", "report.view")
@branch_required
def detail(supplier_id):
    ctx = context()
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None or supplier.business_id != ctx.business_id:
        abort(404)

    orders = db.session.execute(
        select(
            SupplierPurchaseOrder,
            func.coalesce(func.sum(SupplierPurchaseItem.qty_ordered * SupplierPurchaseItem.unit_cost), 0),
        )
        .outerjoin(SupplierPurchaseItem, SupplierPurchaseItem.purchase_order_id == SupplierPurchaseOrder.id)
        .where(SupplierPurchaseOrder.supplier_id == supplier.id)
        .group_by(SupplierPurchaseOrder.id)
        .order_by(SupplierPurchaseOrder.created_at.desc())
        .limit(40)
    ).all()

    received = {
        row.purchase_order_id
        for row in db.session.scalars(
            select(GoodsReceipt).where(GoodsReceipt.business_id == ctx.business_id)
        ).all()
    }
    total_value = sum((Decimal(str(row[1])) for row in orders), Decimal("0"))
    received_count = sum(1 for order, _value in orders if order.id in received)

    return render_template(
        "suppliers/detail.html",
        supplier=supplier,
        orders=orders,
        received=received,
        received_count=received_count,
        total_value=total_value,
        can_manage=can("inventory.purchase"),
    )
