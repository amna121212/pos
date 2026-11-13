# Routes, permissions and CRUD coverage

Every route is server-side guarded. A cashier cannot reach a manager page by typing
its URL; the guard is a permission lookup against the database, not a hidden link.

## Permission model

`business_users.role` holds a role code. That code maps through `role_permissions`
to rows in `permissions`. The context loader reads the set once per request and
caches it keyed by the session's `(uid, bid, branch_id)` tuple, so a branch switch
can never reuse a stale identity.

| Permission | Cashier | Kitchen | Inventory | Manager | Owner |
| --- | --- | --- | --- | --- | --- |
| `order.create` | yes | | | yes | yes |
| `payment.capture` | yes | | | yes | yes |
| `order.discount` | yes | | | yes | yes |
| `order.void` | | | | yes | yes |
| `order.refund` | | | | yes | yes |
| `kitchen.update` | | yes | | yes | yes |
| `inventory.adjust` | | | yes | yes | yes |
| `inventory.purchase` | | | yes | yes | yes |
| `inventory.transfer` | | | yes | yes | yes |
| `menu.manage` | | | | yes | yes |
| `staff.manage` | | | | yes | yes |
| `branch.manage` | | | | yes | yes |
| `report.view` | yes | | yes | yes | yes |
| `business.settings` | | | | | yes |
| `platform.manage` | | | | | platform admin |

Cashier and manager rows also hold `printer.manage` and `shift.manage`. No route
gates on those two yet: printing is allowed for any signed-in branch user, and the
shift screens are not built. They stay in the table because they are seeded data,
not decisions this application made.

Tenant isolation is a second, independent check. Queries filter on
`business_id` and the allowed branch ids; a row outside that scope returns 404 or
403 even for a permitted role. `app/services/tenancy.py` repeats the check inside
the service layer, and PostgreSQL triggers repeat it for orders, order lines,
branch prices and transfers.

## Routes

