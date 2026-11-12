"""Order totals, payments, hold/resume and idempotent receipt finalisation."""
from sqlalchemy import func, select

from app import db
from app.models import Printer
from app.money import money
from app.order_models import OrderItem, OrderPayment, ReceiptRecord, RestaurantOrder
from app.services.audit import write_audit
from app.services.errors import LifecycleError, PaymentError, TenantAccessError
from app.services.tenancy import require_payment_method


def line_total(unit_price, qty):
    return money(money(unit_price) * qty)


def compute_discount(subtotal, kind, value):
    subtotal = money(subtotal)
    if kind == "percent":
        return money(subtotal * money(value) / money(100))
    if kind == "fixed":
        return money(min(subtotal, money(value)))
    raise PaymentError("Discount kind must be percent or fixed")


def order_totals(*, subtotal, discount, tax_rate_percent):
    """Return discount, tax and grand total as Decimal rupees."""
    subtotal = money(subtotal)
    discount = money(discount)
    if discount > subtotal:
        raise PaymentError("Discount cannot exceed the subtotal")
    taxable = subtotal - discount
    tax = money(taxable * money(tax_rate_percent) / money(100))
    grand = money(taxable + tax)
    return {"subtotal": subtotal, "discount": discount, "tax": tax, "grand": grand}


def captured_total(order_id):
    total = db.session.scalar(
        select(func.coalesce(func.sum(OrderPayment.amount), 0)).where(
            OrderPayment.order_id == order_id,
            OrderPayment.status == "captured",
        )
    )
    return money(total)


def capture_payment(*, order_id, payment_method_id, amount, actor_business_id):
    """Capture a payment without letting the paid total exceed the grand total."""
    order = db.session.get(RestaurantOrder, order_id)
    if order is None or order.business_id != actor_business_id:
        raise TenantAccessError("Order is not visible to this business")
    if order.status in ("cancelled", "voided"):
        raise LifecycleError("A cancelled order cannot take a payment")
    method = require_payment_method(payment_method_id, actor_business_id)
    amount = money(amount)
    if amount <= 0:
        raise PaymentError("Payment amount must be positive")
    already = captured_total(order.id)
    if already >= order.grand_total:
        raise PaymentError("This order is already fully paid")
    if money(already + amount) > order.grand_total:
        raise PaymentError("Payment would exceed the amount due")
    payment = OrderPayment(
        order_id=order.id,
        payment_method_id=method.id,
        amount=amount,
        status="captured",
    )
    db.session.add(payment)
    db.session.flush()
    return payment


def hold_order(order_id, *, actor_business_id):
    order = db.session.get(RestaurantOrder, order_id)
    if order is None or order.business_id != actor_business_id:
        raise TenantAccessError("Order is not visible to this business")
    if order.status != "open":
        raise LifecycleError("Only an open order can be held")
    order.status = "held"
    write_audit(
        action="hold",
        entity_type="restaurant_order",
        entity_id=order.id,
        business_id=order.business_id,
        branch_id=order.branch_id,
        message=f"Held bill {order.order_number}",
    )
    return order


def resume_order(order_id, *, actor_business_id):
    order = db.session.get(RestaurantOrder, order_id)
    if order is None or order.business_id != actor_business_id:
        raise TenantAccessError("Order is not visible to this business")
    if order.status != "held":
        raise LifecycleError("Only a held order can be resumed")
    order.status = "open"
    write_audit(
        action="resume",
        entity_type="restaurant_order",
        entity_id=order.id,
        business_id=order.business_id,
        branch_id=order.branch_id,
        message=f"Resumed bill {order.order_number}",
    )
    return order


def finalize_receipt(order_id, *, actor_business_id, printer_id=None):
    """Create the receipt for a paid order. A second call returns the same receipt."""
    order = db.session.get(RestaurantOrder, order_id)
    if order is None or order.business_id != actor_business_id:
        raise TenantAccessError("Order is not visible to this business")
    existing = db.session.scalar(select(ReceiptRecord).where(ReceiptRecord.order_id == order.id))
    if existing is not None:
        return existing
    if order.status != "paid":
        raise LifecycleError("A receipt is issued only for a fully paid order")
    if captured_total(order.id) != money(order.grand_total):
        raise PaymentError("Receipt requires payments that match the grand total")
    if printer_id is not None:
        printer = db.session.get(Printer, printer_id)
        if printer is None:
            raise LifecycleError("Printer does not exist")
    receipt = ReceiptRecord(
        order_id=order.id,
        printer_id=printer_id,
        receipt_number=f"RCPT-{order.branch_id}-{order.order_number}",
        print_status="not_sent",
    )
    db.session.add(receipt)
    db.session.flush()
    write_audit(
        action="finalize_receipt",
        entity_type="receipt_record",
        entity_id=receipt.id,
        business_id=order.business_id,
        branch_id=order.branch_id,
        message=f"Issued {receipt.receipt_number}",
    )
    return receipt


def subtotal_from_items(order_id):
    items = db.session.scalars(select(OrderItem).where(OrderItem.order_id == order_id)).all()
    return money(sum((money(item.line_total) for item in items), money(0)))
