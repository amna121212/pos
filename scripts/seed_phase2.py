"""Idempotent, explicitly synthetic Lahore restaurant POS demo orders.

Only touches retail_pos_db. Builds 24 small example sales from products belonging
strictly to the selected business and branch. No assertions of real sales data.
"""
from decimal import Decimal
from sqlalchemy import select, func
from app import create_app, db
from app.models import Business, Branch, BranchProduct, PaymentMethod, Printer, DiningTable
from app.order_models import (DiningSession, RestaurantOrder, OrderItem, KitchenTicket,
    KitchenTicketItem, OrderPayment, OrderDiscount, OrderStatusEvent, ReceiptRecord,
    MenuModifierGroup, MenuModifierOption, OrderItemModifier)


def money(value):
    return Decimal(value).quantize(Decimal('0.01'))


def seed():
    app = create_app()
    with app.app_context():
        current = db.session.execute(select(func.current_database())).scalar_one()
        if current != 'retail_pos_db':
            raise RuntimeError(f'Refusing to seed wrong database: {current}')
        try:
            restaurants = db.session.scalars(select(Business).where(Business.business_type == 'restaurant', Business.is_demo.is_(True))).all()
            if not restaurants:
                raise RuntimeError('Phase 1 restaurant master data not found')
            made = 0
            for business in restaurants:
                branches = db.session.scalars(select(Branch).where(Branch.business_id == business.id).order_by(Branch.id)).all()
                method = db.session.scalar(select(PaymentMethod).where(PaymentMethod.business_id == business.id, PaymentMethod.code == 'cash'))
                if method is None:
                    raise RuntimeError(f'Cash payment method missing: {business.name}')
                for branch in branches:
                    available = db.session.scalars(select(BranchProduct).where(BranchProduct.branch_id == branch.id, BranchProduct.business_id == business.id, BranchProduct.is_available.is_(True)).order_by(BranchProduct.id)).all()
                    if len(available) < 2:
                        raise RuntimeError(f'Need at least 2 menu items at branch {branch.id}')
                    kitchen_printer = db.session.scalar(select(Printer).where(Printer.branch_id == branch.id, Printer.purpose == 'kitchen'))
                    receipt_printer = db.session.scalar(select(Printer).where(Printer.branch_id == branch.id, Printer.purpose == 'receipt'))
                    first_table = db.session.scalar(select(DiningTable).where(DiningTable.branch_id == branch.id).order_by(DiningTable.id))
                    for n in range(1, 7):
                        order_no = f'DEMO-{branch.code}-{n:03d}'
                        existing = db.session.scalar(select(RestaurantOrder).where(RestaurantOrder.branch_id == branch.id, RestaurantOrder.order_number == order_no))
                        if existing is not None:
                            continue
                        is_dinein = n % 2 == 0
                        ds = None
                        if is_dinein:
                            if first_table is None:
                                raise RuntimeError(f'Dining table missing for branch {branch.id}')
                            ds = DiningSession(business_id=business.id, branch_id=branch.id, dining_table_id=first_table.id, guest_count=2)
                            db.session.add(ds)
                            db.session.flush()
                        chosen = [available[n % len(available)], available[(n + 1) % len(available)]]
                        details = [(bp, 1 if idx == 0 else 2) for idx,bp in enumerate(chosen)]
                        subtotal = sum((money(bp.sale_price) * qty for bp, qty in details), Decimal('0.00'))
                        discount = money('50') if n == 6 and subtotal >= 500 else money('0')
                        # Zero tax is an explicit demo rule, not a representation of Pakistan tax treatment.
                        grand = subtotal - discount
                        order = RestaurantOrder(business_id=business.id, branch_id=branch.id,
                            dining_session_id=ds.id if ds else None, order_number=order_no,
                            order_type='dine_in' if is_dinein else 'takeaway', status='paid',
                            subtotal=subtotal, discount_total=discount, tax_total=money('0'), grand_total=grand)
                        db.session.add(order)
                        db.session.flush()
                        db.session.add(OrderStatusEvent(order_id=order.id, old_status=None, new_status='open', message='Synthetic sample order'))
                        item_ids = []
                        for bp, qty in details:
                            line = OrderItem(order_id=order.id, product_id=bp.product_id, quantity=qty,
                                             unit_price=money(bp.sale_price), line_total=money(bp.sale_price)*qty)
                            db.session.add(line)
                            db.session.flush()
                            item_ids.append(line.id)
                        if discount:
                            db.session.add(OrderDiscount(order_id=order.id, label='Demo promotion', amount=discount))
                        kot = KitchenTicket(order_id=order.id, printer_id=kitchen_printer.id if kitchen_printer else None,
                                            ticket_number=f'KOT-{branch.id}-{n:03d}', status='ready')
                        db.session.add(kot)
                        db.session.flush()
                        for item_id in item_ids:
                            db.session.add(KitchenTicketItem(kitchen_ticket_id=kot.id, order_item_id=item_id, status='ready'))
                        db.session.add(OrderPayment(order_id=order.id, payment_method_id=method.id, amount=grand, status='captured'))
                        db.session.add(OrderStatusEvent(order_id=order.id, old_status='open', new_status='paid', message='Synthetic payment completed'))
                        db.session.add(ReceiptRecord(order_id=order.id,
                            printer_id=receipt_printer.id if receipt_printer else None,
                            receipt_number=f'RCPT-{branch.id}-{n:03d}', print_status='not_sent'))
                        made += 1
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        print(f'SUCCESS: {made} new synthetic restaurant orders added (safe to rerun).')
        for name, model in [('restaurant_orders', RestaurantOrder), ('order_items', OrderItem),
            ('kitchen_tickets', KitchenTicket), ('order_payments', OrderPayment),
            ('receipt_records', ReceiptRecord)]:
            print(f'{name:24} {db.session.query(model).count()}')
        print('NOTE: These are simulation records, not verified Lahore restaurant sales.')


if __name__ == '__main__':
    seed()