| Method | Rule | Endpoint | Guard |
| --- | --- | --- | --- |
| GET, POST | `/login` | `auth.login` | public |
| GET, POST | `/signup` | `auth.signup` | public while `POS_SIGNUP_ENABLED=1`, else 404 |
| POST | `/logout` | `auth.logout` | signed in |
| GET/POST | `/branches/new` | `admin.branch_new` | add a branch to the business |
| GET/POST | `/staff/new` | `admin.staff_new` | create an employee account with a role and branch |
| GET/POST | `/staff/<id>/edit` | `admin.staff_edit` | name, role, branch, optional password reset |
| POST | `/staff/<id>/delete` | `admin.staff_delete` | refused once the account has shifts or audit entries |
| GET | `/payment-methods` | `admin.payment_methods` | methods with payment counts and totals |
| POST | `/payment-methods/new` \| `/<id>/edit` \| `/<id>/delete` | `admin.payment_method_*` | delete refused while payments exist |
| GET/POST | `/shifts/open` | `admin.shift_open` | open a drawer against a register with an opening float |
| POST | `/shifts/<id>/close` | `admin.shift_close` | counted cash, expected cash, variance |
| GET/POST | `/inventory/ingredients/new` \| `/<id>/edit` | `inventory.ingredient_*` | stock item CRUD |
| POST | `/inventory/ingredients/<id>/delete` | `inventory.ingredient_delete` | refused while movements, recipes or receipts reference it |
| GET/POST | `/inventory/recipes/new` \| `/<id>/edit` | `inventory.recipe_*` | recipe and its ingredient lines |
| POST | `/inventory/recipes/<id>/delete` | `inventory.recipe_delete` | removes the lines with it |
| POST | `/pos/quote` | `pos.requote` | re-price the basket after a discount change |
| POST | `/context` | `auth.switch_context` | applies restaurant and branch together; 403 outside scope; JSON for fetch |
| POST | `/branch/<id>` | `auth.switch_branch` | branch in scope, else 403; returns JSON when called with `X-Requested-With: fetch` |
| POST | `/business/<id>` | `auth.switch_business` | business in scope; super admin: any; JSON for fetch |
| GET | `/` | `dashboard.index` | business account |
| GET | `/pos` | `pos.index` | branch |
| POST | `/pos/add` | `pos.add` | branch |
| POST | `/pos/qty` | `pos.set_quantity` | branch |
| POST | `/pos/remove` | `pos.remove` | branch |
| POST | `/pos/clear` | `pos.clear` | branch |
| GET | `/pos/item/<id>` | `pos.configure` | branch, product in business |
| POST | `/pos/checkout` | `pos.checkout` | branch, `order.discount` for a discount |
| GET | `/orders` | `orders.index` | branch |
| GET | `/orders/<id>` | `orders.show` | branch, order in business |
| GET | `/orders/<id>/receipt` | `orders.receipt` | branch |
| POST | `/orders/<id>/receipt/print` | `orders.print_receipt` | branch |
| POST | `/orders/<id>/hold` | `orders.hold` | branch |
| POST | `/orders/<id>/resume` | `orders.resume` | branch |
| POST | `/orders/<id>/cancel` | `orders.cancel` | `order.void` |
| POST | `/orders/<id>/pay` | `orders.pay` | branch |
| POST | `/orders/<id>/refund` | `orders.refund` | `order.refund` |
| GET | `/orders/returns` | `orders.returns` | branch |
| GET | `/kitchen` | `kitchen.index` | branch |
| POST | `/kitchen/<id>/status` | `kitchen.set_status` | `kitchen.update` |
| POST | `/kitchen/items/<id>/status` | `kitchen.set_item_status` | `kitchen.update` |
| GET | `/products` | `catalog.products` | branch |
| GET, POST | `/products/new` | `catalog.product_new` | `menu.manage` |
| GET, POST | `/products/<id>/edit` | `catalog.product_edit` | `menu.manage` |
| POST | `/products/<id>/toggle` | `catalog.product_toggle` | `menu.manage` |
| GET, POST | `/categories` | `catalog.categories` | branch, `menu.manage` to add |
| POST | `/categories/<id>/edit` | `catalog.category_edit` | `menu.manage` |
| GET | `/inventory` | `inventory.index` | any inventory permission |
| GET | `/inventory/movements` | `inventory.movements` | any inventory permission |
| GET, POST | `/inventory/adjust` | `inventory.adjust` | `inventory.adjust` |
| GET | `/inventory/purchases` | `inventory.purchases` | `inventory.purchase` |
| GET, POST | `/inventory/purchases/new` | `inventory.purchase_new` | `inventory.purchase` |
| POST | `/inventory/purchases/<id>/receive` | `inventory.purchase_receive` | `inventory.purchase` |
| GET | `/inventory/transfers` | `inventory.transfers` | `inventory.transfer` |
| GET, POST | `/inventory/transfers/new` | `inventory.transfer_new` | `inventory.transfer` |
| GET | `/reports` | `reports.index` | `report.view` |
| GET | `/reports/api/data` | `reports.api_data` | `report.view`, 403 on a foreign branch/category/payment/supplier/employee, 400 on an unknown section |
| GET | `/reports/api/options` | `reports.api_options` | `report.view` |
| GET | `/restaurants` | `restaurants.index` | any business account; lists only accessible tenants |
| GET | `/restaurants/<id>` | `restaurants.detail` | business in the account's scope, else 403 |
| POST | `/restaurants/open` | `restaurants.open` | switches business and optionally branch, then redirects |
| GET | `/suppliers` | `suppliers.index` | `inventory.purchase` or `report.view` |
| GET, POST | `/suppliers/new` | `suppliers.new` | `inventory.purchase` |
| GET | `/suppliers/<id>` | `suppliers.detail` | same business, else 404 |
| GET, POST | `/suppliers/<id>/edit` | `suppliers.edit` | `inventory.purchase`, same business |
| GET | `/inventory/ingredients` | `inventory.ingredients` | any inventory permission |
| GET | `/inventory/recipes` | `inventory.recipes` | any inventory permission |
| GET | `/audit` | `admin.audit` | `staff.manage` or `business.settings` |
| GET | `/shifts` | `admin.shifts` | `shift.manage` or `staff.manage` |
| GET | `/insights` | `insights.index` | `ai.view` |
| POST | `/insights/refresh` | `insights.refresh` | `ai.view` |
| GET | `/staff` | `admin.staff` | `staff.manage` |
| POST | `/staff/<id>/role` | `admin.staff_role` | `staff.manage` |
| POST | `/staff/<id>/active` | `admin.staff_active` | `staff.manage` |
| GET | `/branches` | `admin.branches` | `branch.manage` |
| POST | `/branches/<id>/edit` | `admin.branch_edit` | `branch.manage` |
| GET, POST | `/settings` | `admin.settings` | `business.settings` or `branch.manage` |
| GET | `/platform` | `platform.index` | platform admin |
| GET | `/platform/integrity` | `platform.integrity` | platform admin |

