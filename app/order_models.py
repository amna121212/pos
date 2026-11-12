"""POS Phase 2: restaurant dine-in/takeaway, kitchen tickets, billing.

These 12 models extend Phase 1; all business records are explicitly scoped to a
business and branch where relevant. Server-side routes must enforce membership.
Amounts are Decimal/Numeric, and invoices are generated from saved line prices.
"""
from datetime import datetime, timezone
from app import db


def utc_now():
    return datetime.now(timezone.utc)


class DiningSession(db.Model):
    __tablename__ = 'dining_sessions'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False, index=True)
    dining_table_id = db.Column(db.Integer, db.ForeignKey('dining_tables.id', ondelete='RESTRICT'), nullable=False)
    guest_count = db.Column(db.Integer, nullable=False, default=1)
    opened_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    closed_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (db.CheckConstraint('guest_count > 0', name='ck_dining_session_guests'),)


class RestaurantOrder(db.Model):
    __tablename__ = 'restaurant_orders'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False, index=True)
    dining_session_id = db.Column(db.Integer, db.ForeignKey('dining_sessions.id', ondelete='RESTRICT'))
    order_number = db.Column(db.String(45), nullable=False)
    order_type = db.Column(db.String(20), nullable=False)  # dine_in, takeaway
    status = db.Column(db.String(24), nullable=False, default='open')
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    grand_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_rule_id = db.Column(db.Integer, db.ForeignKey('tax_rules.id', ondelete='RESTRICT'))
    cashier_shift_id = db.Column(db.Integer, db.ForeignKey('cashier_shifts.id', ondelete='RESTRICT'))
    # Provenance label such as APPLICATION_GENERATED or SYNTHETIC_HISTORY_V1.
    dataset_code = db.Column(db.String(40), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    __table_args__ = (
        db.UniqueConstraint('branch_id', 'order_number', name='uq_order_branch_number'),
        db.CheckConstraint(
            "order_type IN ('dine_in','takeaway','counter_pickup','delivery')",
            name='ck_order_type',
        ),
        db.CheckConstraint(
            "status IN ('open','held','paid','partially_paid','cancelled','voided')",
            name='ck_order_status',
        ),
        db.CheckConstraint(
            'subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND grand_total >= 0',
            name='ck_order_totals',
        ),
        db.CheckConstraint('discount_total <= subtotal', name='ck_discount_within_subtotal'),
    )


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('restaurant_orders.id', ondelete='RESTRICT'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.String(150))
    __table_args__ = (db.CheckConstraint('quantity > 0 AND unit_price >= 0 AND line_total >= 0', name='ck_order_item_amounts'),)


class MenuModifierGroup(db.Model):
    __tablename__ = 'menu_modifier_groups'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_required = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (db.UniqueConstraint('product_id', 'name', name='uq_modifier_product_name'),)


class MenuModifierOption(db.Model):
    __tablename__ = 'menu_modifier_options'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('menu_modifier_groups.id', ondelete='RESTRICT'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    extra_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    __table_args__ = (db.UniqueConstraint('group_id', 'name', name='uq_modifier_option_name'),
                      db.CheckConstraint('extra_price >= 0', name='ck_modifier_price'))


class OrderItemModifier(db.Model):
    __tablename__ = 'order_item_modifiers'
    id = db.Column(db.Integer, primary_key=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id', ondelete='RESTRICT'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('menu_modifier_options.id', ondelete='RESTRICT'), nullable=False)
    price_at_sale = db.Column(db.Numeric(12, 2), nullable=False)
    __table_args__ = (db.UniqueConstraint('order_item_id', 'option_id', name='uq_item_modifier'),)


class KitchenTicket(db.Model):
    __tablename__ = 'kitchen_tickets'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('restaurant_orders.id', ondelete='RESTRICT'), nullable=False)
    printer_id = db.Column(db.Integer, db.ForeignKey('printers.id', ondelete='RESTRICT'))
    ticket_number = db.Column(db.String(50), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default='queued')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class KitchenTicketItem(db.Model):
    __tablename__ = 'kitchen_ticket_items'
    id = db.Column(db.Integer, primary_key=True)
    kitchen_ticket_id = db.Column(db.Integer, db.ForeignKey('kitchen_tickets.id', ondelete='RESTRICT'), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id', ondelete='RESTRICT'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued')
    __table_args__ = (db.UniqueConstraint('kitchen_ticket_id', 'order_item_id', name='uq_kot_item'),)


class OrderDiscount(db.Model):
    __tablename__ = 'order_discounts'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('restaurant_orders.id', ondelete='RESTRICT'), nullable=False)
    label = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    __table_args__ = (db.CheckConstraint('amount >= 0', name='ck_discount_amount'),)


class OrderPayment(db.Model):
    __tablename__ = 'order_payments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('restaurant_orders.id', ondelete='RESTRICT'), nullable=False, index=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_methods.id', ondelete='RESTRICT'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='captured')
    paid_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (db.CheckConstraint('amount > 0', name='ck_payment_positive'),)


class OrderStatusEvent(db.Model):
    __tablename__ = 'order_status_events'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('restaurant_orders.id', ondelete='RESTRICT'), nullable=False)
    old_status = db.Column(db.String(24))
    new_status = db.Column(db.String(24), nullable=False)
    message = db.Column(db.String(200))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class ReceiptRecord(db.Model):
    __tablename__ = 'receipt_records'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('restaurant_orders.id', ondelete='RESTRICT'), nullable=False, unique=True)
    printer_id = db.Column(db.Integer, db.ForeignKey('printers.id', ondelete='RESTRICT'))
    receipt_number = db.Column(db.String(50), nullable=False, unique=True)
    print_status = db.Column(db.String(20), nullable=False, default='not_sent')
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
