"""The till screen: pick items, adjust the basket, take payment."""
from decimal import Decimal

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from app import db
from app import cart as basket
from app.models import BranchProduct, Category, DiningTable, PaymentMethod, Product
from app.operations_models import CashierShift, ProductBarcode
from app.security import branch_required, can, context
from app.services.errors import PaymentError, StockPolicyError, TenantAccessError
from app.services.pos_orders import ORDER_TYPES, create_order, quote

bp = Blueprint("pos", __name__, url_prefix="/pos")


def _money_value(raw, default="0"):
    text = (raw or "").strip().replace(",", "")
    if not text:
        text = default
    try:
        return Decimal(text)
    except Exception:
        raise PaymentError(f"'{raw}' is not a valid amount.")


def _wants_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"


def _request_discount(strict=False):
    """The discount typed in the checkout form, or (None, 0).

    `strict` is used by the live re-quote so an out-of-range percentage is
    reported; cart edits ignore it rather than breaking the till.
    """
    try:
        raw = (request.form.get("discount_value") or "").strip()
        if not raw:
            return None, Decimal("0")
        value = _money_value(raw)
        if value <= 0:
            return None, Decimal("0")
        kind = request.form.get("discount_kind") or "percent"
        if kind == "percent" and value >= 100:
            raise PaymentError("A percentage discount must be below 100.")
        return kind, value
    except PaymentError:
        if strict:
            raise
        return None, Decimal("0")


def _quote_lines(lines, discount_kind=None, discount_value=0):
    ctx = context()
    return quote(
        business_id=ctx.business_id,
        branch_id=ctx.branch_id,
        lines=lines,
        discount_kind=discount_kind,
        discount_value=discount_value,
    )


def _cart_payload(extra=None, strict_discount=False):
    ctx = context()
    kind, value = _request_discount(strict=strict_discount)
    lines = basket.get_cart()["lines"]
    try:
        priced = _quote_lines(lines, kind, value)
    except PaymentError:
        if kind:
            # The discount was the problem, not the basket: keep the items and
            # show the bill without it. The live re-quote reports the reason.
            priced = _quote_lines(lines)
        else:
            basket.clear()
            flash("The basket was cleared because an item is no longer available.", "warn")
            priced = _quote_lines([])
    except TenantAccessError:
        basket.clear()
        flash("The basket was cleared because an item is no longer available.", "warn")
        priced = _quote_lines([])
    html = render_template("pos/_cart.html", cart=basket.get_cart(), quote=priced)
    payload = {
        "ok": True,
        "html": html,
        "lines": len(basket.get_cart()["lines"]),
        "grand": str(priced["grand"]),
        "discount": str(priced["discount"]),
        "subtotal": str(priced["subtotal"]),
        "tax": str(priced["tax"]),
    }
    if extra:
        payload.update(extra)
    return jsonify(payload)


def _back_to_till():
    return redirect(url_for("pos.index"))


def _product_options(product_id):
    """Modifier groups (with their options) defined for one product."""
    from app.order_models import MenuModifierGroup, MenuModifierOption

    groups = db.session.scalars(
        select(MenuModifierGroup)
        .where(MenuModifierGroup.product_id == product_id)
        .order_by(MenuModifierGroup.id)
    ).all()
    result = []
    for group in groups:
        options = db.session.scalars(
            select(MenuModifierOption)
            .where(MenuModifierOption.group_id == group.id)
            .order_by(MenuModifierOption.id)
        ).all()
        result.append({"group": group, "options": options})
    return result


def _options_by_product(product_ids):
    """One query so the grid can badge items that have choices."""
    from app.order_models import MenuModifierGroup

    if not product_ids:
        return set()
    rows = db.session.scalars(
        select(MenuModifierGroup.product_id).where(MenuModifierGroup.product_id.in_(product_ids))
    ).all()
    return set(rows)


@bp.get("")
@branch_required
def index():
    ctx = context()
    search = (request.args.get("q") or "").strip()
    category_id = request.args.get("category", type=int)

    scan = (request.args.get("scan") or "").strip()
    if scan:
        barcode = db.session.scalar(
            select(ProductBarcode).where(
                ProductBarcode.business_id == ctx.business_id,
                ProductBarcode.barcode == scan,
            )
        )
        if barcode is None:
            flash(f"No product matches barcode {scan}.", "warn")
        else:
            basket.add_line(barcode.product_id, 1)
            flash("Added from barcode.", "info")
        return redirect(url_for("pos.index"))

    query = (
        select(BranchProduct, Product)
        .join(Product, Product.id == BranchProduct.product_id)
        .where(
            BranchProduct.business_id == ctx.business_id,
            BranchProduct.branch_id == ctx.branch_id,
            BranchProduct.is_available.is_(True),
            Product.is_active.is_(True),
        )
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(Product.name.ilike(pattern) | Product.sku.ilike(pattern))
    if category_id:
        query = query.where(Product.category_id == category_id)
    rows = db.session.execute(query.order_by(Product.name).limit(200)).all()
    products = [
        {"product": product, "branch_product": branch_product}
        for branch_product, product in rows
    ]
    choices = _options_by_product([item["product"].id for item in products])

    cart = basket.get_cart()
    try:
        priced = quote(
            business_id=ctx.business_id,
            branch_id=ctx.branch_id,
            lines=cart["lines"],
        )
        cart_error = None
    except (PaymentError, TenantAccessError) as error:
        basket.clear()
        cart = basket.get_cart()
        priced = quote(business_id=ctx.business_id, branch_id=ctx.branch_id, lines=[])
        cart_error = str(error)

    return render_template(
        "pos/index.html",
        products=products,
        choices=choices,
        categories=db.session.scalars(
            select(Category).where(Category.business_id == ctx.business_id).order_by(Category.name)
        ).all(),
        cart=cart,
        quote=priced,
        search=search,
        category_id=category_id,
        tables=db.session.scalars(
            select(DiningTable).where(DiningTable.branch_id == ctx.branch_id).order_by(DiningTable.table_number)
        ).all(),
        payment_methods=db.session.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.business_id == ctx.business_id, PaymentMethod.enabled.is_(True))
            .order_by(PaymentMethod.label)
        ).all(),
        cart_error=cart_error,
        may_discount=can("order.discount"),
    )


