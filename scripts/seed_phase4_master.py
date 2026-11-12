"""Idempotent curated master data for the Lahore demo tenants.

Re-running this script does not duplicate businesses, products, recipes or staff.
It does not overwrite a product price that is already stored.
"""
import hashlib
import os
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.intelligence_models import DatasetManifest
from app.inventory_models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryItem,
    StockBatch,
    SupplierPurchaseItem,
    SupplierPurchaseOrder,
)
from app.models import (
    Branch,
    BranchProduct,
    Business,
    BusinessUser,
    Category,
    PaymentMethod,
    Printer,
    Product,
    Supplier,
    User,
)
from app.money import money, quantity
from app.operations_models import PrintJob, ProductBarcode, ScannerSession
from app.order_models import MenuModifierGroup, MenuModifierOption
from app.platform_models import (
    BranchOperatingHour,
    BusinessSetting,
    BusinessSubscription,
    Permission,
    Role,
    RolePermission,
    SubscriptionPlan,
    TaxRule,
)
from app.recipe_models import KitchenStation, ProductStationRoute, Recipe, RecipeLine
from app.seeddata.catalog import EXTRA_SUPPLIERS, INGREDIENTS, NEW_PRODUCTS, RECIPES, meta
from app.seeddata.naming import PRIMARY_SUPPLIER, extra_suppliers, receipt_footer_for
from app.seeddata.demand import HISTORY_START, HOURS
from app.seeddata.staff import OWNER_CODES, PLATFORM_ADMIN, STAFF
from app.services.audit import write_audit
from app.services.inventory import apply_stock_delta
from app.timeutil import pakistan_local, parse_hhmm
from scripts.common import get_or_create, require_pos_database

PERMISSIONS = [
    ("platform.manage", "Manage the platform", "Maintain plans and platform-level records."),
    ("business.settings", "Edit business settings", "Change receipt text, tax and margin rules."),
    ("branch.manage", "Manage a branch", "Maintain branch hours and local setup."),
    ("menu.manage", "Manage the menu", "Create categories, products, prices and recipes."),
    ("order.create", "Create orders", "Ring dine-in, takeaway, pickup and delivery tickets."),
    ("order.discount", "Apply a discount", "Request a fixed or percentage discount."),
    ("order.refund", "Post a return", "Refund or exchange a paid ticket."),
    ("order.void", "Void an open ticket", "Cancel a ticket that has not been posted."),
    ("payment.capture", "Capture payment", "Record cash, card or transfer against a ticket."),
    ("kitchen.update", "Update kitchen status", "Move ticket items through preparation."),
    ("inventory.adjust", "Adjust stock", "Post a counted stock correction."),
    ("inventory.purchase", "Purchase stock", "Create and receive supplier orders."),
    ("inventory.transfer", "Transfer stock", "Move stock between branches of the same business."),
    ("report.view", "View reports", "Read branch sales and stock reports."),
    ("ai.view", "View sales intelligence", "Read stored snapshots and rule-based suggestions."),
    ("staff.manage", "Manage staff", "Assign roles inside the business."),
    ("shift.manage", "Manage a shift", "Open, close and reconcile a cashier shift."),
    ("printer.manage", "Manage printers", "Record print jobs and printer issues."),
]

ROLE_GRANTS = {
    "platform_admin": [code for code, _label, _text in PERMISSIONS],
    "owner": [code for code, _label, _text in PERMISSIONS if code != "platform.manage"],
    "manager": [
        "branch.manage", "menu.manage", "order.create", "order.discount", "order.refund",
        "order.void", "payment.capture", "kitchen.update", "inventory.adjust",
        "inventory.purchase", "inventory.transfer", "report.view", "ai.view",
        "staff.manage", "shift.manage", "printer.manage",
    ],
    "cashier": ["order.create", "order.discount", "payment.capture", "shift.manage", "printer.manage", "report.view"],
    "kitchen": ["kitchen.update"],
    "inventory": ["inventory.adjust", "inventory.purchase", "inventory.transfer", "report.view"],
}


def barcode_for(slug, sku):
    number = int(hashlib.sha256(f"{slug}|{sku}".encode()).hexdigest()[:12], 16) % 10**10
    return "990" + str(number).zfill(10)


def random_password_hash():
    return generate_password_hash(os.urandom(24).hex())


