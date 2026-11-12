"""Stock on hand, adjustments, purchase orders, receiving and transfers."""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import db
from app.inventory_models import (
    BranchStock,
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryItem,
    StockAdjustment,
    StockMovement,
    SupplierPurchaseItem,
    SupplierPurchaseOrder,
    StockTransferRequest,
)
from app.models import Branch, Product, Supplier
from app.numbering import next_purchase_order_number, next_transfer_number
from app.security import any_permission_required, branch_required, can, context, permission_required
from app.services.audit import write_audit
from app.services.errors import StockPolicyError, TenantAccessError
from app.services.inventory import apply_stock_delta
from app.services.transfers import post_transfer
from app.timeutil import utcnow
from app.blueprints.helpers import page_args, total_pages

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


def _decimal(raw, label, *, allow_negative=False, default="0"):
    text = (raw or "").strip().replace(",", "")
    if not text:
        text = default
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{label} must be a number.")
    if not allow_negative and value <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return value


def _items(business_id):
    return db.session.scalars(
        select(InventoryItem).where(InventoryItem.business_id == business_id).order_by(InventoryItem.name)
    ).all()


@bp.get("")
@any_permission_required("inventory.adjust", "inventory.purchase", "inventory.transfer")
@branch_required
def index():
    ctx = context()
    search = (request.args.get("q") or "").strip()
    low_only = request.args.get("low") == "1"
    page, size, offset = page_args()

    conditions = [
        BranchStock.business_id == ctx.business_id,
        BranchStock.branch_id == ctx.branch_id,
    ]
    query = (
        select(BranchStock, InventoryItem)
        .join(InventoryItem, InventoryItem.id == BranchStock.item_id)
        .where(*conditions)
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(InventoryItem.name.ilike(pattern) | InventoryItem.sku.ilike(pattern))
    if low_only:
        query = query.where(BranchStock.quantity <= InventoryItem.reorder_level)

    total = int(
        db.session.scalar(
            select(func.count())
            .select_from(BranchStock)
            .join(InventoryItem, InventoryItem.id == BranchStock.item_id)
            .where(*conditions, *(([InventoryItem.name.ilike(f"%{search}%")] if search else [])))
        )
        or 0
    )
    rows = db.session.execute(query.order_by(InventoryItem.name).limit(size).offset(offset)).all()
    return render_template(
        "inventory/index.html",
        rows=rows,
        search=search,
        low_only=low_only,
        page=page,
        pages=total_pages(total, size),
        total=total,
        can_adjust=can("inventory.adjust"),
    )


@bp.get("/ingredients")
@any_permission_required("inventory.adjust", "inventory.purchase", "inventory.transfer")
@branch_required
def ingredients():
    """Every stock item for the business, with what this branch holds."""
    ctx = context()
    search = (request.args.get("q") or "").strip()
    query = select(InventoryItem).where(InventoryItem.business_id == ctx.business_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(InventoryItem.name.ilike(pattern) | InventoryItem.sku.ilike(pattern))
    items = db.session.scalars(query.order_by(InventoryItem.name)).all()
    stock = {
        row.item_id: row.quantity
        for row in db.session.scalars(
            select(BranchStock).where(
                BranchStock.branch_id == ctx.branch_id,
                BranchStock.item_id.in_([item.id for item in items] or [0]),
            )
        ).all()
    }
    used_in = _recipe_usage(ctx.business_id)
    return render_template(
        "inventory/ingredients.html",
        items=items,
        stock=stock,
        used_in=used_in,
        search=search,
    )


def _recipe_usage(business_id):
    from app.recipe_models import Recipe, RecipeLine

    rows = db.session.execute(
        select(RecipeLine.inventory_item_id, func.count(RecipeLine.id))
        .join(Recipe, Recipe.id == RecipeLine.recipe_id)
        .where(Recipe.business_id == business_id)
        .group_by(RecipeLine.inventory_item_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


@bp.get("/recipes")
@any_permission_required("inventory.adjust", "inventory.purchase", "inventory.transfer")
@branch_required
def recipes():
    """Recipes decide which ingredients a paid sale consumes."""
    from app.recipe_models import Recipe, RecipeLine

    ctx = context()
    rows = db.session.execute(
        select(
            Recipe,
            Product.name,
            Product.sku,
            func.count(RecipeLine.id),
        )
        .join(Product, Product.id == Recipe.product_id)
        .outerjoin(RecipeLine, RecipeLine.recipe_id == Recipe.id)
        .where(Recipe.business_id == ctx.business_id)
        .group_by(Recipe.id, Product.name, Product.sku)
        .order_by(Product.name)
    ).all()
    return render_template("inventory/recipes.html", rows=rows)


@bp.get("/movements")
@any_permission_required("inventory.adjust", "inventory.purchase", "inventory.transfer")
@branch_required
def movements():
    ctx = context()
    rows = db.session.execute(
        select(StockMovement, InventoryItem)
        .join(InventoryItem, InventoryItem.id == StockMovement.item_id)
        .where(
            StockMovement.business_id == ctx.business_id,
            StockMovement.branch_id == ctx.branch_id,
        )
        .order_by(StockMovement.created_at.desc())
        .limit(100)
    ).all()
    return render_template("inventory/movements.html", rows=rows)


@bp.route("/adjust", methods=["GET", "POST"])
@permission_required("inventory.adjust")
@branch_required
def adjust():
    ctx = context()
    items = _items(ctx.business_id)
    if request.method == "POST":
        try:
            item_id = request.form.get("item_id", type=int)
            item = next((row for row in items if row.id == item_id), None)
            if item is None:
                raise ValueError("Choose one of your own inventory items.")
            delta = _decimal(request.form.get("delta"), "Quantity change", allow_negative=True)
            if delta == 0:
                raise ValueError("Quantity change cannot be zero.")
            reason = (request.form.get("reason") or "").strip()
            if len(reason) < 3:
                raise ValueError("Give a short reason for the adjustment.")
            code = f"ADJ-{ctx.branch_id}-{int(utcnow().timestamp())}"
            db.session.add(
                StockAdjustment(
                    business_id=ctx.business_id,
                    branch_id=ctx.branch_id,
                    item_id=item.id,
                    adjustment_code=code,
                    delta_qty=delta,
                    reason=reason[:150],
                )
            )
            apply_stock_delta(
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                item_id=item.id,
                movement_type="adjustment",
                delta_qty=delta,
                reference_code=code,
            )
            write_audit(
                action="stock_adjustment",
                entity_type="inventory_item",
                entity_id=item.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"{code} {delta} {item.unit} of {item.sku}",
            )
            db.session.commit()
            flash("Adjustment posted.", "success")
            return redirect(url_for("inventory.index"))
        except (ValueError, StockPolicyError, TenantAccessError) as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That adjustment was already applied. Try again.", "error")
    return render_template("inventory/adjust.html", items=items)


@bp.get("/purchases")
@permission_required("inventory.purchase")
@branch_required
def purchases():
    ctx = context()
    orders = db.session.execute(
        select(SupplierPurchaseOrder, Supplier)
        .join(Supplier, Supplier.id == SupplierPurchaseOrder.supplier_id)
        .where(
            SupplierPurchaseOrder.business_id == ctx.business_id,
            SupplierPurchaseOrder.branch_id == ctx.branch_id,
        )
        .order_by(SupplierPurchaseOrder.created_at.desc())
        .limit(60)
    ).all()
    receipts = {
        row.purchase_order_id
        for row in db.session.scalars(
            select(GoodsReceipt).where(GoodsReceipt.business_id == ctx.business_id)
        ).all()
    }
    return render_template("inventory/purchases.html", orders=orders, received=receipts)


@bp.route("/purchases/new", methods=["GET", "POST"])
@permission_required("inventory.purchase")
@branch_required
def purchase_new():
    ctx = context()
    suppliers = db.session.scalars(
        select(Supplier).where(Supplier.business_id == ctx.business_id).order_by(Supplier.name)
    ).all()
    items = _items(ctx.business_id)
    if request.method == "POST":
        try:
            supplier_id = request.form.get("supplier_id", type=int)
            supplier = next((row for row in suppliers if row.id == supplier_id), None)
            if supplier is None:
                raise ValueError("Choose one of your own suppliers.")
            lines = []
            for index in range(12):
                item_id = request.form.get(f"item_id_{index}", type=int)
                if not item_id:
                    continue
                item = next((row for row in items if row.id == item_id), None)
                if item is None:
                    raise ValueError("A purchase line uses an unknown item.")
                quantity = _decimal(request.form.get(f"qty_{index}"), "Ordered quantity")
                unit_cost = _decimal(request.form.get(f"cost_{index}"), "Unit cost", allow_negative=True)
                lines.append((item, quantity, unit_cost))
            if not lines:
                raise ValueError("Add at least one purchase line.")
            purchase = SupplierPurchaseOrder(
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                supplier_id=supplier.id,
                po_number=next_purchase_order_number(ctx.business_id, ctx.branch),
                status="ordered",
            )
            db.session.add(purchase)
            db.session.flush()
            for item, quantity, unit_cost in lines:
                db.session.add(
                    SupplierPurchaseItem(
                        purchase_order_id=purchase.id,
                        item_id=item.id,
                        qty_ordered=quantity,
                        unit_cost=unit_cost,
                    )
                )
            write_audit(
                action="create_purchase_order",
                entity_type="supplier_purchase_order",
                entity_id=purchase.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Raised {purchase.po_number}",
            )
            db.session.commit()
            flash(f"Purchase order {purchase.po_number} raised.", "success")
            return redirect(url_for("inventory.purchases"))
        except (ValueError, StockPolicyError) as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That purchase order number was taken. Try again.", "error")
    return render_template(
        "inventory/purchase_new.html", suppliers=suppliers, items=items, rows=range(6)
    )


@bp.post("/purchases/<int:purchase_id>/receive")
@permission_required("inventory.purchase")
@branch_required
def purchase_receive(purchase_id):
    ctx = context()
    purchase = db.session.get(SupplierPurchaseOrder, purchase_id)
    if purchase is None or purchase.business_id != ctx.business_id:
        abort(404)
    if purchase.branch_id != ctx.branch_id:
        abort(403)
    try:
        existing = db.session.scalar(
            select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == purchase.id)
        )
        if existing is not None:
            flash("That purchase order is already received.", "warn")
            return redirect(url_for("inventory.purchases"))
        receipt = GoodsReceipt(
            purchase_order_id=purchase.id,
            business_id=ctx.business_id,
            branch_id=purchase.branch_id,
            receipt_number=f"GRN-{purchase.po_number}",
            received_at=utcnow(),
        )
        db.session.add(receipt)
        db.session.flush()
        for line in db.session.scalars(
            select(SupplierPurchaseItem).where(SupplierPurchaseItem.purchase_order_id == purchase.id)
        ).all():
            db.session.add(
                GoodsReceiptItem(
                    goods_receipt_id=receipt.id,
                    purchase_item_id=line.id,
                    quantity=line.qty_ordered,
                )
            )
            apply_stock_delta(
                business_id=ctx.business_id,
                branch_id=purchase.branch_id,
                item_id=line.item_id,
                movement_type="purchase_receipt",
                delta_qty=line.qty_ordered,
                reference_code=receipt.receipt_number,
            )
        purchase.status = "received"
        write_audit(
            action="receive_purchase",
            entity_type="goods_receipt",
            entity_id=receipt.id,
            business_id=ctx.business_id,
            branch_id=purchase.branch_id,
            actor_user_id=ctx.user.id,
            message=f"Received {receipt.receipt_number}",
        )
        db.session.commit()
        flash("Stock received and added to the branch.", "success")
    except (StockPolicyError, TenantAccessError) as error:
        db.session.rollback()
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("That receipt already exists.", "error")
    return redirect(url_for("inventory.purchases"))


@bp.get("/transfers")
@permission_required("inventory.transfer")
@branch_required
def transfers():
    ctx = context()
    rows = db.session.scalars(
        select(StockTransferRequest)
        .where(StockTransferRequest.business_id == ctx.business_id)
        .order_by(StockTransferRequest.created_at.desc())
        .limit(50)
    ).all()
    branches = {
        branch.id: branch
        for branch in db.session.scalars(
            select(Branch).where(Branch.business_id == ctx.business_id)
        ).all()
    }
    return render_template("inventory/transfers.html", rows=rows, branches=branches)


@bp.route("/transfers/new", methods=["GET", "POST"])
@permission_required("inventory.transfer")
@branch_required
def transfer_new():
    ctx = context()
    branches = db.session.scalars(
        select(Branch)
        .where(Branch.business_id == ctx.business_id, Branch.id != ctx.branch_id)
        .order_by(Branch.code)
    ).all()
    items = _items(ctx.business_id)
    if request.method == "POST":
        try:
            to_branch_id = request.form.get("to_branch_id", type=int)
            if not any(branch.id == to_branch_id for branch in branches):
                raise ValueError("Choose another branch of this business.")
            item_id = request.form.get("item_id", type=int)
            item = next((row for row in items if row.id == item_id), None)
            if item is None:
                raise ValueError("Choose an inventory item.")
            quantity = _decimal(request.form.get("quantity"), "Transfer quantity")
            transfer = post_transfer(
                business_id=ctx.business_id,
                from_branch_id=ctx.branch_id,
                to_branch_id=to_branch_id,
                transfer_number=next_transfer_number(),
                lines=[{"item_id": item.id, "quantity": quantity}],
                note=(request.form.get("note") or "")[:200],
            )
            write_audit(
                action="post_transfer",
                entity_type="stock_transfer",
                entity_id=transfer.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"{transfer.transfer_number} sent",
            )
            db.session.commit()
            flash("Transfer posted and stock moved.", "success")
            return redirect(url_for("inventory.transfers"))
        except (ValueError, StockPolicyError, TenantAccessError) as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That transfer number was taken. Try again.", "error")
    return render_template("inventory/transfer_new.html", branches=branches, items=items)