@bp.post("/add")
@branch_required
def add():
    ctx = context()
    product_id = request.form.get("product_id", type=int)
    if not product_id:
        abort(400)
    branch_product = db.session.scalar(
        select(BranchProduct).where(
            BranchProduct.branch_id == ctx.branch_id,
            BranchProduct.product_id == product_id,
            BranchProduct.is_available.is_(True),
        )
    )
    if branch_product is None:
        abort(404)
    options = request.form.getlist("option")
    basket.add_line(product_id, request.form.get("qty", type=int) or 1, options)
    if _wants_json():
        return _cart_payload()
    return _back_to_till()


@bp.post("/qty")
@branch_required
def set_quantity():
    key = request.form.get("key") or ""
    basket.set_qty(key, request.form.get("qty", type=int) or 0)
    if _wants_json():
        return _cart_payload()
    return _back_to_till()


@bp.post("/remove")
@branch_required
def remove():
    basket.remove_line(request.form.get("key") or "")
    if _wants_json():
        return _cart_payload()
    return _back_to_till()


@bp.post("/clear")
@branch_required
def clear():
    basket.clear()
    if _wants_json():
        return _cart_payload()
    return _back_to_till()


@bp.get("/item/<int:product_id>")
@branch_required
def configure(product_id):
    ctx = context()
    row = db.session.execute(
        select(BranchProduct, Product)
        .join(Product, Product.id == BranchProduct.product_id)
        .where(
            BranchProduct.branch_id == ctx.branch_id,
            BranchProduct.business_id == ctx.business_id,
            BranchProduct.product_id == product_id,
        )
    ).first()
    if row is None:
        abort(404)
    branch_product, product = row
    return render_template(
        "pos/configure.html",
        product=product,
        branch_product=branch_product,
        groups=_product_options(product.id),
    )


@bp.post("/quote")
@branch_required
def requote():
    """Re-price the basket for a discount change, without touching the order."""
    try:
        return _cart_payload(strict_discount=True)
    except PaymentError as error:
        return jsonify({"ok": False, "error": str(error)}), 400


@bp.post("/checkout")
@branch_required
def checkout():
    ctx = context()
    cart = basket.get_cart()
    if not cart["lines"]:
        flash("The basket is empty.", "warn")
        return _back_to_till()

    order_type = request.form.get("order_type") or "dine_in"
    table_id = request.form.get("table_id", type=int)

    try:
        discount = Decimal("0")
        discount_kind = request.form.get("discount_kind") or "percent"
        if request.form.get("discount_value"):
            if not can("order.discount"):
                raise PaymentError("This account cannot apply a discount.")
            discount = _money_value(request.form.get("discount_value"))
            if discount > 0 and discount_kind == "percent" and discount >= 100:
                raise PaymentError("A percentage discount must be below 100.")
            if discount <= 0:
                discount = Decimal("0")
                discount_kind = None

        # Blank means "bill the full amount due". The service resolves that against
        # the discounted total, so the till never asks for a figure twice.
        amount_paid = None
        if (request.form.get("amount_paid") or "").strip():
            amount_paid = _money_value(request.form.get("amount_paid"))
        payment_method_id = request.form.get("payment_method_id", type=int)
        if (amount_paid or 0) > 0 and not payment_method_id:
            raise PaymentError("Choose a payment method.")

        # Tie the sale to the cashier's open drawer, so closing that shift can
        # reconcile exactly the cash this till took.
        open_shift = db.session.scalar(
            select(CashierShift)
            .where(
                CashierShift.user_id == ctx.user.id,
                CashierShift.branch_id == ctx.branch_id,
                CashierShift.status == "open",
            )
            .order_by(CashierShift.id.desc())
        )

        order = create_order(
            business_id=ctx.business_id,
            branch=ctx.branch,
            order_type=order_type if order_type in ORDER_TYPES else "dine_in",
            lines=cart["lines"],
            table_id=table_id,
            discount_kind=discount_kind if discount > 0 else None,
            discount_value=discount,
            payment_method_id=payment_method_id,
            amount_paid=amount_paid,
            note=request.form.get("note") or "",
            cashier_shift_id=open_shift.id if open_shift else None,
            actor_user_id=ctx.user.id,
        )
    except (PaymentError, StockPolicyError, TenantAccessError) as error:
        db.session.rollback()
        flash(str(error), "error")
        return _back_to_till()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Checkout failed")
        flash("The order could not be saved. Nothing was charged.", "error")
        return _back_to_till()

    basket.clear()
    if order.status == "paid":
        flash(f"Order {order.order_number} paid.", "success")
        return redirect(url_for("orders.receipt", order_id=order.id))
    flash(f"Order {order.order_number} saved as {order.status.replace('_', ' ')}.", "info")
    return redirect(url_for("orders.show", order_id=order.id))