def seed_access():
    roles = {}
    for code, label, scope in (
        ("platform_admin", "Platform administrator", "platform"),
        ("owner", "Business owner", "business"),
        ("manager", "Branch manager", "branch"),
        ("cashier", "Cashier", "branch"),
        ("kitchen", "Kitchen staff", "branch"),
        ("inventory", "Inventory staff", "business"),
    ):
        roles[code] = get_or_create(Role, {"code": code}, label=label, scope=scope)
    permissions = {}
    for code, label, description in PERMISSIONS:
        permissions[code] = get_or_create(Permission, {"code": code}, label=label, description=description)
    for role_code, grants in ROLE_GRANTS.items():
        for permission_code in grants:
            get_or_create(
                RolePermission,
                {"role_id": roles[role_code].id, "permission_id": permissions[permission_code].id},
            )
    admin = get_or_create(
        User,
        {"email": PLATFORM_ADMIN["email"]},
        display_name=PLATFORM_ADMIN["display_name"],
        password_hash=random_password_hash(),
        is_platform_admin=True,
        is_synthetic=True,
        employee_code=PLATFORM_ADMIN["employee_code"],
    )
    admin.is_platform_admin = True
    admin.is_synthetic = True
    admin.employee_code = admin.employee_code or PLATFORM_ADMIN["employee_code"]


def seed_plans_and_settings(business):
    single = get_or_create(
        SubscriptionPlan,
        {"code": "single_branch"},
        name="Single branch",
        monthly_fee_pkr=money(4500),
        max_branches=1,
        description="Coursework demo fee for one branch. Not a market quotation.",
    )
    multi = get_or_create(
        SubscriptionPlan,
        {"code": "multi_branch"},
        name="Multi branch",
        monthly_fee_pkr=money(12000),
        max_branches=8,
        description="Coursework demo fee for several branches of one business. Not a market quotation.",
    )
    del single
    get_or_create(
        BusinessSubscription,
        {"business_id": business.id},
        plan_id=multi.id,
        status="active",
        started_on=HISTORY_START,
        notes="Demo subscription. The fee is illustrative.",
    )
    margin = Decimal("15.00") if business.business_type == "restaurant" else Decimal("8.00")
    get_or_create(
        BusinessSetting,
        {"business_id": business.id},
        currency_code="PKR",
        timezone_name="Asia/Karachi",
        trading_since=HISTORY_START,
        receipt_header=f"{business.name}, Lahore",
        receipt_footer=receipt_footer_for(business.business_type),
        allow_negative_stock=False,
        min_gross_margin_pct=margin,
    )
    if business.business_type == "restaurant":
        get_or_create(
            TaxRule,
            {"business_id": business.id, "code": "DEMO_FOOD_5"},
            label="Illustrative 5 percent food rate",
            rate_percent=Decimal("5.000"),
            applies_to="menu_item",
            is_active=True,
            is_demo_rate=True,
            notes="Coursework rate only. This is not an FBR or PRA quotation.",
        )
    else:
        get_or_create(
            TaxRule,
            {"business_id": business.id, "code": "DEMO_SHELF_0"},
            label="Shelf price, no tax added",
            rate_percent=Decimal("0.000"),
            applies_to="retail_item",
            is_active=True,
            is_demo_rate=True,
            notes="Demo grocery tickets use the shelf price as the amount payable. Not tax advice.",
        )


def seed_hours(branch, slug):
    opens, closes = HOURS[slug]
    for weekday in range(7):
        get_or_create(
            BranchOperatingHour,
            {"branch_id": branch.id, "weekday": weekday},
            opens_at=parse_hhmm(opens),
            closes_at=parse_hhmm(closes),
            is_closed=False,
        )


def seed_staff(business, branches):
    by_code = {branch.code: branch for branch in branches}
    owner = db.session.scalar(
        select(User).join(BusinessUser, BusinessUser.user_id == User.id).where(
            BusinessUser.business_id == business.id,
            BusinessUser.role == "owner",
        )
    )
    if owner is not None:
        owner.is_synthetic = True
        owner.employee_code = owner.employee_code or OWNER_CODES[business.slug]
    for branch_code, employee_code, display_name, email, role in STAFF[business.slug]:
        user = get_or_create(
            User,
            {"email": email},
            display_name=display_name,
            password_hash=random_password_hash(),
            is_synthetic=True,
            employee_code=employee_code,
        )
        user.is_synthetic = True
        user.employee_code = user.employee_code or employee_code
        branch = by_code.get(branch_code)
        get_or_create(
            BusinessUser,
            {
                "business_id": business.id,
                "user_id": user.id,
                "branch_id": None if branch is None else branch.id,
                "role": role,
            },
        )


