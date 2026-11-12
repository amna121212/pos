"""Product catalogue and categories."""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import BranchProduct, Category, Product
from app.security import branch_required, can, context, permission_required
from app.services.audit import write_audit
from app.blueprints.helpers import page_args, total_pages

bp = Blueprint("catalog", __name__)

KINDS = ("menu_item", "retail_item")


def _amount(raw, field, default="0"):
    text = (raw or "").strip().replace(",", "")
    if not text:
        text = default
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{field} must be a number.")
    if value < 0:
        raise ValueError(f"{field} cannot be negative.")
    return value.quantize(Decimal("0.01"))


def _categories(business_id):
    return db.session.scalars(
        select(Category).where(Category.business_id == business_id).order_by(Category.name)
    ).all()


@bp.get("/products")
@branch_required
def products():
    ctx = context()
    search = (request.args.get("q") or "").strip()
    category_id = request.args.get("category", type=int)
    active = request.args.get("active") or "yes"
    page, size, offset = page_args()

    conditions = [Product.business_id == ctx.business_id]
    if search:
        pattern = f"%{search}%"
        conditions.append(Product.name.ilike(pattern) | Product.sku.ilike(pattern))
    if category_id:
        conditions.append(Product.category_id == category_id)
    if active == "yes":
        conditions.append(Product.is_active.is_(True))
    elif active == "no":
        conditions.append(Product.is_active.is_(False))

    total = int(db.session.scalar(select(func.count()).select_from(Product).where(*conditions)) or 0)
    rows = db.session.scalars(
        select(Product).where(*conditions).order_by(Product.name).limit(size).offset(offset)
    ).all()
    prices = {
        row.product_id: row
        for row in db.session.scalars(
            select(BranchProduct).where(
                BranchProduct.branch_id == ctx.branch_id,
                BranchProduct.product_id.in_([product.id for product in rows] or [0]),
            )
        ).all()
    }
    return render_template(
        "catalog/products.html",
        products=rows,
        prices=prices,
        categories=_categories(ctx.business_id),
        search=search,
        category_id=category_id,
        active=active,
        page=page,
        pages=total_pages(total, size),
        total=total,
        can_manage=can("menu.manage"),
    )


@bp.route("/products/new", methods=["GET", "POST"])
@permission_required("menu.manage")
@branch_required
def product_new():
    ctx = context()
    categories = _categories(ctx.business_id)
    if request.method == "POST":
        try:
            if not categories:
                raise ValueError("Create a category first.")
            name = (request.form.get("name") or "").strip()
            sku = (request.form.get("sku") or "").strip().upper()
            if not name or not sku:
                raise ValueError("Name and SKU are required.")
            category_id = request.form.get("category_id", type=int)
            if not any(category.id == category_id for category in categories):
                raise ValueError("Choose one of your own categories.")
            price = _amount(request.form.get("sale_price"), "Sale price")
            cost = _amount(request.form.get("base_cost"), "Base cost")
            product = Product(
                business_id=ctx.business_id,
                category_id=category_id,
                sku=sku,
                name=name,
                kind=request.form.get("kind") if request.form.get("kind") in KINDS else "menu_item",
                base_cost=cost,
                is_active=True,
            )
            db.session.add(product)
            db.session.flush()
            db.session.add(
                BranchProduct(
                    business_id=ctx.business_id,
                    branch_id=ctx.branch_id,
                    product_id=product.id,
                    sale_price=price,
                    is_available=True,
                )
            )
            write_audit(
                action="create_product",
                entity_type="product",
                entity_id=product.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Added {sku} {name}",
            )
            db.session.commit()
            flash(f"{name} added.", "success")
            return redirect(url_for("catalog.products"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That SKU is already used in this business.", "error")
    return render_template(
        "catalog/product_form.html", product=None, categories=categories, kinds=KINDS, price=None
    )


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@permission_required("menu.manage")
@branch_required
def product_edit(product_id):
    ctx = context()
    product = db.session.get(Product, product_id)
    if product is None or product.business_id != ctx.business_id:
        abort(404)
    categories = _categories(ctx.business_id)
    branch_price = db.session.scalar(
        select(BranchProduct).where(
            BranchProduct.branch_id == ctx.branch_id, BranchProduct.product_id == product.id
        )
    )
    if request.method == "POST":
        try:
            name = (request.form.get("name") or "").strip()
            if not name:
                raise ValueError("Name is required.")
            category_id = request.form.get("category_id", type=int)
            if not any(category.id == category_id for category in categories):
                raise ValueError("Choose one of your own categories.")
            product.name = name
            product.category_id = category_id
            product.kind = request.form.get("kind") if request.form.get("kind") in KINDS else product.kind
            product.base_cost = _amount(request.form.get("base_cost"), "Base cost")
            price = _amount(request.form.get("sale_price"), "Sale price")
            if branch_price is None:
                branch_price = BranchProduct(
                    business_id=ctx.business_id,
                    branch_id=ctx.branch_id,
                    product_id=product.id,
                    sale_price=price,
                    is_available=True,
                )
                db.session.add(branch_price)
            else:
                branch_price.sale_price = price
                branch_price.is_available = bool(request.form.get("is_available"))
            write_audit(
                action="update_product",
                entity_type="product",
                entity_id=product.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Updated {product.sku}",
            )
            db.session.commit()
            flash("Product saved.", "success")
            return redirect(url_for("catalog.products"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template(
        "catalog/product_form.html",
        product=product,
        categories=categories,
        kinds=KINDS,
        price=branch_price,
    )


@bp.post("/products/<int:product_id>/toggle")
@permission_required("menu.manage")
@branch_required
def product_toggle(product_id):
    ctx = context()
    product = db.session.get(Product, product_id)
    if product is None or product.business_id != ctx.business_id:
        abort(404)
    product.is_active = not product.is_active
    write_audit(
        action="toggle_product",
        entity_type="product",
        entity_id=product.id,
        business_id=ctx.business_id,
        branch_id=ctx.branch_id,
        actor_user_id=ctx.user.id,
        message=f"{product.sku} {'activated' if product.is_active else 'retired'}",
    )
    db.session.commit()
    flash(f"{product.name} {'activated' if product.is_active else 'retired'}.", "info")
    return redirect(url_for("catalog.products"))


@bp.route("/categories", methods=["GET", "POST"])
@branch_required
def categories():
    ctx = context()
    if request.method == "POST":
        if not can("menu.manage"):
            abort(403)
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Category name is required.", "error")
        else:
            try:
                db.session.add(Category(business_id=ctx.business_id, name=name[:100]))
                db.session.commit()
                flash("Category added.", "success")
            except IntegrityError:
                db.session.rollback()
                flash("That category already exists.", "error")
        return redirect(url_for("catalog.categories"))

    rows = db.session.execute(
        select(Category, func.count(Product.id))
        .outerjoin(Product, Product.category_id == Category.id)
        .where(Category.business_id == ctx.business_id)
        .group_by(Category.id, Category.name)
        .order_by(Category.name)
    ).all()
    return render_template("catalog/categories.html", rows=rows, can_manage=can("menu.manage"))


@bp.post("/categories/<int:category_id>/edit")
@permission_required("menu.manage")
@branch_required
def category_edit(category_id):
    ctx = context()
    category = db.session.get(Category, category_id)
    if category is None or category.business_id != ctx.business_id:
        abort(404)
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Category name is required.", "error")
        return redirect(url_for("catalog.categories"))
    category.name = name[:100]
    try:
        db.session.commit()
        flash("Category renamed.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Another category already uses that name.", "error")
    return redirect(url_for("catalog.categories"))
