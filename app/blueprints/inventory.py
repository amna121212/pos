"""Stock on hand, adjustments, purchase orders, receiving and transfers."""
import re
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
    StockBatch,
    StockMovement,
    SupplierPurchaseItem,
    SupplierPurchaseOrder,
    StockTransferRequest,
)
from app.models import Branch, Product, Supplier
from app.numbering import next_purchase_order_number, next_transfer_number
from app.recipe_models import Recipe, RecipeLine
from app.security import any_permission_required, branch_required, can, context, permission_required
from app.services.audit import write_audit
from app.services.errors import StockPolicyError, TenantAccessError
from app.services.inventory import apply_stock_delta
from app.services.transfers import post_transfer
from app.timeutil import utcnow
from app.blueprints.helpers import page_args, total_pages

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


def _amount(raw, label):
    """A money or stock figure that is allowed to be zero."""
    text = (raw or "").strip().replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{label} must be a number.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value.quantize(Decimal("0.01"))


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
            for index in range(16):
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


# ------------------------------------------------------- inventory item CRUD

UNITS = ("pcs", "kg", "g", "litre", "ml", "pack", "dozen", "box")


@bp.route("/ingredients/new", methods=["GET", "POST"])
@permission_required("inventory.adjust")
@branch_required
def ingredient_new():
    ctx = context()
    values = {"sku": "", "name": "", "unit": "kg", "reorder_level": "0", "standard_cost": "0", "product_id": ""}
    if request.method == "POST":
        values = {
            "sku": request.form.get("sku", ""),
            "name": request.form.get("name", ""),
            "unit": request.form.get("unit", ""),
            "reorder_level": request.form.get("reorder_level", ""),
            "standard_cost": request.form.get("standard_cost", ""),
            "product_id": request.form.get("product_id", ""),
        }
        try:
            item = _save_ingredient(ctx, None, request.form)
            db.session.add(item)
            db.session.flush()
            write_audit(
                action="create_ingredient",
                entity_type="inventory_item",
                entity_id=item.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Added ingredient {item.sku} {item.name}",
            )
            db.session.commit()
            flash(f"{item.name} added.", "success")
            return redirect(url_for("inventory.ingredients"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That SKU is already used in this business.", "error")
    return render_template(
        "inventory/ingredient_form.html",
        item=None,
        values=values,
        units=UNITS,
        products=_linkable_products(ctx.business_id),
    )


@bp.route("/ingredients/<int:item_id>/edit", methods=["GET", "POST"])
@permission_required("inventory.adjust")
@branch_required
def ingredient_edit(item_id):
    ctx = context()
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.business_id != ctx.business_id:
        abort(404)
    values = {
        "sku": item.sku,
        "name": item.name,
        "unit": item.unit,
        "reorder_level": str(item.reorder_level),
        "standard_cost": str(item.standard_cost),
        "product_id": str(item.product_id or ""),
    }
    if request.method == "POST":
        values = {
            "sku": item.sku,
            "name": request.form.get("name", ""),
            "unit": request.form.get("unit", ""),
            "reorder_level": request.form.get("reorder_level", ""),
            "standard_cost": request.form.get("standard_cost", ""),
            "product_id": request.form.get("product_id", ""),
        }
        try:
            _save_ingredient(ctx, item, request.form)
            write_audit(
                action="update_ingredient",
                entity_type="inventory_item",
                entity_id=item.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Updated ingredient {item.sku}",
            )
            db.session.commit()
            flash("Ingredient saved.", "success")
            return redirect(url_for("inventory.ingredients"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template(
        "inventory/ingredient_form.html",
        item=item,
        values=values,
        units=UNITS,
        products=_linkable_products(ctx.business_id),
    )


def _linkable_products(business_id):
    return db.session.scalars(
        select(Product).where(Product.business_id == business_id).order_by(Product.name)
    ).all()


def _save_ingredient(ctx, item, form):
    """Validate and fill an InventoryItem from a form. Raises ValueError."""
    name = (form.get("name") or "").strip()
    unit = (form.get("unit") or "").strip()
    if len(name) < 2:
        raise ValueError("Enter the ingredient name.")
    if unit not in UNITS:
        raise ValueError("Choose a unit of measure.")
    reorder = _amount(form.get("reorder_level"), "Reorder level")
    cost = _amount(form.get("standard_cost"), "Standard cost")
    product_id = form.get("product_id", type=int)
    if product_id is not None and db.session.get(Product, product_id) is None:
        raise ValueError("That product is not part of this business.")
    if item is None:
        sku = (form.get("sku") or "").strip().upper()
        if not re.match(r"^[A-Z0-9][A-Z0-9-]{1,47}$", sku):
            raise ValueError("SKU must be 2-48 characters: letters, digits or dash.")
        item = InventoryItem(
            business_id=ctx.business_id, sku=sku, name=name[:130], unit=unit,
            reorder_level=reorder, standard_cost=cost,
        )
    else:
        item.name = name[:130]
        item.unit = unit
        item.reorder_level = reorder
        item.standard_cost = cost
    item.product_id = product_id
    return item


@bp.post("/ingredients/<int:item_id>/delete")
@permission_required("inventory.adjust")
@branch_required
def ingredient_delete(item_id):
    ctx = context()
    item = db.session.get(InventoryItem, item_id)
    if item is None or item.business_id != ctx.business_id:
        abort(404)
    references = {
        "stock movements": db.session.scalar(
            select(func.count()).select_from(StockMovement).where(StockMovement.item_id == item.id)
        ),
        "recipe lines": db.session.scalar(
            select(func.count()).select_from(RecipeLine).where(RecipeLine.inventory_item_id == item.id)
        ),
        "purchase lines": db.session.scalar(
            select(func.count())
            .select_from(SupplierPurchaseItem)
            .where(SupplierPurchaseItem.item_id == item.id)
        ),
        "goods received": db.session.scalar(
            select(func.count())
            .select_from(GoodsReceiptItem)
            .join(SupplierPurchaseItem, SupplierPurchaseItem.id == GoodsReceiptItem.purchase_item_id)
            .where(SupplierPurchaseItem.item_id == item.id)
        ),
        "stock batches": db.session.scalar(
            select(func.count()).select_from(StockBatch).where(StockBatch.item_id == item.id)
        ),
    }
    used = {label: int(count or 0) for label, count in references.items()}
    blocking = {label: count for label, count in used.items() if count}
    if blocking:
        detail = ", ".join(f"{count} {label}" for label, count in blocking.items())
        flash(f"{item.name} is in use ({detail}). It cannot be deleted.", "error")
        return redirect(url_for("inventory.ingredients"))

    stock = db.session.scalars(
        select(BranchStock).where(BranchStock.item_id == item.id)
    ).all()
    for row in stock:
        db.session.delete(row)
    name = item.name
    db.session.delete(item)
    write_audit(
        action="delete_ingredient",
        entity_type="inventory_item",
        entity_id=item_id,
        business_id=ctx.business_id,
        branch_id=ctx.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Deleted ingredient {name}",
    )
    db.session.commit()
    flash(f"{name} deleted.", "success")
    return redirect(url_for("inventory.ingredients"))


# --------------------------------------------------------------- recipe CRUD


def _recipe_lines(form):
    """Read the repeated ingredient rows from a recipe form."""
    lines = []
    seen = set()
    for index in range(12):
        item_id = form.get(f"item_id_{index}", type=int)
        if not item_id:
            continue
        if item_id in seen:
            raise ValueError("The same ingredient is listed twice.")
        raw = (form.get(f"qty_{index}") or "").strip()
        if not raw:
            raise ValueError("Every ingredient row needs a quantity.")
        try:
            qty = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            raise ValueError("Quantities must be numbers.")
        if qty <= 0:
            raise ValueError("Quantities must be greater than zero.")
        seen.add(item_id)
        lines.append((item_id, qty))
    if not lines:
        raise ValueError("Add at least one ingredient.")
    return lines


def _save_recipe(ctx, recipe, form):
    product_id = form.get("product_id", type=int)
    product = db.session.get(Product, product_id) if product_id else None
    if product is None or product.business_id != ctx.business_id:
        raise ValueError("Choose one of your own products.")
    yield_qty = _decimal(form.get("yield_qty") or "1", "Yield")
    notes = (form.get("notes") or "").strip()[:240] or None
    is_active = bool(form.get("is_active"))
    lines = _recipe_lines(form)

    if recipe is None:
        recipe = Recipe(
            business_id=ctx.business_id,
            product_id=product.id,
            name=f"{product.name} recipe",
            yield_qty=yield_qty,
            notes=notes,
            is_active=is_active,
        )
        db.session.add(recipe)
        db.session.flush()
    else:
        recipe.product_id = product.id
        recipe.name = f"{product.name} recipe"
        recipe.yield_qty = yield_qty
        recipe.notes = notes
        recipe.is_active = is_active
        for line in db.session.scalars(
            select(RecipeLine).where(RecipeLine.recipe_id == recipe.id)
        ).all():
            db.session.delete(line)
        db.session.flush()

    for item_id, qty in lines:
        item = db.session.get(InventoryItem, item_id)
        if item is None or item.business_id != ctx.business_id:
            raise ValueError("An ingredient on this recipe is not part of this business.")
        db.session.add(
            RecipeLine(
                recipe_id=recipe.id,
                inventory_item_id=item.id,
                quantity=qty,
                unit=item.unit,
            )
        )
    return recipe


@bp.route("/recipes/new", methods=["GET", "POST"])
@permission_required("inventory.adjust")
@branch_required
def recipe_new():
    ctx = context()
    values = {"product_id": "", "yield_qty": "1", "notes": ""}
    if request.method == "POST":
        values = {
            "product_id": request.form.get("product_id", ""),
            "yield_qty": request.form.get("yield_qty", ""),
            "notes": request.form.get("notes", ""),
        }
        try:
            recipe = _save_recipe(ctx, None, request.form)
            write_audit(
                action="create_recipe",
                entity_type="recipe",
                entity_id=recipe.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Added recipe for {recipe.name}",
            )
            db.session.commit()
            flash("Recipe added.", "success")
            return redirect(url_for("inventory.recipes"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That product already has a recipe.", "error")
    return render_template(
        "inventory/recipe_form.html",
        recipe=None,
        values=values,
        products=_recipes_free_products(ctx.business_id, None),
        items=_items(ctx.business_id),
        lines=[],
        rows=range(8),
    )


def _recipes_free_products(business_id, recipe_id):
    taken = select(Recipe.product_id).where(Recipe.product_id.is_not(None))
    if recipe_id is not None:
        taken = taken.where(Recipe.id != recipe_id)
    return db.session.scalars(
        select(Product)
        .where(Product.business_id == business_id, Product.id.notin_(taken))
        .order_by(Product.name)
    ).all()


@bp.route("/recipes/<int:recipe_id>/edit", methods=["GET", "POST"])
@permission_required("inventory.adjust")
@branch_required
def recipe_edit(recipe_id):
    ctx = context()
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None or recipe.business_id != ctx.business_id:
        abort(404)
    values = {
        "product_id": str(recipe.product_id),
        "yield_qty": str(recipe.yield_qty),
        "notes": recipe.notes or "",
    }
    if request.method == "POST":
        values = {
            "product_id": request.form.get("product_id", ""),
            "yield_qty": request.form.get("yield_qty", ""),
            "notes": request.form.get("notes", ""),
        }
        try:
            _save_recipe(ctx, recipe, request.form)
            write_audit(
                action="update_recipe",
                entity_type="recipe",
                entity_id=recipe.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Updated recipe {recipe.name}",
            )
            db.session.commit()
            flash("Recipe saved.", "success")
            return redirect(url_for("inventory.recipes"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    lines = db.session.execute(
        select(RecipeLine, InventoryItem)
        .join(InventoryItem, InventoryItem.id == RecipeLine.inventory_item_id)
        .where(RecipeLine.recipe_id == recipe.id)
        .order_by(RecipeLine.id)
    ).all()
    return render_template(
        "inventory/recipe_form.html",
        recipe=recipe,
        values=values,
        products=_recipes_free_products(ctx.business_id, recipe.id) + [recipe_product(recipe)],
        items=_items(ctx.business_id),
        lines=lines,
        rows=range(max(8, len(lines) + 2)),
    )


def recipe_product(recipe):
    return db.session.get(Product, recipe.product_id)


@bp.post("/recipes/<int:recipe_id>/delete")
@permission_required("inventory.adjust")
@branch_required
def recipe_delete(recipe_id):
    ctx = context()
    recipe = db.session.get(Recipe, recipe_id)
    if recipe is None or recipe.business_id != ctx.business_id:
        abort(404)
    for line in db.session.scalars(select(RecipeLine).where(RecipeLine.recipe_id == recipe.id)).all():
        db.session.delete(line)
    name = recipe.name
    db.session.flush()
    db.session.delete(recipe)
    write_audit(
        action="delete_recipe",
        entity_type="recipe",
        entity_id=recipe_id,
        business_id=ctx.business_id,
        branch_id=ctx.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Deleted recipe {name}",
    )
    db.session.commit()
    flash("Recipe deleted.", "success")
    return redirect(url_for("inventory.recipes"))
