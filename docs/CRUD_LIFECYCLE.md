# CRUD and lifecycle

The university rubric expects Create, Read, Update and Delete behaviour. For a POS ledger, Delete is not always a physical `DELETE`.

## Ordinary master data

These rows are created and read through the seed scripts and the CSV importer. They can be updated while nothing important points at them. `is_active` is the safe way to retire a product, recipe, station or tax rule. Foreign keys use `ON DELETE RESTRICT`, so a category that still has products cannot be deleted. The database raises an integrity error instead of leaving orphans.

Examples: businesses, branches, categories, products, branch prices, suppliers, printers, registers, roles, permissions, tax rules, recipes, stations, barcodes.

## Documents that stay after they are posted

Sales, payments, receipts, returns, stock movements, purchase receipts and shift reconciliations are historical facts.

- Create inserts the document and, for stock, a matching ledger row.
- Read is a normal query filtered by `business_id`.
- Update is limited to status fields such as print status, shift close, or a draft that has not been posted.
- Delete is refused once the row is referenced. The lifecycle is void, cancel or reverse.

| Situation | What to do | What not to do |
| --- | --- | --- |
| Guest leaves before paying | Set the order status to `cancelled` and write an `order_status_events` row | Delete the order if lines were already saved |
| Bill is paused | Set status to `held`, then back to `open` | Delete the ticket |
| Guest returns an item | Insert a posted `sales_returns` row and restock through a new movement | Edit the original payment down and delete stock history |
| Count is short | Insert `stock_adjustments` and a negative `stock_movements` row | Change `branch_stocks.quantity` with no movement |
| Receipt button is pressed twice | Return the existing `receipt_records` row | Insert a second receipt |
| Payment is posted twice | The service rejects a capture that would exceed the grand total | Insert another full payment |

## Services that implement the lifecycle

- `app/services/orders.py` prices a ticket, captures payment, holds and resumes, and finalises a receipt once.
- `app/services/recipes.py` deducts ingredients for a paid order once.
- `app/services/returns.py` posts a refund or exchange and restocks only what was consumed.
- `app/services/inventory.py` is the only supported way to change on-hand quantity.
- `app/services/transfers.py` moves stock inside one business.
- `app/services/pricing.py` checks a discount against the margin floor.
- `app/services/tenancy.py` rejects a branch, product or payment method from another business.

HTTP routes are not part of this database phase. Later Flask views should call these functions and then redirect with a flash message.

## Tenant rule

Every service that loads an order, product, branch or payment method compares `business_id` with the acting business. A manipulated id from another restaurant raises `TenantAccessError` before any write. Triggers on orders, order lines, branch prices and transfers repeat that rule inside PostgreSQL.