Every state-changing request also needs the session CSRF token in `_csrf` (forms)
or `X-CSRF-Token` (the till's fetch calls). A missing or stale token returns 400
before any handler runs.

## CRUD coverage by entity group

Legend: **C** create, **R** read, **U** update, **D** delete/retire, **S** written by
a service rather than a form.

### Master data

| Table | App coverage |
| --- | --- |
| `businesses` | C at registration, R on the restaurants page and platform console, R in settings |
| `branches` | C at registration, R, U (name, area, open flag), R on the restaurants page |
| `branch_operating_hours` | R on the restaurants pages, collapsed to a readable line per branch |
| `categories` | C, R, U |
| `products` | C, R, U, D via `is_active` retire |
| `branch_products` | R, U (branch price and availability on the product form) |
| `dining_tables` | R (table picker at checkout) |
| `payment_methods` | C (Cash, Card, Bank Transfer at registration), R at checkout and refund |
| `suppliers` | C, R, U on the suppliers page (no delete: purchase orders reference it) |
| `printers` | R (chosen for a print job) |
| `cash_registers` | not surfaced, see gaps |

### Platform and tenancy

| Table | App coverage |
| --- | --- |
| `roles`, `permissions`, `role_permissions` | R; driven by the permission gates |
| `business_settings` | C at registration, R, U (receipt text, margin floor, negative stock) |
| `business_subscriptions`, `subscription_plans` | C (trial at registration), R (platform console) |
| `branch_operating_hours` | not surfaced, see gaps |
| `tax_rules` | C at registration when a rate is entered, R; the active rule prices every bill |

### Sales

| Table | App coverage |
| --- | --- |
| `restaurant_orders` | C, R, U (status lifecycle only) |
| `order_items` | C, R |
| `order_item_modifiers` | C, R |
| `order_discounts` | C when a discount is applied |
| `order_payments` | C, R |
| `order_status_events` | S on every status change, R on the order page |
| `order_fulfillments` | S at checkout |
| `dining_sessions` | S for dine-in, closed when the bill is paid |
| `receipt_records` | S on full payment, R on the receipt page |
| `kitchen_tickets`, `kitchen_ticket_items` | S at checkout, R and U on the board |
| `menu_modifier_groups`, `menu_modifier_options` | R at the till |

### Inventory and purchasing

| Table | App coverage |
| --- | --- |
| `inventory_items` | R |
| `branch_stocks` | R; quantity changes only through a movement |
| `stock_movements` | C, R (ledger) |
| `stock_adjustments` | C with a matching movement |
| `supplier_purchase_orders` | C, R, U (`ordered` to `received`) |
| `supplier_purchase_items` | C, R |
| `goods_receipts`, `goods_receipt_items` | C on receive |
| `stock_transfer_requests`, `stock_transfer_items`, `stock_transfer_events` | C on transfer |
| `stock_batches` | not surfaced, see gaps |
| `recipes`, `recipe_lines` | R on the recipes page; they decide what a paid sale consumes |

### Operations

| Table | App coverage |
| --- | --- |
| `sales_returns`, `sales_return_lines` | C, R |
| `print_jobs` | C when a print is recorded |
| `audit_events` | S on every important action |
| `product_barcodes` | R by the barcode field |
| `printer_issue_reports` | not surfaced, see gaps |
| `scanner_sessions` | not surfaced, see gaps |
| `cashier_shifts`, `cash_movements`, `shift_reconciliations` | not surfaced, see gaps |
| `discount_approvals` | not surfaced; a discount needs `order.discount` outright |

### Intelligence

| Table | App coverage |
| --- | --- |
| `dataset_manifests` | R (platform console) |
| `ai_analysis_runs` | C through the Insights refresh, R on the Insights page |
| `product_performance_snapshots` | S during a refresh, R on the Insights page |
| `ai_recommendations` | S during a refresh, R on the Insights page |
| `recommendation_feedback` | not surfaced; no feedback form yet |

The Insights page calls `analytics.refresh_snapshots()`, which is idempotent: a
second run returns the existing run rather than duplicating rows. It is labelled
`deterministic_sql` and every recommendation is `rule_engine`. No language model is
called anywhere in the request path.

## Deliberate restrictions

- A paid order cannot be cancelled. It is refunded, which writes a posted
  `sales_returns` row and restocks only what the order consumed.
- A second full payment is refused by `capture_payment` before it reaches SQL.
- A receipt is issued once; a repeat call returns the existing row.
- Stock can only change through `apply_stock_delta`, which writes the movement and
  the balance in one transaction.
- Refunds restock through `assert_consumption_exists`, so an item is never added
  back if the sale never took it.
- Nothing is hard-deleted. Products retire, documents are voided or reversed.

## Known gaps

These exist in the schema and are intentionally not exposed, rather than shown as
broken screens:

- **Shift open/close and cash counting** (`cashier_shifts`, `cash_movements`,
  `shift_reconciliations`, `cash_registers`). `/shifts` lists every shift with its
  float, counted cash and variance, but a cashier cannot open or close a shift from
  this application yet.
- **Branch opening hours editing** (`branch_operating_hours`). Hours are displayed on
  the restaurants pages; there is no editor for them.
- **Stock batches and expiry** (`stock_batches`). Received stock is not tracked by
  batch, so expiry is not reported.
- **Discount approval queue** (`discount_approvals`). A discount is currently gated
  by permission instead of a manager approval request.
- **Printer issue reports** (`printer_issue_reports`). The receipt page records a
  print job but has no failure report form.
- **Scanner pairing** (`scanner_sessions`). Barcode entry works as a keyboard-wedge
  field; no camera pairing is claimed.
- **Station routing** (`kitchen_stations`, `product_station_routes`). One kitchen
  ticket is raised per order instead of splitting by station.
- **Supplier deletion**. A supplier can be created and edited, never deleted, because
  purchase orders reference it. Retire by renaming or by adding a note is not
  implemented either.
- **AI narration** (`ai_analysis_runs`, `ai_recommendations`). The Insights page
  shows stored deterministic figures and rule-engine recommendations. No language
  model produces text at runtime, and the schema only permits `deterministic_sql`
  or `rule_engine` in `ai_analysis_runs.engine`, so a model-written run would need
  a reviewed migration before it could be stored.
