"""The till: price a basket, write the order, take payment, deduct stock, issue the receipt.

Routes call these functions and never write order rows themselves, so the
totals, the stock ledger and the receipt always come from one code path.
"""
from sqlalchemy import select

from app import db
from app.money import money
from app.models import BranchProduct, Business, DiningTable, Printer, Product
from app.numbering import next_order_number
from app.operations_models import OrderFulfillment
from app.order_models import (
    DiningSession,
    KitchenTicket,
    KitchenTicketItem,
    MenuModifierGroup,
    MenuModifierOption,
    OrderDiscount,
    OrderItem,
    OrderItemModifier,
    OrderStatusEvent,
    RestaurantOrder,
)
from app.platform_models import TaxRule
from app.services.audit import write_audit
from app.services.errors import PaymentError
from app.services.orders import capture_payment, compute_discount, finalize_receipt, order_totals
from app.services.recipes import post_recipe_consumption
from app.timeutil import utcnow

ORDER_TYPES = ("dine_in", "takeaway", "counter_pickup")


def active_tax_rule(business_id):
    """The applicable demo tax rate. 'all' wins over a kind-specific rule."""
    return db.session.scalar(
        select(TaxRule)
        .where(TaxRule.business_id == business_id, TaxRule.is_active.is_(True))
        .order_by((TaxRule.applies_to == "all").desc(), TaxRule.rate_percent)
    )


def _load_options(product_id, option_ids):
    """Accept only modifier options that belong to this product's own groups."""
    wanted = sorted({int(option) for option in option_ids or []})
    if not wanted:
        return []
    rows = db.session.scalars(
        select(MenuModifierOption)
        .join(MenuModifierGroup, MenuModifierGroup.id == MenuModifierOption.group_id)
        .where(
            MenuModifierGroup.product_id == product_id,
            MenuModifierOption.id.in_(wanted),
        )
    ).all()
    if len(rows) != len(wanted):
        raise PaymentError("One of the selected options is not valid for this item.")
    return list(rows)


def price_lines(*, business_id, branch_id, lines):
    """Resolve basket lines against branch prices. Client prices are never trusted."""
    if not lines:
        return []
    product_ids = [int(line["product_id"]) for line in lines]
    rows = db.session.execute(
        select(BranchProduct, Product)
        .join(Product, Product.id == BranchProduct.product_id)
        .where(
            BranchProduct.business_id == business_id,
            BranchProduct.branch_id == branch_id,
            BranchProduct.product_id.in_(product_ids),
            BranchProduct.is_available.is_(True),
            Product.is_active.is_(True),
        )
    ).all()
    available = {product.id: (branch_product, product) for branch_product, product in rows}

    priced = []
    for line in lines:
        found = available.get(int(line["product_id"]))
        if found is None:
            raise PaymentError("An item in the basket is no longer sold at this branch.")
        branch_product, product = found
        options = _load_options(product.id, line.get("options"))
        unit_price = money(branch_product.sale_price)
        for option in options:
            unit_price += money(option.extra_price)
        quantity = max(1, min(999, int(line.get("qty", 1))))
        priced.append(
            {
                "product": product,
                "product_id": product.id,
                "name": product.name,
                "sku": product.sku,
                "quantity": quantity,
                "unit_price": money(unit_price),
                "line_total": money(unit_price * quantity),
                "options": options,
                "option_label": ", ".join(option.name for option in options),
                "note": (line.get("note") or "")[:150],
            }
        )
    return priced


def quote(*, business_id, branch_id, lines, discount_kind=None, discount_value=0):
    """Everything the cart panel needs to render, including tax and discount.

    `discount_value` means different things depending on `discount_kind`: a
    percentage of the subtotal for `percent`, a flat rupee amount for `fixed`.
    Passing the raw figure straight through as an amount is what made a 10%
    discount take off ten rupees.
    """
    priced = price_lines(business_id=business_id, branch_id=branch_id, lines=lines)
    subtotal = money(sum((line["line_total"] for line in priced), money(0)))
    rule = active_tax_rule(business_id)
    rate = money(rule.rate_percent) if rule is not None else money(0)

    discount = money(0)
    if discount_kind in ("percent", "fixed") and money(discount_value) > 0:
        discount = compute_discount(subtotal, discount_kind, discount_value)

    totals = order_totals(subtotal=subtotal, discount=discount, tax_rate_percent=rate)
    return {
        "lines": priced,
        "subtotal": subtotal,
        "discount": totals["discount"],
        "tax": totals["tax"],
        "grand": totals["grand"],
        "tax_rate": rate,
        "tax_rule": rule,
        "discount_kind": discount_kind,
        "discount_value": money(discount_value),
    }


def _raise_kitchen_ticket(order, priced, *, business_id, branch):
    """Send the cooked lines to the kitchen board. Retail sales get no ticket."""
    business = db.session.get(Business, business_id)
    if business is None or business.business_type not in ("restaurant", "cafe"):
        return None
    printer = db.session.scalar(
        select(Printer).where(Printer.branch_id == branch.id, Printer.purpose == "kitchen")
    )
    ticket = KitchenTicket(
        order_id=order.id,
        printer_id=printer.id if printer is not None else None,
        # ticket_number is globally unique, and (branch_id, order_number) is unique,
        # so the branch id must be part of it: two businesses can both use branch code MAIN.
        ticket_number=f"KOT-{branch.id}-{order.order_number}"[:50],
        status="queued",
        created_at=utcnow(),
    )
    db.session.add(ticket)
    db.session.flush()
    for line in priced:
        item = db.session.scalar(
            select(OrderItem).where(
                OrderItem.order_id == order.id,
                OrderItem.product_id == line["product_id"],
            )
        )
        if item is None:
            continue
        db.session.add(
            KitchenTicketItem(kitchen_ticket_id=ticket.id, order_item_id=item.id, status="queued")
        )
    return ticket