def seed_suppliers(business):
    primary = db.session.scalar(
        select(Supplier).where(Supplier.business_id == business.id, Supplier.name == PRIMARY_SUPPLIER)
    )
    if primary is None:
        primary = get_or_create(Supplier, {"business_id": business.id, "name": PRIMARY_SUPPLIER}, city="Lahore")
    primary.lead_time_days = 2
    primary.is_synthetic = True
    for name, lead in extra_suppliers(business.slug):
        supplier = get_or_create(Supplier, {"business_id": business.id, "name": name}, city="Lahore")
        supplier.lead_time_days = lead
        supplier.is_synthetic = True
    return primary


def seed_products(business, branches):
    slug = business.slug
    kind = "menu_item" if business.business_type == "restaurant" else "retail_item"
    for product in NEW_PRODUCTS[slug]:
        category = get_or_create(Category, {"business_id": business.id, "name": product.category})
        row = get_or_create(
            Product,
            {"business_id": business.id, "sku": product.sku},
            category_id=category.id,
            name=product.name,
            kind=kind,
            base_cost=money(product.cost),
            is_active=True,
        )
        for index, branch in enumerate(branches):
            get_or_create(
                BranchProduct,
                {"branch_id": branch.id, "product_id": row.id},
                business_id=business.id,
                sale_price=money(product.price + index * 20),
                is_available=True,
            )


def seed_retail_inventory(business):
    products = db.session.scalars(select(Product).where(Product.business_id == business.id).order_by(Product.id)).all()
    for product in products:
        item = get_or_create(
            InventoryItem,
            {"business_id": business.id, "sku": f"INV-{product.sku}"},
            name=product.name,
            unit="pcs",
            reorder_level=quantity(8),
            standard_cost=money(product.base_cost),
            product_id=product.id,
        )
        item.product_id = product.id
        item.standard_cost = money(product.base_cost)


def seed_ingredients(business, branches, supplier):
    by_sku = {}
    for ingredient in INGREDIENTS:
        item = get_or_create(
            InventoryItem,
            {"business_id": business.id, "sku": ingredient.sku},
            name=ingredient.name,
            unit=ingredient.unit,
            reorder_level=quantity(ingredient.reorder),
            standard_cost=money(ingredient.cost),
        )
        item.standard_cost = money(ingredient.cost)
        by_sku[ingredient.sku] = item
    po_number = f"SYN-OPEN-{business.id:03d}"
    if db.session.scalar(select(SupplierPurchaseOrder).where(
        SupplierPurchaseOrder.business_id == business.id,
        SupplierPurchaseOrder.po_number == po_number,
    )):
        return by_sku
    # One opening receipt per branch so unused ingredients are still on a ledger.
    for branch in branches:
        po = SupplierPurchaseOrder(
            business_id=business.id,
            branch_id=branch.id,
            supplier_id=supplier.id,
            po_number=po_number if branch.id == branches[0].id else f"{po_number}-{branch.code}",
            status="received",
            created_at=pakistan_local(2025, 5, 1, 7, 0),
        )
        db.session.add(po)
        db.session.flush()
        receipt = GoodsReceipt(
            purchase_order_id=po.id,
            business_id=business.id,
            branch_id=branch.id,
            receipt_number=f"SYN-OPEN-GRN-{business.id:03d}-{branch.code}",
            received_at=pakistan_local(2025, 5, 1, 7, 15),
        )
        db.session.add(receipt)
        db.session.flush()
        for ingredient in INGREDIENTS:
            item = by_sku[ingredient.sku]
            qty = quantity(ingredient.reorder)
            if qty <= 0:
                qty = quantity("1")
            purchase = SupplierPurchaseItem(
                purchase_order_id=po.id,
                item_id=item.id,
                qty_ordered=qty,
                unit_cost=money(ingredient.cost),
            )
            db.session.add(purchase)
            db.session.flush()
            db.session.add(GoodsReceiptItem(goods_receipt_id=receipt.id, purchase_item_id=purchase.id, quantity=qty))
            expiry = None
            if ingredient.shelf_days:
                expiry = datetime(2025, 5, 1).date() + timedelta(days=ingredient.shelf_days)
            db.session.add(StockBatch(
                business_id=business.id,
                branch_id=branch.id,
                item_id=item.id,
                batch_number=f"OPEN-{branch.code}-{item.id}",
                received_qty=qty,
                expiry_date=expiry,
            ))
            apply_stock_delta(
                business_id=business.id,
                branch_id=branch.id,
                item_id=item.id,
                movement_type="purchase_receipt",
                delta_qty=qty,
                reference_code=receipt.receipt_number,
                created_at=receipt.received_at,
            )
    return by_sku


