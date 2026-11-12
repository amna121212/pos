"""Phase 1 of the POS SaaS schema: 12 connected master-data models.

All tenant-scoped records carry business_id or belong to a tenant-scoped parent.
"""
from datetime import datetime, timezone
from app import db


def now_utc():
    return datetime.now(timezone.utc)


class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    business_type = db.Column(db.String(25), nullable=False)  # restaurant, cafe, retail
    city = db.Column(db.String(80), nullable=False, default='Lahore')
    is_demo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    branches = db.relationship('Branch', back_populates='business')


class Branch(db.Model):
    __tablename__ = 'branches'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    area = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(80), nullable=False, default='Lahore')
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    business = db.relationship('Business', back_populates='branches')
    __table_args__ = (db.UniqueConstraint('business_id', 'code', name='uq_branch_business_code'),)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Platform admin is not a member of any one restaurant.
    is_platform_admin = db.Column(db.Boolean, nullable=False, default=False, server_default='false')
    employee_code = db.Column(db.String(40), unique=True)
    # True for coursework personas. Real accounts added later should set this false.
    is_synthetic = db.Column(db.Boolean, nullable=False, default=False, server_default='false')
    memberships = db.relationship('BusinessUser', back_populates='user')


class BusinessUser(db.Model):
    __tablename__ = 'business_users'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'))
    role = db.Column(db.String(20), nullable=False)  # owner, manager, cashier
    user = db.relationship('User', back_populates='memberships')
    business = db.relationship('Business')
    branch = db.relationship('Branch')
    __table_args__ = (db.UniqueConstraint('business_id', 'user_id', 'branch_id', name='uq_business_user_branch'),)


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    __table_args__ = (db.UniqueConstraint('business_id', 'name', name='uq_category_business_name'),)


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='RESTRICT'), nullable=False)
    sku = db.Column(db.String(35), nullable=False)
    name = db.Column(db.String(130), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default='menu_item')
    base_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    category = db.relationship('Category')
    __table_args__ = (db.UniqueConstraint('business_id', 'sku', name='uq_product_business_sku'),)


class BranchProduct(db.Model):
    __tablename__ = 'branch_products'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False)
    sale_price = db.Column(db.Numeric(12, 2), nullable=False)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    product = db.relationship('Product')
    branch = db.relationship('Branch')
    __table_args__ = (db.UniqueConstraint('branch_id', 'product_id', name='uq_branch_product'),
                      db.CheckConstraint('sale_price >= 0', name='ck_branch_product_price_nonnegative'))


class DiningTable(db.Model):
    __tablename__ = 'dining_tables'
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False)
    table_number = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint('branch_id', 'table_number', name='uq_table_branch_number'),
                      db.CheckConstraint('capacity > 0', name='ck_table_capacity_positive'))


class PaymentMethod(db.Model):
    __tablename__ = 'payment_methods'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    code = db.Column(db.String(30), nullable=False)
    label = db.Column(db.String(70), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (db.UniqueConstraint('business_id', 'code', name='uq_payment_business_code'),)


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    name = db.Column(db.String(130), nullable=False)
    city = db.Column(db.String(80), nullable=False, default='Lahore')
    lead_time_days = db.Column(db.Integer, nullable=False, default=2, server_default='2')
    is_synthetic = db.Column(db.Boolean, nullable=False, default=True, server_default='true')
    __table_args__ = (
        db.UniqueConstraint('business_id', 'name', name='uq_supplier_business_name'),
        db.CheckConstraint('lead_time_days >= 0', name='ck_supplier_lead_time'),
    )


class Printer(db.Model):
    __tablename__ = 'printers'
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False)
    label = db.Column(db.String(90), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)  # receipt, kitchen, label
    connection_type = db.Column(db.String(20), nullable=False, default='browser')
    paper_width_mm = db.Column(db.Integer)
    __table_args__ = (
        db.UniqueConstraint('branch_id', 'label', name='uq_printer_branch_label'),
        db.CheckConstraint("purpose IN ('receipt','kitchen','label')", name='ck_printer_purpose'),
        db.CheckConstraint('paper_width_mm IS NULL OR paper_width_mm IN (58, 80)', name='ck_printer_paper_width'),
    )


class CashRegister(db.Model):
    __tablename__ = 'cash_registers'
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False)
    code = db.Column(db.String(30), nullable=False)
    label = db.Column(db.String(80), nullable=False)
    __table_args__ = (db.UniqueConstraint('branch_id', 'code', name='uq_register_branch_code'),)

# Register later phases so Flask-Migrate sees one metadata catalog.
from app import order_models  # noqa: F401
from app import inventory_models  # noqa: F401
from app import platform_models  # noqa: F401
from app import recipe_models  # noqa: F401
from app import operations_models  # noqa: F401
from app import intelligence_models  # noqa: F401
