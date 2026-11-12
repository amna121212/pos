"""CSV import used by students to load their own menu and stock files.

Existing rows are left unchanged. A row that matches a natural key is skipped
and reported. Dry-run validates and inserts inside a transaction that is rolled back.
"""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app import db
from app.inventory_models import InventoryItem, StockBatch
from app.models import Branch, Business, BusinessUser, Category, Product, BranchProduct, Supplier, User
from app.money import money, quantity
from app.platform_models import BusinessSetting
from app.recipe_models import Recipe, RecipeLine
from app.services.inventory import apply_stock_delta
from app.timeutil import utcnow

ALLOWED_EMAIL_DOMAIN = "@example.invalid"
ROLES = {"owner", "manager", "cashier", "kitchen", "inventory"}
KINDS = {"menu_item", "retail_item"}
BUSINESS_TYPES = {"restaurant", "retail", "cafe"}


class ImportResult(dict):
    """Plain summary a student can print or explain in a viva."""


def _rows(path):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV file has no header row")
        return reader.fieldnames, list(reader)


def _require_columns(fieldnames, required):
    missing = [name for name in required if name not in fieldnames]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))


def _decimal(value, label, row_number):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"Row {row_number}: {label} is not a number")


def _business(slug, row_number):
    business = db.session.scalar(select(Business).where(Business.slug == slug))
    if business is None:
        raise ValueError(f"Row {row_number}: unknown business slug {slug}")
    return business


def import_file(path, kind, *, dry_run=False):
    """Import one CSV. Returns a summary and rolls back when dry_run is true or validation fails."""
    handlers = {
        "businesses": (
            _import_businesses,
            ["slug", "name", "business_type", "city", "trading_since", "min_gross_margin_pct"],
        ),
        "branches": (_import_branches, ["business_slug", "code", "name", "area", "city"]),
        "categories": (_import_categories, ["business_slug", "category_name"]),
        "products": (_import_products, ["business_slug", "category_name", "sku", "name", "kind", "base_cost"]),
        "branch_prices": (_import_prices, ["business_slug", "branch_code", "sku", "sale_price", "is_available"]),
        "ingredients": (_import_ingredients, ["business_slug", "sku", "name", "unit", "reorder_level", "standard_cost"]),
        "recipes": (_import_recipes, ["business_slug", "product_sku", "ingredient_sku", "quantity", "unit"]),
        "suppliers": (_import_suppliers, ["business_slug", "name", "city", "lead_time_days"]),
        "staff": (_import_staff, ["business_slug", "branch_code", "employee_code", "display_name", "email", "role"]),
        "opening_inventory": (
            _import_opening,
            ["business_slug", "branch_code", "ingredient_sku", "quantity", "batch_number", "unit_cost"],
        ),
    }
    if kind not in handlers:
        raise ValueError("Unknown import kind: " + kind)
    handler, required = handlers[kind]
    fieldnames, rows = _rows(path)
    _require_columns(fieldnames, required)
    result = ImportResult(kind=kind, dry_run=dry_run, inserted=0, skipped_existing=0, errors=[], rows=len(rows))
    try:
        for number, row in enumerate(rows, start=2):
            if str(row.get("sku", "")).startswith("EXAMPLE_") or str(row.get("name", "")).startswith("EXAMPLE_"):
                result["errors"].append(f"Row {number}: remove EXAMPLE_ rows before importing")
                continue
            try:
                outcome = handler(row, number)
            except ValueError as exc:
                result["errors"].append(str(exc))
                continue
            result[outcome] += 1
        if result["errors"]:
            db.session.rollback()
            result["inserted"] = 0
            result["status"] = "rejected"
            return result
        if dry_run:
            db.session.rollback()
            result["status"] = "dry_run"
            return result
        db.session.commit()
        result["status"] = "committed"
        return result
    except Exception:
        db.session.rollback()
        raise


def _import_businesses(row, number):
    """Create a tenant and its PKR settings. An existing slug is left unchanged."""
    slug = row["slug"].strip().lower()
    name = row["name"].strip()
    kind = row["business_type"].strip().lower()
    if not slug or not name:
        raise ValueError(f"Row {number}: slug and name are required")
    if any(not (character.isalnum() or character == "-") for character in slug) or slug.startswith("-") or slug.endswith("-"):
        raise ValueError(f"Row {number}: slug must use lowercase letters, numbers and hyphens")
    if kind not in BUSINESS_TYPES:
        raise ValueError(f"Row {number}: business_type must be restaurant, retail or cafe")
    trading_since = _date(row["trading_since"], number)
    margin = money(_decimal(row["min_gross_margin_pct"], "min_gross_margin_pct", number))
    if margin < 0 or margin >= 100:
        raise ValueError(f"Row {number}: margin floor must be from 0 up to, but not including, 100")
    existing = db.session.scalar(select(Business).where(Business.slug == slug))
    if existing is not None:
        return "skipped_existing"
    taken = db.session.scalar(select(Business).where(Business.name == name))
    if taken is not None:
        raise ValueError(f"Row {number}: business name is already used by slug {taken.slug}")
    business = Business(name=name, slug=slug, business_type=kind, city=row["city"].strip() or "Lahore", is_demo=False)
    db.session.add(business)
    db.session.flush()
    db.session.add(BusinessSetting(
        business_id=business.id,
        currency_code="PKR",
        timezone_name="Asia/Karachi",
        trading_since=trading_since,
        receipt_header=name,
        receipt_footer="Student import. Prices are the amounts entered in the CSV.",
        allow_negative_stock=False,
        min_gross_margin_pct=margin,
    ))
    db.session.flush()
    return "inserted"


