"""Recipe consumption. A paid order deducts ingredients once, never the finished plate itself."""
from collections import defaultdict

from sqlalchemy import select

from app import db
from app.inventory_models import InventoryItem, StockMovement
from app.money import quantity
from app.order_models import OrderItem, RestaurantOrder
from app.recipe_models import Recipe, RecipeLine
from app.services.errors import LifecycleError, StockPolicyError, TenantAccessError
from app.services.inventory import apply_stock_delta

CONSUMPTION_PREFIX = "HCONS-"


def consumption_reference(order_number):
    return CONSUMPTION_PREFIX + order_number


def recipe_requirements(product_ids):
    """Map product id -> list of (inventory item id, quantity per serving, movement type)."""
    if not product_ids:
        return {}
    rows = db.session.execute(
        select(Recipe.product_id, RecipeLine.inventory_item_id, RecipeLine.quantity, Recipe.yield_qty)
        .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
        .where(Recipe.product_id.in_(product_ids), Recipe.is_active.is_(True))
    ).all()
    requirements = defaultdict(list)
    for product_id, item_id, line_qty, yield_qty in rows:
        per_serving = quantity(line_qty / yield_qty)
        requirements[product_id].append((item_id, per_serving, "recipe_consumption"))
    retail_rows = db.session.execute(
        select(InventoryItem.product_id, InventoryItem.id).where(
            InventoryItem.product_id.in_(product_ids)
        )
    ).all()
    for product_id, item_id in retail_rows:
        if product_id not in requirements:
            requirements[product_id].append((item_id, quantity(1), "retail_sale"))
    return requirements


def post_recipe_consumption(order_id, *, actor_business_id, created_at=None):
    """Deduct recipe ingredients or retail units for a paid order. Safe to call again."""
    order = db.session.get(RestaurantOrder, order_id)
    if order is None or order.business_id != actor_business_id:
        raise TenantAccessError("Order is not visible to this business")
    if order.status != "paid":
        raise LifecycleError("Inventory is consumed only when an order is paid")
    items = db.session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    requirements = recipe_requirements([item.product_id for item in items])
    needed = defaultdict(lambda: {"qty": quantity(0), "movement_type": None})
    for item in items:
        for item_id, per_serving, movement_type in requirements.get(item.product_id, []):
            bucket = needed[item_id]
            bucket["qty"] = quantity(bucket["qty"] + per_serving * item.quantity)
            bucket["movement_type"] = movement_type
    reference = consumption_reference(order.order_number)
    movements = []
    for item_id, bucket in needed.items():
        movements.append(
            apply_stock_delta(
                business_id=order.business_id,
                branch_id=order.branch_id,
                item_id=item_id,
                movement_type=bucket["movement_type"],
                delta_qty=-bucket["qty"],
                reference_code=reference,
                created_at=created_at,
            )
        )
    return movements


def assert_consumption_exists(order, item_id):
    reference = consumption_reference(order.order_number)
    found = db.session.scalar(
        select(StockMovement.id).where(
            StockMovement.branch_id == order.branch_id,
            StockMovement.item_id == item_id,
            StockMovement.reference_code == reference,
            StockMovement.movement_type.in_(("recipe_consumption", "retail_sale")),
        )
    )
    if found is None:
        raise StockPolicyError("Cannot restock an item that this order never consumed")
