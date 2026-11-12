"""Inter-branch transfers. Both branches must belong to the same business."""
from sqlalchemy import select

from app import db
from app.inventory_models import StockTransferEvent, StockTransferItem, StockTransferRequest
from app.money import quantity
from app.services.audit import write_audit
from app.services.errors import StockPolicyError
from app.services.inventory import apply_stock_delta
from app.services.tenancy import require_branch


def post_transfer(*, business_id, from_branch_id, to_branch_id, transfer_number, lines, note):
    """Move stock between two branches of one business. Repeating the transfer number is a no-op."""
    if from_branch_id == to_branch_id:
        raise StockPolicyError("A transfer needs two different branches")
    source = require_branch(from_branch_id, business_id)
    destination = require_branch(to_branch_id, business_id)
    existing = db.session.scalar(
        select(StockTransferRequest).where(StockTransferRequest.transfer_number == transfer_number)
    )
    if existing is not None:
        if existing.business_id != business_id:
            raise StockPolicyError("Transfer number already belongs to another business")
        return existing
    transfer = StockTransferRequest(
        business_id=business_id,
        from_branch_id=source.id,
        to_branch_id=destination.id,
        transfer_number=transfer_number,
        status="received",
    )
    db.session.add(transfer)
    db.session.flush()
    for line in lines:
        qty = quantity(line["quantity"])
        if qty <= 0:
            raise StockPolicyError("Transfer quantity must be positive")
        db.session.add(StockTransferItem(transfer_id=transfer.id, item_id=line["item_id"], quantity=qty))
        apply_stock_delta(
            business_id=business_id,
            branch_id=source.id,
            item_id=line["item_id"],
            movement_type="transfer_out",
            delta_qty=-qty,
            reference_code=transfer_number,
        )
        apply_stock_delta(
            business_id=business_id,
            branch_id=destination.id,
            item_id=line["item_id"],
            movement_type="transfer_in",
            delta_qty=qty,
            reference_code=transfer_number,
        )
    for status in ("requested", "approved", "dispatched", "received"):
        db.session.add(StockTransferEvent(transfer_id=transfer.id, status=status, note=note))
    write_audit(
        action="post_transfer",
        entity_type="stock_transfer",
        entity_id=transfer.id,
        business_id=business_id,
        message=f"Received transfer {transfer_number}",
    )
    return transfer