def seed_recipes(business, items_by_sku):
    for product_sku, lines in RECIPES.get(business.slug, {}).items():
        product = db.session.scalar(
            select(Product).where(Product.business_id == business.id, Product.sku == product_sku)
        )
        if product is None:
            raise RuntimeError("Recipe product was not found: " + product_sku)
        recipe = get_or_create(
            Recipe,
            {"product_id": product.id},
            business_id=business.id,
            name=product.name,
            yield_qty=quantity(1),
            notes="Representative coursework recipe. One yield is one menu serving.",
            is_active=True,
        )
        for ingredient_sku, qty in lines:
            item = items_by_sku[ingredient_sku]
            get_or_create(
                RecipeLine,
                {"recipe_id": recipe.id, "inventory_item_id": item.id},
                quantity=quantity(qty),
                unit=item.unit,
            )


def seed_stations(business, branches):
    from app.seeddata.demand import STATIONS

    for branch in branches:
        station_by_code = {}
        kitchen_printer = db.session.scalar(
            select(Printer).where(Printer.branch_id == branch.id, Printer.purpose == "kitchen")
        )
        for code, name, _tags in STATIONS[business.slug]:
            station = get_or_create(
                KitchenStation,
                {"branch_id": branch.id, "code": code},
                business_id=business.id,
                name=name,
                printer_id=None if code == "COLD" else (kitchen_printer.id if kitchen_printer else None),
                is_active=True,
            )
            station_by_code[code] = station
        tag_to_code = {}
        for code, _name, tags in STATIONS[business.slug]:
            for tag in tags:
                tag_to_code[tag] = code
        products = db.session.scalars(select(Product).where(Product.business_id == business.id)).all()
        for product in products:
            _popularity, tag = meta(business.slug, product.sku)
            code = tag_to_code.get(tag, STATIONS[business.slug][0][0])
            station = station_by_code[code]
            get_or_create(
                ProductStationRoute,
                {"branch_id": branch.id, "product_id": product.id},
                business_id=business.id,
                station_id=station.id,
            )


def seed_modifiers(business):
    products = db.session.scalars(
        select(Product).join(Category, Category.id == Product.category_id).where(Product.business_id == business.id)
    ).all()
    for product in products:
        _popularity, tag = meta(business.slug, product.sku)
        if tag in ("karahi", "handi"):
            group = get_or_create(
                MenuModifierGroup,
                {"product_id": product.id, "name": "Spice and sides"},
                business_id=business.id,
                is_required=False,
            )
            for name, price in (("Mild", 0), ("Medium", 0), ("Extra spicy", 0), ("Extra raita", 80)):
                get_or_create(MenuModifierOption, {"group_id": group.id, "name": name}, extra_price=money(price))
        if tag == "burger":
            group = get_or_create(
                MenuModifierGroup,
                {"product_id": product.id, "name": "Burger add-ons"},
                business_id=business.id,
                is_required=False,
            )
            for name, price in (("Extra cheese", 70), ("Extra sauce", 40)):
                get_or_create(MenuModifierOption, {"group_id": group.id, "name": name}, extra_price=money(price))


def seed_barcodes_and_devices(business, branches):
    products = db.session.scalars(select(Product).where(Product.business_id == business.id).order_by(Product.sku)).all()
    for product in products:
        get_or_create(
            ProductBarcode,
            {"business_id": business.id, "barcode": barcode_for(business.slug, product.sku)},
            product_id=product.id,
            symbology="CODE128",
            is_primary=True,
        )
    started = pakistan_local(2025, 5, 2, 10, 0)
    ended = pakistan_local(2025, 5, 2, 18, 0)
    for branch in branches:
        cashier = db.session.scalar(
            select(User).join(BusinessUser, BusinessUser.user_id == User.id).where(
                BusinessUser.business_id == business.id,
                BusinessUser.branch_id == branch.id,
                BusinessUser.role == "cashier",
            )
        )
        if cashier is None:
            continue
        for mode, label in (("camera", "Counter camera"), ("keyboard_wedge", "USB wedge scanner")):
            get_or_create(
                ScannerSession,
                {"session_code": f"SCAN-{branch.code}-{mode.upper()}"},
                business_id=business.id,
                branch_id=branch.id,
                user_id=cashier.id,
                device_label=label,
                mode=mode,
                status="closed",
                started_at=started,
                ended_at=ended,
            )
        label_printer = db.session.scalar(
            select(Printer).where(Printer.branch_id == branch.id, Printer.purpose == "label")
        )
        for product in products[:2]:
            get_or_create(
                PrintJob,
                {"idempotency_key": f"label:{branch.code}:{product.sku}"},
                business_id=business.id,
                branch_id=branch.id,
                printer_id=label_printer.id if label_printer else None,
                job_type="barcode_label",
                status="printed",
                attempt_count=1,
                created_at=started,
            )