def _open_dining_session(*, business_id, branch_id, table_id):
    table = db.session.get(DiningTable, table_id) if table_id else None
    if table is None:
        return None
    session_row = DiningSession(
        business_id=business_id,
        branch_id=branch_id,
        dining_table_id=table.id,
        guest_count=1,
        opened_at=utcnow(),
    )
    db.session.add(session_row)
    db.session.flush()
    return session_row


def resolve_amount_paid(grand_total, amount_paid):
    """What the guest actually hands over.

    Blank means "bill the full amount due", which is the total *after* any
    discount and tax. Falling back to a pre-discount figure is what used to make
    a discounted bill fail with "received amount is more than the total due".
    """
    if amount_paid is None or str(amount_paid).strip() == "":
        return money(grand_total)
    return money(amount_paid)


def create_order(
    *,
    business_id,
    branch,
    order_type,
    lines,
    table_id=None,
    discount_kind=None,
    discount_value=0,
    payment_method_id=None,
    amount_paid=None,
    note="",
    cashier_shift_id=None,
    actor_user_id=None,
):
    """Create and optionally settle one order. Commits on success, rolls back on failure."""
    if order_type not in ORDER_TYPES:
        raise PaymentError("Choose dine-in, takeaway or counter pickup.")
    quote_result = quote(
        business_id=business_id,
        branch_id=branch.id,
        lines=lines,
        discount_kind=discount_kind,
        discount_value=discount_value,
    )
    priced = quote_result["lines"]
    if not priced:
        raise PaymentError("Add at least one item before taking payment.")

    amount_paid = resolve_amount_paid(quote_result["grand"], amount_paid)
    if amount_paid > quote_result["grand"]:
        raise PaymentError("Received amount is more than the total due.")
    if amount_paid < 0:
        raise PaymentError("Received amount cannot be negative.")

    try:
        order = RestaurantOrder(
            business_id=business_id,
            branch_id=branch.id,
            order_number=next_order_number(branch),
            order_type=order_type,
            status="open",
            subtotal=quote_result["subtotal"],
            discount_total=quote_result["discount"],
            tax_total=quote_result["tax"],
            grand_total=quote_result["grand"],
            tax_rule_id=quote_result["tax_rule"].id if quote_result["tax_rule"] else None,
            cashier_shift_id=cashier_shift_id,
            dataset_code="APPLICATION_GENERATED",
            created_at=utcnow(),
        )
        if order_type == "dine_in" and table_id:
            dining = _open_dining_session(
                business_id=business_id, branch_id=branch.id, table_id=table_id
            )
            order.dining_session_id = dining.id if dining is not None else None
        db.session.add(order)
        db.session.flush()

        for line in priced:
            item = OrderItem(
                order_id=order.id,
                product_id=line["product_id"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                line_total=line["line_total"],
                note=line["note"] or None,
            )
            db.session.add(item)
            db.session.flush()
            for option in line["options"]:
                db.session.add(
                    OrderItemModifier(
                        order_item_id=item.id,
                        option_id=option.id,
                        price_at_sale=money(option.extra_price),
                    )
                )

        db.session.add(
            OrderStatusEvent(order_id=order.id, old_status=None, new_status="open", message="Bill opened")
        )
        _raise_kitchen_ticket(order, priced, business_id=business_id, branch=branch)
        table = db.session.get(DiningTable, table_id) if table_id else None
        db.session.add(
            OrderFulfillment(
                order_id=order.id,
                fulfillment_type=order_type,
                contact_label=(table.table_number if table is not None else branch.name)[:80],
                area=branch.area[:100],
                notes=(note or "")[:200] or None,
            )
        )
        if quote_result["discount"] > 0:
            db.session.add(
                OrderDiscount(
                    order_id=order.id,
                    label="Till discount" if not discount_kind else f"Till discount ({discount_kind})",
                    amount=quote_result["discount"],
                )
            )

        if amount_paid > 0:
            capture_payment(
                order_id=order.id,
                payment_method_id=payment_method_id,
                amount=amount_paid,
                actor_business_id=business_id,
            )

        if amount_paid >= quote_result["grand"]:
            order.status = "paid"
            db.session.add(
                OrderStatusEvent(order_id=order.id, old_status="open", new_status="paid", message="Paid in full")
            )
            db.session.flush()
            post_recipe_consumption(order.id, actor_business_id=business_id)
            finalize_receipt(order.id, actor_business_id=business_id)
            if order.dining_session_id:
                dining = db.session.get(DiningSession, order.dining_session_id)
                if dining is not None:
                    dining.closed_at = utcnow()
        elif amount_paid > 0:
            order.status = "partially_paid"
            db.session.add(
                OrderStatusEvent(
                    order_id=order.id,
                    old_status="open",
                    new_status="partially_paid",
                    message="Part payment captured",
                )
            )

        write_audit(
            action="create_order",
            entity_type="restaurant_order",
            entity_id=order.id,
            business_id=business_id,
            branch_id=branch.id,
            actor_user_id=actor_user_id,
            message=f"{order.order_number} {order.status} total {order.grand_total}",
        )
        db.session.commit()
        return order
    except Exception:
        db.session.rollback()
        raise