def _import_branches(row, number):
    """Add a branch to an existing business. An existing branch code is left unchanged."""
    business = _business(row["business_slug"].strip(), number)
    code = row["code"].strip().upper()
    name = row["name"].strip()
    area = row["area"].strip()
    if not code or not name or not area:
        raise ValueError(f"Row {number}: code, name and area are required")
    existing = db.session.scalar(select(Branch).where(Branch.business_id == business.id, Branch.code == code))
    if existing is not None:
        return "skipped_existing"
    db.session.add(Branch(
        business_id=business.id,
        code=code,
        name=name,
        area=area,
        city=row["city"].strip() or "Lahore",
        is_active=True,
    ))
    db.session.flush()
    return "inserted"


def _date(value, row_number):
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"Row {row_number}: trading_since must be YYYY-MM-DD")


def _import_categories(row, number):
    business = _business(row["business_slug"].strip(), number)
    name = row["category_name"].strip()
    if not name:
        raise ValueError(f"Row {number}: category name is empty")
    existing = db.session.scalar(select(Category).where(Category.business_id == business.id, Category.name == name))
    if existing is not None:
        return "skipped_existing"
    db.session.add(Category(business_id=business.id, name=name))
    db.session.flush()
    return "inserted"


def _import_products(row, number):
    business = _business(row["business_slug"].strip(), number)
    sku = row["sku"].strip()
    kind = row["kind"].strip()
    if kind not in KINDS:
        raise ValueError(f"Row {number}: kind must be menu_item or retail_item")
    category = db.session.scalar(select(Category).where(
        Category.business_id == business.id, Category.name == row["category_name"].strip()
    ))
    if category is None:
        raise ValueError(f"Row {number}: category does not exist for this business")
    existing = db.session.scalar(select(Product).where(Product.business_id == business.id, Product.sku == sku))
    if existing is not None:
        return "skipped_existing"
    cost = money(_decimal(row["base_cost"], "base_cost", number))
    if cost < 0:
        raise ValueError(f"Row {number}: base cost cannot be negative")
    db.session.add(Product(
        business_id=business.id,
        category_id=category.id,
        sku=sku,
        name=row["name"].strip(),
        kind=kind,
        base_cost=cost,
        is_active=True,
    ))
    db.session.flush()
    return "inserted"


def _import_prices(row, number):
    business = _business(row["business_slug"].strip(), number)
    branch = db.session.scalar(select(Branch).where(
        Branch.business_id == business.id, Branch.code == row["branch_code"].strip()
    ))
    product = db.session.scalar(select(Product).where(
        Product.business_id == business.id, Product.sku == row["sku"].strip()
    ))
    if branch is None or product is None:
        raise ValueError(f"Row {number}: branch or product was not found in this business")
    existing = db.session.scalar(select(BranchProduct).where(
        BranchProduct.branch_id == branch.id, BranchProduct.product_id == product.id
    ))
    if existing is not None:
        return "skipped_existing"
    price = money(_decimal(row["sale_price"], "sale_price", number))
    if price < 0:
        raise ValueError(f"Row {number}: sale price cannot be negative")
    available = row["is_available"].strip().lower() in {"1", "true", "yes", "y"}
    db.session.add(BranchProduct(
        business_id=business.id,
        branch_id=branch.id,
        product_id=product.id,
        sale_price=price,
        is_available=available,
    ))
    db.session.flush()
    return "inserted"


def _import_ingredients(row, number):
    business = _business(row["business_slug"].strip(), number)
    sku = row["sku"].strip()
    existing = db.session.scalar(select(InventoryItem).where(
        InventoryItem.business_id == business.id, InventoryItem.sku == sku
    ))
    if existing is not None:
        return "skipped_existing"
    reorder = quantity(_decimal(row["reorder_level"], "reorder_level", number))
    cost = money(_decimal(row["standard_cost"], "standard_cost", number))
    if reorder < 0 or cost < 0:
        raise ValueError(f"Row {number}: reorder and cost must be zero or positive")
    db.session.add(InventoryItem(
        business_id=business.id,
        sku=sku,
        name=row["name"].strip(),
        unit=row["unit"].strip() or "pcs",
        reorder_level=reorder,
        standard_cost=cost,
    ))
    db.session.flush()
    return "inserted"


