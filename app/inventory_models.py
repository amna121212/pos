"""Phase 3: tenant-scoped inventory, procurement and branch transfers."""
from datetime import datetime, timezone
from app import db

def utcnow():
    return datetime.now(timezone.utc)

class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=True)
    sku = db.Column(db.String(48), nullable=False)
    name = db.Column(db.String(130), nullable=False)
    unit = db.Column(db.String(24), nullable=False, default='pcs')
    reorder_level = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    # Curated demo cost per stock unit. Not a live market quotation.
    standard_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default='0')
    __table_args__ = (
        db.UniqueConstraint('business_id','sku',name='uq_inventory_item_tenant_sku'),
        db.CheckConstraint('reorder_level >= 0',name='ck_item_reorder_nonnegative'),
        db.CheckConstraint('standard_cost >= 0', name='ck_item_standard_cost_nonnegative'),
    )

class BranchStock(db.Model):
    __tablename__ = 'branch_stocks'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id', ondelete='RESTRICT'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('inventory_items.id', ondelete='RESTRICT'), nullable=False)
    quantity = db.Column(db.Numeric(14,3),nullable=False,default=0)
    __table_args__ = (db.UniqueConstraint('branch_id','item_id',name='uq_branch_stock_item'),db.CheckConstraint('quantity >= 0',name='ck_stock_nonnegative'))

class StockBatch(db.Model):
    __tablename__ = 'stock_batches'
    id = db.Column(db.Integer,primary_key=True)
    business_id = db.Column(db.Integer,db.ForeignKey('businesses.id',ondelete='RESTRICT'),nullable=False)
    branch_id = db.Column(db.Integer,db.ForeignKey('branches.id',ondelete='RESTRICT'),nullable=False)
    item_id = db.Column(db.Integer,db.ForeignKey('inventory_items.id',ondelete='RESTRICT'),nullable=False)
    batch_number = db.Column(db.String(65),nullable=False)
    received_qty = db.Column(db.Numeric(14,3),nullable=False)
    expiry_date = db.Column(db.Date)
    __table_args__=(db.UniqueConstraint('branch_id','item_id','batch_number',name='uq_batch_branch_item_no'),db.CheckConstraint('received_qty > 0',name='ck_batch_received_positive'))

class StockMovement(db.Model):
    __tablename__='stock_movements'
    id=db.Column(db.Integer,primary_key=True)
    business_id=db.Column(db.Integer,db.ForeignKey('businesses.id',ondelete='RESTRICT'),nullable=False,index=True)
    branch_id=db.Column(db.Integer,db.ForeignKey('branches.id',ondelete='RESTRICT'),nullable=False,index=True)
    item_id=db.Column(db.Integer,db.ForeignKey('inventory_items.id',ondelete='RESTRICT'),nullable=False)
    movement_type=db.Column(db.String(24),nullable=False)
    delta_qty=db.Column(db.Numeric(14,3),nullable=False)
    reference_code=db.Column(db.String(75),nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    __table_args__=(db.UniqueConstraint('branch_id','item_id','movement_type','reference_code',name='uq_stock_movement_reference'),db.CheckConstraint('delta_qty <> 0',name='ck_movement_nonzero'))

class StockAdjustment(db.Model):
    __tablename__='stock_adjustments'
    id=db.Column(db.Integer,primary_key=True)
    business_id=db.Column(db.Integer,db.ForeignKey('businesses.id',ondelete='RESTRICT'),nullable=False)
    branch_id=db.Column(db.Integer,db.ForeignKey('branches.id',ondelete='RESTRICT'),nullable=False)
    item_id=db.Column(db.Integer,db.ForeignKey('inventory_items.id',ondelete='RESTRICT'),nullable=False)
    adjustment_code=db.Column(db.String(60),nullable=False,unique=True)
    delta_qty=db.Column(db.Numeric(14,3),nullable=False)
    reason=db.Column(db.String(150),nullable=False)
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    __table_args__=(db.CheckConstraint('delta_qty <> 0',name='ck_adjust_nonzero'),)

class SupplierPurchaseOrder(db.Model):
    __tablename__='supplier_purchase_orders'
    id=db.Column(db.Integer,primary_key=True)
    business_id=db.Column(db.Integer,db.ForeignKey('businesses.id',ondelete='RESTRICT'),nullable=False)
    branch_id=db.Column(db.Integer,db.ForeignKey('branches.id',ondelete='RESTRICT'),nullable=False)
    supplier_id=db.Column(db.Integer,db.ForeignKey('suppliers.id',ondelete='RESTRICT'),nullable=False)
    po_number=db.Column(db.String(60),nullable=False)
    status=db.Column(db.String(20),nullable=False,default='draft')
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    __table_args__=(db.UniqueConstraint('business_id','po_number',name='uq_po_business_number'),)

class SupplierPurchaseItem(db.Model):
    __tablename__='supplier_purchase_items'
    id=db.Column(db.Integer,primary_key=True)
    purchase_order_id=db.Column(db.Integer,db.ForeignKey('supplier_purchase_orders.id',ondelete='RESTRICT'),nullable=False)
    item_id=db.Column(db.Integer,db.ForeignKey('inventory_items.id',ondelete='RESTRICT'),nullable=False)
    qty_ordered=db.Column(db.Numeric(14,3),nullable=False)
    unit_cost=db.Column(db.Numeric(12,2),nullable=False)
    __table_args__=(db.UniqueConstraint('purchase_order_id','item_id',name='uq_po_item'),db.CheckConstraint('qty_ordered > 0 AND unit_cost >= 0',name='ck_purchase_item_values'))

class GoodsReceipt(db.Model):
    __tablename__='goods_receipts'
    id=db.Column(db.Integer,primary_key=True)
    purchase_order_id=db.Column(db.Integer,db.ForeignKey('supplier_purchase_orders.id',ondelete='RESTRICT'),nullable=False)
    business_id=db.Column(db.Integer,db.ForeignKey('businesses.id',ondelete='RESTRICT'),nullable=False)
    branch_id=db.Column(db.Integer,db.ForeignKey('branches.id',ondelete='RESTRICT'),nullable=False)
    receipt_number=db.Column(db.String(65),nullable=False,unique=True)
    received_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)

