"""Refunds and same-price exchanges. Posted returns stay in the ledger and can be voided."""
from sqlalchemy import select

from app import db
from app.money import money, quantity
from app.operations_models import SalesReturn, SalesReturnLine
from app.order_models import OrderItem, RestaurantOrder
from app.services.audit import write_audit
from app.services.errors import LifecycleError, TenantAccessError
from app.services.inventory import apply_stock_delta
from app.services.recipes import assert_consumption_exists, recipe_requirements
from app.services.tenancy import require_payment_method, require_product
from app.timeutil import utcnow


def post_return_stock(sales_return, *, created_at=None):
    """Restock returned recipe ingredients and, for an exchange, issue the replacement once."""
    order = db.session.get(RestaurantOrder, sales_return.order_id)
    lines = db.session.scalars(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == sales_return.id)
    ).all()
    order_items = {
        item.id: item
        for item in db.session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    }
    product_ids = [order_items[line.order_item_id].product_id for line in lines]
    product_ids += [line.replacement_product_id for line in lines if line.replacement_product_id]
    requirements = recipe_requirements(product_ids)
    for line in lines:
        item = order_items[line.order_item_id]
        for item_id, per_serving, _movement_type in requirements.get(item.product_id, []):
            assert_consumption_exists(order, item_id)
            apply_stock_delta(
                business_id=sales_return.business_id,
                branch_id=sales_return.branch_id,
                item_id=item_id,
                movement_type="return_restock",
                delta_qty=quantity(per_serving * line.quantity),
                reference_code=f"HRET-{sales_return.return_number}",
                created_at=created_at,
            )
        if sales_return.return_type == "exchange" and line.replacement_product_id:
            for item_id, per_serving, movement_type in requirements.get(line.replacement_product_id, []):
                issue_type = "exchange_issue" if movement_type == "retail_sale" else "recipe_consumption"
                apply_stock_delta(
                    business_id=sales_return.business_id,
                    branch_id=sales_return.branch_id,
                    item_id=item_id,
                    movement_type=issue_type,
                    delta_qty=-quantity(per_serving * line.quantity),
                    reference_code=f"EXCH-{sales_return.return_number}",
                    created_at=created_at,
                )


def create_posted_return(
    *,
    order_id,
    actor_business_id,
    return_number,
    return_type,
    reason,
    lines,
    payment_method_id=None,
    created_at=None,
    refund_amount=None,
):
    """Create a posted return. `lines` is a list of dicts: order_item_id, quantity, amount, replacement_product_id."""
    order = db.session.get(RestaurantOrder, order_id)
    if order is None or order.business_id != actor_business_id:
        raise TenantAccessError("Order is not visible to this business")
    if order.status != "paid":
        raise LifecycleError("Returns are posted only against a paid order")
    if return_type not in ("refund", "exchange"):
        raise LifecycleError("Return type must be refund or exchange")
    if payment_method_id is not None:
        require_payment_method(payment_method_id, actor_business_id)
    existing = db.session.scalar(
        select(SalesReturn).where(
            SalesReturn.business_id == actor_business_id,
            SalesReturn.return_number == return_number,
        )
    )
    if existing is not None:
        return existing
    if refund_amount is None:
        refund_amount = money(sum((money(line["amount"]) for line in lines), money(0)))
    else:
        refund_amount = money(refund_amount)
    sales_return = SalesReturn(
        business_id=order.business_id,
        branch_id=order.branch_id,
        order_id=order.id,
        return_number=return_number,
        return_type=return_type,
        status="posted",
        reason=reason,
        refund_amount=refund_amount,
        balance_due=money(0),
        payment_method_id=payment_method_id,
        created_at=created_at or utcnow(),
        posted_at=created_at or utcnow(),
    )
    db.session.add(sales_return)
    db.session.flush()
    for line in lines:
        replacement_id = line.get("replacement_product_id")
        if replacement_id is not None:
            require_product(replacement_id, actor_business_id)
        db.session.add(
            SalesReturnLine(
                sales_return_id=sales_return.id,
                order_item_id=line["order_item_id"],
                quantity=line["quantity"],
                amount=money(line["amount"]),
                replacement_product_id=replacement_id,
            )
        )
    db.session.flush()
    post_return_stock(sales_return, created_at=created_at)
    write_audit(
        action="post_return",
        entity_type="sales_return",
        entity_id=sales_return.id,
        business_id=order.business_id,
        branch_id=order.branch_id,
        message=f"Posted {return_type} {return_number}",
    )
    return sales_return