def seed_printers(branch):
    receipt = db.session.scalar(select(Printer).where(Printer.branch_id == branch.id, Printer.purpose == "receipt", Printer.label == "Receipt printer"))
    if receipt is not None and receipt.paper_width_mm is None:
        receipt.paper_width_mm = 80
    kitchen = db.session.scalar(select(Printer).where(Printer.branch_id == branch.id, Printer.purpose == "kitchen"))
    if kitchen is not None and kitchen.paper_width_mm is None:
        kitchen.paper_width_mm = 80
    get_or_create(
        Printer,
        {"branch_id": branch.id, "label": "Receipt printer 58mm"},
        purpose="receipt",
        connection_type="browser",
        paper_width_mm=58,
    )
    get_or_create(
        Printer,
        {"branch_id": branch.id, "label": "Label printer"},
        purpose="label",
        connection_type="browser",
        paper_width_mm=80,
    )


def seed_manifests():
    rows = [
        (
            "PHASE1_MASTER",
            "MANUALLY_CURATED",
            "Phase 1 fictional Lahore tenants",
            "Three fictional businesses, six branches and the original short menus.",
            "Written by scripts/seed_phase1.py. Names are fictional. Prices are sample PKR.",
            "complete",
        ),
        (
            "PHASE2_DEMO_ORDERS",
            "APPLICATION_GENERATED",
            "Twenty-four demonstration tickets",
            "Small paid examples created from each restaurant branch menu. Tax on these rows is zero by the original demo rule.",
            "Written by scripts/seed_phase2.py. Not a sales export.",
            "complete",
        ),
        (
            "PHASE3_STOCK_DEMO",
            "APPLICATION_GENERATED",
            "Phase 3 purchasing sample",
            "One received purchase and one transfer per demo business, posted through the stock ledger.",
            "Written by scripts/seed_phase3.py.",
            "complete",
        ),
        (
            "PHASE4_CATALOG",
            "MANUALLY_CURATED",
            "Expanded Lahore demo catalog",
            "Menu items, grocery items, ingredients, representative recipes, roles, tax rules and branch hours.",
            "Curated in app/seeddata and loaded by scripts/seed_phase4_master.py. No public menu was copied.",
            "complete",
        ),
        (
            "SYNTHETIC_HISTORY_V1",
            "SYNTHETIC_HISTORICAL",
            "Simulated trading from May 2025 through October 2026",
            "Deterministic tickets, payments, shifts and stock movements. Patterns such as weekend dinner and a Grill House iftar window are planted.",
            "Generated by scripts/seed_phase4_history.py. business.created_at remains the day the demo row was inserted. trading_since is the fictional operating start.",
            "recorded",
        ),
    ]
    for code, category, title, description, source_note, status in rows:
        manifest = get_or_create(
            DatasetManifest,
            {"code": code},
            category=category,
            title=title,
            description=description,
            source_note=source_note,
            status=status,
        )
        if code != "SYNTHETIC_HISTORY_V1":
            manifest.status = status
            manifest.description = description


def run():
    app = create_app()
    with app.app_context():
        require_pos_database()
        try:
            seed_access()
            seed_manifests()
            businesses = db.session.scalars(select(Business).where(Business.is_demo.is_(True)).order_by(Business.id)).all()
            if len(businesses) != 3:
                raise RuntimeError("Expected the three existing demo businesses")
            for business in businesses:
                branches = db.session.scalars(
                    select(Branch).where(Branch.business_id == business.id).order_by(Branch.id)
                ).all()
                seed_plans_and_settings(business)
                supplier = seed_suppliers(business)
                seed_staff(business, branches)
                seed_products(business, branches)
                for branch in branches:
                    seed_hours(branch, business.slug)
                    seed_printers(branch)
                if business.business_type == "restaurant":
                    items = seed_ingredients(business, branches, supplier)
                    seed_recipes(business, items)
                    seed_stations(business, branches)
                    seed_modifiers(business)
                else:
                    seed_retail_inventory(business)
                seed_barcodes_and_devices(business, branches)
                write_audit(
                    action="seed_master",
                    entity_type="business",
                    entity_id=business.id,
                    business_id=business.id,
                    message="Phase 4 curated master data recorded for " + business.name,
                )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        print("SUCCESS: phase 4 master data is in retail_pos_db")
        print("products", db.session.scalar(select(db.func.count()).select_from(Product)))
        print("ingredients", db.session.scalar(select(db.func.count()).select_from(InventoryItem)))
        print("recipes", db.session.scalar(select(db.func.count()).select_from(Recipe)))


if __name__ == "__main__":
    run()