class GoodsReceiptItem(db.Model):
    __tablename__='goods_receipt_items'
    id=db.Column(db.Integer,primary_key=True)
    goods_receipt_id=db.Column(db.Integer,db.ForeignKey('goods_receipts.id',ondelete='RESTRICT'),nullable=False)
    purchase_item_id=db.Column(db.Integer,db.ForeignKey('supplier_purchase_items.id',ondelete='RESTRICT'),nullable=False)
    quantity=db.Column(db.Numeric(14,3),nullable=False)
    __table_args__=(db.UniqueConstraint('goods_receipt_id','purchase_item_id',name='uq_goods_receipt_item'),db.CheckConstraint('quantity > 0',name='ck_goods_receipt_qty'))

class StockTransferRequest(db.Model):
    __tablename__='stock_transfer_requests'
    id=db.Column(db.Integer,primary_key=True)
    business_id=db.Column(db.Integer,db.ForeignKey('businesses.id',ondelete='RESTRICT'),nullable=False)
    from_branch_id=db.Column(db.Integer,db.ForeignKey('branches.id',ondelete='RESTRICT'),nullable=False)
    to_branch_id=db.Column(db.Integer,db.ForeignKey('branches.id',ondelete='RESTRICT'),nullable=False)
    transfer_number=db.Column(db.String(65),nullable=False,unique=True)
    status=db.Column(db.String(20),nullable=False,default='requested')
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
    __table_args__=(db.CheckConstraint('from_branch_id <> to_branch_id',name='ck_transfer_different_branches'),)

class StockTransferItem(db.Model):
    __tablename__='stock_transfer_items'
    id=db.Column(db.Integer,primary_key=True)
    transfer_id=db.Column(db.Integer,db.ForeignKey('stock_transfer_requests.id',ondelete='RESTRICT'),nullable=False)
    item_id=db.Column(db.Integer,db.ForeignKey('inventory_items.id',ondelete='RESTRICT'),nullable=False)
    quantity=db.Column(db.Numeric(14,3),nullable=False)
    __table_args__=(db.UniqueConstraint('transfer_id','item_id',name='uq_transfer_item'),db.CheckConstraint('quantity > 0',name='ck_transfer_qty_positive'))

class StockTransferEvent(db.Model):
    __tablename__='stock_transfer_events'
    id=db.Column(db.Integer,primary_key=True)
    transfer_id=db.Column(db.Integer,db.ForeignKey('stock_transfer_requests.id',ondelete='RESTRICT'),nullable=False)
    status=db.Column(db.String(20),nullable=False)
    note=db.Column(db.String(200))
    created_at=db.Column(db.DateTime(timezone=True),nullable=False,default=utcnow)
