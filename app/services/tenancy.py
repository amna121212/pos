"""Tenant guards. Every service that loads a business row should use these."""
from app import db
from app.models import Branch, Business, PaymentMethod, Product
from app.services.errors import TenantAccessError


def require_business(business_id):
    business = db.session.get(Business, business_id)
    if business is None:
        raise TenantAccessError("Business does not exist")
    return business


def require_branch(branch_id, business_id):
    branch = db.session.get(Branch, branch_id)
    if branch is None or branch.business_id != business_id:
        raise TenantAccessError("Branch is not part of this business")
    return branch


def require_product(product_id, business_id):
    product = db.session.get(Product, product_id)
    if product is None or product.business_id != business_id:
        raise TenantAccessError("Product is not part of this business")
    return product


def require_payment_method(method_id, business_id):
    method = db.session.get(PaymentMethod, method_id)
    if method is None or method.business_id != business_id:
        raise TenantAccessError("Payment method is not part of this business")
    return method
