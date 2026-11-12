"""Stock ledger. Branch quantity changes only through a stock movement."""
from sqlalchemy import select

from app import db
from app.inventory_models import BranchStock, InventoryItem, StockMovement
from app.models import Branch
from app.money import quantity
from app.platform_models import BusinessSetting
from app.timeutil import utcnow
from app.services.errors import StockPolicyError, TenantAccessError


def apply_stock_delta(*, business_id, branch_id, item_id, movement_type, delta_qty, reference_code, created_at=None):
    """Apply one stock change. Repeating the same reference returns the original movement."""
    delta = quantity(delta_qty)
    if delta == 0:
        raise StockPolicyError("Stock movement quantity cannot be zero")
    branch = db.session.get(Branch, branch_id)
    item = db.session.get(InventoryItem, item_id)
    if branch is None or item is None or branch.business_id != business_id or item.business_id != business_id:
        raise TenantAccessError("Stock movement crosses a business boundary")
    existing = db.session.scalar(
        select(StockMovement).where(
            StockMovement.branch_id == branch_id,
            StockMovement.item_id == item_id,
            StockMovement.movement_type == movement_type,
            StockMovement.reference_code == reference_code,
        )
    )
    if existing is not None:
        return existing
    stock = db.session.scalar(
        select(BranchStock).where(BranchStock.branch_id == branch_id, BranchStock.item_id == item_id).with_for_update()
    )
    if stock is None:
        stock = BranchStock(business_id=business_id, branch_id=branch_id, item_id=item_id, quantity=quantity(0))
        db.session.add(stock)
        db.session.flush()
    settings = db.session.scalar(select(BusinessSetting).where(BusinessSetting.business_id == business_id))
    allow_negative = bool(settings.allow_negative_stock) if settings is not None else False
    new_qty = quantity(stock.quantity + delta)
    if new_qty < 0 and not allow_negative:
        raise StockPolicyError(
            f"Negative stock is not allowed for item {item.sku} at branch {branch.code}"
        )
    stock.quantity = new_qty
    movement = StockMovement(
        business_id=business_id,
        branch_id=branch_id,
        item_id=item_id,
        movement_type=movement_type,
        delta_qty=delta,
        reference_code=reference_code,
        created_at=created_at or utcnow(),
    )
    db.session.add(movement)
    db.session.flush()
    return movement
