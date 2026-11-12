"""Human-readable document numbers.

The database has unique constraints on every one of these, so a collision is a
retry rather than a corrupt ledger. Numbers are per branch or per business as
the constraint requires.
"""
from sqlalchemy import func, select

from app import db
from app.inventory_models import (
    StockTransferRequest,
    SupplierPurchaseOrder,
)
from app.operations_models import CashierShift, SalesReturn
from app.order_models import RestaurantOrder


def _free(candidate, exists):
    return candidate if not exists(candidate) else None


def _scan(prefix, start, exists, width=5, limit=500):
    for number in range(max(start, 1), max(start, 1) + limit):
        candidate = f"{prefix}-{number:0{width}d}"
        if not exists(candidate):
            return candidate
    raise RuntimeError(f"Cannot allocate a free number for {prefix}")


def next_order_number(branch):
    """ORD-JT-00025 style, unique inside the branch."""
    def exists(number):
        return db.session.scalar(
            select(RestaurantOrder.id).where(
                RestaurantOrder.branch_id == branch.id,
                RestaurantOrder.order_number == number,
            )
        ) is not None

    used = db.session.scalar(
        select(func.count()).select_from(RestaurantOrder).where(RestaurantOrder.branch_id == branch.id)
    )
    return _scan(f"ORD-{branch.code}", int(used or 0) + 1, exists, width=5)


def next_purchase_order_number(business_id, branch):
    def exists(number):
        return db.session.scalar(
            select(SupplierPurchaseOrder.id).where(
                SupplierPurchaseOrder.business_id == business_id,
                SupplierPurchaseOrder.po_number == number,
            )
        ) is not None

    used = db.session.scalar(
        select(func.count()).select_from(SupplierPurchaseOrder).where(SupplierPurchaseOrder.business_id == business_id)
    )
    return _scan(f"PO-{branch.code}", int(used or 0) + 1, exists, width=4)


def next_transfer_number():
    def exists(number):
        return db.session.scalar(
            select(StockTransferRequest.id).where(StockTransferRequest.transfer_number == number)
        ) is not None

    used = db.session.scalar(select(func.count()).select_from(StockTransferRequest))
    return _scan("TRF", int(used or 0) + 1, exists, width=4)


def next_return_number(business_id):
    def exists(number):
        return db.session.scalar(
            select(SalesReturn.id).where(
                SalesReturn.business_id == business_id,
                SalesReturn.return_number == number,
            )
        ) is not None

    used = db.session.scalar(
        select(func.count()).select_from(SalesReturn).where(SalesReturn.business_id == business_id)
    )
    return _scan("RET", int(used or 0) + 1, exists, width=5)


def next_shift_code(branch):
    def exists(code):
        return db.session.scalar(
            select(CashierShift.id).where(
                CashierShift.branch_id == branch.id,
                CashierShift.shift_code == code,
            )
        ) is not None

    used = db.session.scalar(
        select(func.count()).select_from(CashierShift).where(CashierShift.branch_id == branch.id)
    )
    return _scan(f"SHIFT-{branch.code}", int(used or 0) + 1, exists, width=4)