def _import_recipes(row, number):
    business = _business(row["business_slug"].strip(), number)
    product = db.session.scalar(select(Product).where(
        Product.business_id == business.id, Product.sku == row["product_sku"].strip()
    ))
    item = db.session.scalar(select(InventoryItem).where(
        InventoryItem.business_id == business.id, InventoryItem.sku == row["ingredient_sku"].strip()
    ))
    if product is None or item is None:
        raise ValueError(f"Row {number}: product or ingredient was not found in this business")
    qty = quantity(_decimal(row["quantity"], "quantity", number))
    if qty <= 0:
        raise ValueError(f"Row {number}: recipe quantity must be positive")
    recipe = db.session.scalar(select(Recipe).where(Recipe.product_id == product.id))
    if recipe is None:
        recipe = Recipe(
            business_id=business.id,
            product_id=product.id,
            name=product.name,
            yield_qty=quantity(1),
            notes="Imported from a student CSV.",
            is_active=True,
        )
        db.session.add(recipe)
        db.session.flush()
    existing = db.session.scalar(select(RecipeLine).where(
        RecipeLine.recipe_id == recipe.id, RecipeLine.inventory_item_id == item.id
    ))
    if existing is not None:
        return "skipped_existing"
    db.session.add(RecipeLine(recipe_id=recipe.id, inventory_item_id=item.id, quantity=qty, unit=row["unit"].strip() or item.unit))
    db.session.flush()
    return "inserted"


def _import_suppliers(row, number):
    business = _business(row["business_slug"].strip(), number)
    name = row["name"].strip()
    existing = db.session.scalar(select(Supplier).where(Supplier.business_id == business.id, Supplier.name == name))
    if existing is not None:
        return "skipped_existing"
    lead = int(_decimal(row["lead_time_days"], "lead_time_days", number))
    if lead < 0:
        raise ValueError(f"Row {number}: lead time cannot be negative")
    db.session.add(Supplier(
        business_id=business.id, name=name, city=row["city"].strip() or "Lahore",
        lead_time_days=lead, is_synthetic=True,
    ))
    db.session.flush()
    return "inserted"


def _import_staff(row, number):
    business = _business(row["business_slug"].strip(), number)
    email = row["email"].strip().lower()
    if not email.endswith(ALLOWED_EMAIL_DOMAIN):
        raise ValueError(f"Row {number}: email must use the reserved {ALLOWED_EMAIL_DOMAIN} domain")
    role = row["role"].strip()
    if role not in ROLES:
        raise ValueError(f"Row {number}: role is not recognised")
    branch = None
    if row["branch_code"].strip():
        branch = db.session.scalar(select(Branch).where(
            Branch.business_id == business.id, Branch.code == row["branch_code"].strip()
        ))
        if branch is None:
            raise ValueError(f"Row {number}: branch code was not found")
    existing_user = db.session.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        return "skipped_existing"
    import os
    from werkzeug.security import generate_password_hash
    user = User(
        display_name=row["display_name"].strip(),
        email=email,
        password_hash=generate_password_hash(os.urandom(24).hex()),
        is_synthetic=True,
        employee_code=row["employee_code"].strip(),
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(BusinessUser(
        business_id=business.id,
        user_id=user.id,
        branch_id=None if branch is None else branch.id,
        role=role,
    ))
    db.session.flush()
    return "inserted"


def _import_opening(row, number):
    business = _business(row["business_slug"].strip(), number)
    branch = db.session.scalar(select(Branch).where(
        Branch.business_id == business.id, Branch.code == row["branch_code"].strip()
    ))
    item = db.session.scalar(select(InventoryItem).where(
        InventoryItem.business_id == business.id, InventoryItem.sku == row["ingredient_sku"].strip()
    ))
    if branch is None or item is None:
        raise ValueError(f"Row {number}: branch or ingredient was not found in this business")
    qty = quantity(_decimal(row["quantity"], "quantity", number))
    if qty <= 0:
        raise ValueError(f"Row {number}: opening quantity must be positive")
    batch_number = row["batch_number"].strip()
    reference = f"CSV-OPEN-{branch.code}-{batch_number}"
    existing = db.session.scalar(select(StockBatch).where(
        StockBatch.branch_id == branch.id,
        StockBatch.item_id == item.id,
        StockBatch.batch_number == batch_number,
    ))
    if existing is not None:
        return "skipped_existing"
    db.session.add(StockBatch(
        business_id=business.id,
        branch_id=branch.id,
        item_id=item.id,
        batch_number=batch_number,
        received_qty=qty,
        expiry_date=None,
    ))
    apply_stock_delta(
        business_id=business.id,
        branch_id=branch.id,
        item_id=item.id,
        movement_type="opening_balance",
        delta_qty=qty,
        reference_code=reference,
        created_at=utcnow(),
    )
    return "inserted"
