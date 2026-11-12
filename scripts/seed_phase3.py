"""Idempotent, synthetic tenant-isolated procurement/receiving/transfer demo.
Stock changes are ledger-backed; no deductions from restaurant sales before recipes.
"""
from decimal import Decimal
from sqlalchemy import select, func
from app import create_app, db
from app.models import Business, Branch, Product, Supplier
from app.seeddata.naming import PRIMARY_SUPPLIER, extra_suppliers, receipt_footer_for
from app.inventory_models import (InventoryItem, BranchStock, StockBatch, StockMovement,
    SupplierPurchaseOrder, SupplierPurchaseItem, GoodsReceipt, GoodsReceiptItem,
    StockTransferRequest, StockTransferItem, StockTransferEvent)

D=lambda s: Decimal(str(s))

def get(model, **conditions):
    return db.session.scalar(select(model).filter_by(**conditions))

def run():
    app=create_app()
    with app.app_context():
        actual=db.session.scalar(select(func.current_database()))
        if actual!='retail_pos_db': raise RuntimeError('Refusing wrong database: '+str(actual))
        created=0
        try:
            businesses=db.session.scalars(select(Business).where(Business.is_demo.is_(True)).order_by(Business.id)).all()
            if not businesses: raise RuntimeError('No Phase 1 businesses')
            for biz in businesses:
                branches=db.session.scalars(select(Branch).where(Branch.business_id==biz.id).order_by(Branch.id)).all()
                supplier=get(Supplier,business_id=biz.id,name=PRIMARY_SUPPLIER)
                if len(branches)<2 or supplier is None: raise RuntimeError('Missing branches/supplier for '+biz.name)
                a,b=branches[:2]
                # For restaurants these are supply inventory records, NOT finished menu items.
                if biz.business_type=='restaurant':
                    catalog=[('INV-FLOUR','Flour','kg','55.00'),('INV-OIL','Cooking Oil','ltr','520.00'),('INV-CHICKEN','Chicken','kg','780.00')]
                else:
                    products=db.session.scalars(select(Product).where(Product.business_id==biz.id).order_by(Product.id).limit(3)).all()
                    catalog=[(f'INV-{p.sku}',p.name,'pcs',str(p.base_cost)) for p in products]
                po_no=f'P3-PO-{biz.id:03d}'
                if get(SupplierPurchaseOrder,business_id=biz.id,po_number=po_no):
                    continue  # Entire prior demo transaction already committed; safe rerun.
                po=SupplierPurchaseOrder(business_id=biz.id,branch_id=a.id,supplier_id=supplier.id,po_number=po_no,status='received')
                db.session.add(po);db.session.flush()
                receipt=GoodsReceipt(purchase_order_id=po.id,business_id=biz.id,branch_id=a.id,receipt_number=f'P3-GRN-{biz.id:03d}')
                db.session.add(receipt);db.session.flush()
                first=None
                for ix,(sku,name,unit,cost) in enumerate(catalog):
                    item=get(InventoryItem,business_id=biz.id,sku=sku)
                    if item is None:
                        item=InventoryItem(business_id=biz.id,sku=sku,name=name,unit=unit,reorder_level=D(10))
                        db.session.add(item);db.session.flush()
                    if ix==0:first=item
                    qty=D(100)
                    pi=SupplierPurchaseItem(purchase_order_id=po.id,item_id=item.id,qty_ordered=qty,unit_cost=D(cost))
                    db.session.add(pi);db.session.flush()
                    db.session.add(GoodsReceiptItem(goods_receipt_id=receipt.id,purchase_item_id=pi.id,quantity=qty))
                    stock=get(BranchStock,branch_id=a.id,item_id=item.id)
                    if stock is None:
                        stock=BranchStock(business_id=biz.id,branch_id=a.id,item_id=item.id,quantity=D(0))
                        db.session.add(stock)
                    stock.quantity+=qty
                    db.session.add(StockBatch(business_id=biz.id,branch_id=a.id,item_id=item.id,batch_number=f'P3-BATCH-{biz.id}-{ix}',received_qty=qty))
                    db.session.add(StockMovement(business_id=biz.id,branch_id=a.id,item_id=item.id,movement_type='purchase_receipt',delta_qty=qty,reference_code=receipt.receipt_number))
                transfer=StockTransferRequest(business_id=biz.id,from_branch_id=a.id,to_branch_id=b.id,transfer_number=f'P3-TR-{biz.id:03d}',status='received')
                db.session.add(transfer);db.session.flush()
                qty=D(15)
                db.session.add(StockTransferItem(transfer_id=transfer.id,item_id=first.id,quantity=qty))
                for status in ['requested','approved','dispatched','received']:
                    db.session.add(StockTransferEvent(transfer_id=transfer.id,status=status,note='Synthetic demonstration'))
                from_stock=get(BranchStock,branch_id=a.id,item_id=first.id)
                if from_stock.quantity < qty: raise RuntimeError('Insufficient source stock')
                from_stock.quantity-=qty
                to_stock=get(BranchStock,branch_id=b.id,item_id=first.id)
                if to_stock is None:
                    to_stock=BranchStock(business_id=biz.id,branch_id=b.id,item_id=first.id,quantity=D(0))
                    db.session.add(to_stock)
                to_stock.quantity+=qty
                db.session.add(StockMovement(business_id=biz.id,branch_id=a.id,item_id=first.id,movement_type='transfer_out',delta_qty=-qty,reference_code=transfer.transfer_number))
                db.session.add(StockMovement(business_id=biz.id,branch_id=b.id,item_id=first.id,movement_type='transfer_in',delta_qty=qty,reference_code=transfer.transfer_number))
                created+=1
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        print(f'SUCCESS: synthetic purchasing + receiving + transfer workflows seeded for {created} new businesses')
        for cls in [InventoryItem,BranchStock,StockMovement,SupplierPurchaseOrder,GoodsReceipt,StockTransferRequest]:
            print(f'{cls.__tablename__:26s}',db.session.query(cls).count())
        # Verify ledger equals branch balance for *all* Phase 3 seeded stocks.
        stocks=db.session.scalars(select(BranchStock)).all()
        for stock in stocks:
            movement_total=db.session.scalar(select(func.coalesce(func.sum(StockMovement.delta_qty),0)).where(StockMovement.branch_id==stock.branch_id, StockMovement.item_id==stock.item_id))
            if D(movement_total)!=D(stock.quantity):
                raise RuntimeError(f'Stock ledger mismatch: branch={stock.branch_id}, item={stock.item_id}')
        print('PASS: branch stock quantities reconcile with stock movement ledger')
        print('NOTE: Demo data is synthetic. Restaurant ingredient consumption is not linked to finished-menu sales yet.')

if __name__=='__main__': run()
