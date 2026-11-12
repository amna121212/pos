# Database dictionary

The POS uses one PostgreSQL database, `retail_pos_db`.
A business is a tenant. A branch belongs to that business.
Money is `NUMERIC` and timezone-aware timestamps are stored in UTC.
Display times in Asia/Karachi.

Posted sales, payments, receipts, returns and stock movements are not hard-deleted.
The application voids, reverses or deactivates them instead.
Foreign keys use `ON DELETE RESTRICT`, so a parent with children cannot be removed.

Application tables: 65.

## `ai_analysis_runs`

One deterministic snapshot pass. Grok is not called here.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| run_code | VARCHAR(60) | False |
| engine | VARCHAR(40) | False |
| dataset_code | VARCHAR(60) | False |
| period_start | DATE | False |
| period_end | DATE | False |
| status | VARCHAR(20) | False |
| summary | VARCHAR(400) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- business_id -> businesses(id)

## `ai_recommendations`

Rule-written suggestions. They explain stored figures; they do not invent them.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| run_id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | True |
| product_id | INTEGER | True |
| source | VARCHAR(40) | False |
| recommendation_code | VARCHAR(40) | False |
| title | VARCHAR(140) | False |
| detail | VARCHAR(400) | False |
| priority | VARCHAR(10) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- product_id -> products(id)
- run_id -> ai_analysis_runs(id)

## `audit_events`

Append-only note of a meaningful action.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | True |
| branch_id | INTEGER | True |
| actor_user_id | INTEGER | True |
| action | VARCHAR(40) | False |
| entity_type | VARCHAR(40) | False |
| entity_id | VARCHAR(40) | True |
| message | VARCHAR(300) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- actor_user_id -> users(id)
- branch_id -> branches(id)
- business_id -> businesses(id)

## `branch_operating_hours`

Opening hours for each weekday. Stored as local times, not as sales.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| branch_id | INTEGER | False |
| weekday | INTEGER | False |
| opens_at | TIME | False |
| closes_at | TIME | False |
| is_closed | BOOLEAN | False |

Foreign keys:
- branch_id -> branches(id)

## `branch_products`

Branch price and availability for a product defined by the parent business.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| product_id | INTEGER | False |
| sale_price | NUMERIC(12, 2) | False |
| is_available | BOOLEAN | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- product_id -> products(id)

## `branch_stocks`

Current on-hand quantity. It must match the sum of stock movements.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| item_id | INTEGER | False |
| quantity | NUMERIC(14, 3) | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- item_id -> inventory_items(id)

## `branches`

A selling location owned by one business. Staff, stock and prices can differ here.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| code | VARCHAR(20) | False |
| name | VARCHAR(120) | False |
| area | VARCHAR(100) | False |
| city | VARCHAR(80) | False |
| is_active | BOOLEAN | False |

Foreign keys:
- business_id -> businesses(id)

## `business_settings`

Currency, Pakistan timezone, fictional trading start and margin floor.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| currency_code | VARCHAR(3) | False |
| timezone_name | VARCHAR(64) | False |
| trading_since | DATE | False |
| receipt_header | VARCHAR(160) | False |
| receipt_footer | VARCHAR(240) | False |
| allow_negative_stock | BOOLEAN | False |
| min_gross_margin_pct | NUMERIC(5, 2) | False |
| created_at | TIMESTAMP | False |
| updated_at | TIMESTAMP | False |

Foreign keys:
- business_id -> businesses(id)

## `business_subscriptions`

The current plan for one business. Changing it updates this row.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| plan_id | INTEGER | False |
| status | VARCHAR(20) | False |
| started_on | DATE | False |
| notes | VARCHAR(240) | True |
| created_at | TIMESTAMP | False |
| updated_at | TIMESTAMP | False |

Foreign keys:
- business_id -> businesses(id)
- plan_id -> subscription_plans(id)

## `business_users`

Grants a user a role at a business, optionally limited to one branch.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| user_id | INTEGER | False |
| branch_id | INTEGER | True |
| role | VARCHAR(20) | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- user_id -> users(id)

## `businesses`

A tenant on the POS platform. One restaurant or shop, not one database.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| name | VARCHAR(140) | False |
| slug | VARCHAR(100) | False |
| business_type | VARCHAR(25) | False |
| city | VARCHAR(80) | False |
| is_demo | BOOLEAN | False |
| created_at | TIMESTAMP | False |

## `cash_movements`

Cash in or out of a shift. The amount is always positive; the type gives the direction.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| shift_id | INTEGER | False |
| business_id | INTEGER | False |
| movement_type | VARCHAR(24) | False |
| amount | NUMERIC(12, 2) | False |
| reference_code | VARCHAR(80) | False |
| note | VARCHAR(160) | True |
| created_at | TIMESTAMP | False |

Foreign keys:
- business_id -> businesses(id)
- shift_id -> cashier_shifts(id)

## `cash_registers`

A counter drawer at a branch.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| branch_id | INTEGER | False |
| code | VARCHAR(30) | False |
| label | VARCHAR(80) | False |

Foreign keys:
- branch_id -> branches(id)

## `cashier_shifts`

One cashier session on one register, with an opening float.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| register_id | INTEGER | False |
| user_id | INTEGER | False |
| shift_code | VARCHAR(40) | False |
| status | VARCHAR(20) | False |
| opening_float | NUMERIC(12, 2) | False |
| opened_at | TIMESTAMP | False |
| closed_at | TIMESTAMP | True |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- register_id -> cash_registers(id)
- user_id -> users(id)

## `categories`

Menu or shelf grouping inside one business.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| name | VARCHAR(100) | False |

Foreign keys:
- business_id -> businesses(id)

## `dataset_manifests`

Where a dataset came from: curated, generated or synthetic history.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| code | VARCHAR(60) | False |
| category | VARCHAR(40) | False |
| title | VARCHAR(140) | False |
| description | TEXT | False |
| source_note | TEXT | False |
| status | VARCHAR(20) | False |
| generated_at | TIMESTAMP | False |

## `dining_sessions`

A seating at one table. Several orders could share it; this demo uses one.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| dining_table_id | INTEGER | False |
| guest_count | INTEGER | False |
| opened_at | TIMESTAMP | False |
| closed_at | TIMESTAMP | True |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- dining_table_id -> dining_tables(id)

## `dining_tables`

A physical table at a restaurant branch.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| branch_id | INTEGER | False |
| table_number | VARCHAR(20) | False |
| capacity | INTEGER | False |

Foreign keys:
- branch_id -> branches(id)

## `discount_approvals`

Manager approval or rejection of a discount. Rejected amounts are not applied.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| order_id | INTEGER | False |
| requested_by_user_id | INTEGER | False |
| approved_by_user_id | INTEGER | True |
| discount_kind | VARCHAR(20) | False |
| requested_amount | NUMERIC(12, 2) | False |
| status | VARCHAR(20) | False |
| reason | VARCHAR(160) | False |
| created_at | TIMESTAMP | False |
| decided_at | TIMESTAMP | True |

Foreign keys:
- approved_by_user_id -> users(id)
- business_id -> businesses(id)
- order_id -> restaurant_orders(id)
- requested_by_user_id -> users(id)

## `goods_receipt_items`

How much of each purchase line was received.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| goods_receipt_id | INTEGER | False |
| purchase_item_id | INTEGER | False |
| quantity | NUMERIC(14, 3) | False |

Foreign keys:
- goods_receipt_id -> goods_receipts(id)
- purchase_item_id -> supplier_purchase_items(id)

## `goods_receipts`

Proof that a purchase was received at a branch.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| purchase_order_id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| receipt_number | VARCHAR(65) | False |
| received_at | TIMESTAMP | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- purchase_order_id -> supplier_purchase_orders(id)

## `inventory_items`

A stocked ingredient or retail unit. Restaurant plates are not stocked here.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| product_id | INTEGER | True |
| sku | VARCHAR(48) | False |
| name | VARCHAR(130) | False |
| unit | VARCHAR(24) | False |
| reorder_level | NUMERIC(14, 3) | False |
| standard_cost | NUMERIC(12, 2) | False |

Foreign keys:
- business_id -> businesses(id)
- product_id -> products(id)

## `kitchen_stations`

A prep area in a branch, such as the grill or the pizza oven.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| code | VARCHAR(20) | False |
| name | VARCHAR(80) | False |
| printer_id | INTEGER | True |
| is_active | BOOLEAN | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- printer_id -> printers(id)

## `kitchen_ticket_items`

Preparation status for one order line on a kitchen ticket.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| kitchen_ticket_id | INTEGER | False |
| order_item_id | INTEGER | False |
| status | VARCHAR(20) | False |

Foreign keys:
- kitchen_ticket_id -> kitchen_tickets(id)
- order_item_id -> order_items(id)

## `kitchen_tickets`

The kitchen copy of a paid restaurant ticket.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_id | INTEGER | False |
| printer_id | INTEGER | True |
| ticket_number | VARCHAR(50) | False |
| status | VARCHAR(20) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- order_id -> restaurant_orders(id)
- printer_id -> printers(id)

## `menu_modifier_groups`

An optional choice group such as spice level or burger add-ons.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| product_id | INTEGER | False |
| name | VARCHAR(100) | False |
| is_required | BOOLEAN | False |

Foreign keys:
- business_id -> businesses(id)
- product_id -> products(id)

## `menu_modifier_options`

One choice inside a modifier group, with an extra price.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| group_id | INTEGER | False |
| name | VARCHAR(100) | False |
| extra_price | NUMERIC(12, 2) | False |

Foreign keys:
- group_id -> menu_modifier_groups(id)

## `order_discounts`

A discount amount that was actually applied to a ticket.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_id | INTEGER | False |
| label | VARCHAR(80) | False |
| amount | NUMERIC(12, 2) | False |

Foreign keys:
- order_id -> restaurant_orders(id)

## `order_fulfillments`

How the guest receives the ticket: table, counter, takeaway or a synthetic delivery drop.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_id | INTEGER | False |
| fulfillment_type | VARCHAR(20) | False |
| contact_label | VARCHAR(80) | False |
| area | VARCHAR(100) | False |
| notes | VARCHAR(200) | True |

Foreign keys:
- order_id -> restaurant_orders(id)

## `order_item_modifiers`

The choice actually taken on a line, priced at the time of sale.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_item_id | INTEGER | False |
| option_id | INTEGER | False |
| price_at_sale | NUMERIC(12, 2) | False |

Foreign keys:
- option_id -> menu_modifier_options(id)
- order_item_id -> order_items(id)

## `order_items`

One sold product line. unit_price is the branch price captured at sale time.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_id | INTEGER | False |
| product_id | INTEGER | False |
| quantity | INTEGER | False |
| unit_price | NUMERIC(12, 2) | False |
| line_total | NUMERIC(12, 2) | False |
| note | VARCHAR(150) | True |

Foreign keys:
- order_id -> restaurant_orders(id)
- product_id -> products(id)

## `order_payments`

A captured tender. Split payments are several rows. The sum cannot exceed the grand total.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_id | INTEGER | False |
| payment_method_id | INTEGER | False |
| amount | NUMERIC(12, 2) | False |
| status | VARCHAR(20) | False |
| paid_at | TIMESTAMP | False |

Foreign keys:
- order_id -> restaurant_orders(id)
- payment_method_id -> payment_methods(id)

## `order_status_events`

Status history. Cancelled tickets stay in this history.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_id | INTEGER | False |
| old_status | VARCHAR(24) | True |
| new_status | VARCHAR(24) | False |
| message | VARCHAR(200) | True |
| created_at | TIMESTAMP | False |

Foreign keys:
- order_id -> restaurant_orders(id)

## `payment_methods`

Cash, card or transfer offered by one business.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| code | VARCHAR(30) | False |
| label | VARCHAR(70) | False |
| enabled | BOOLEAN | False |

Foreign keys:
- business_id -> businesses(id)

## `permissions`

An action the server may allow, such as order.refund.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| code | VARCHAR(60) | False |
| label | VARCHAR(120) | False |
| description | VARCHAR(240) | False |

## `print_jobs`

A receipt, kitchen or barcode print, with retry attempts.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| printer_id | INTEGER | True |
| job_type | VARCHAR(20) | False |
| status | VARCHAR(20) | False |
| attempt_count | INTEGER | False |
| last_error | VARCHAR(200) | True |
| idempotency_key | VARCHAR(80) | False |
| related_receipt_id | INTEGER | True |
| related_ticket_id | INTEGER | True |
| created_at | TIMESTAMP | False |
| updated_at | TIMESTAMP | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- printer_id -> printers(id)
- related_receipt_id -> receipt_records(id)
- related_ticket_id -> kitchen_tickets(id)

## `printer_issue_reports`

A paper-out or other printer problem linked to a job when one exists.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| printer_id | INTEGER | False |
| print_job_id | INTEGER | True |
| reported_by_user_id | INTEGER | True |
| issue_code | VARCHAR(40) | False |
| description | VARCHAR(200) | False |
| status | VARCHAR(20) | False |
| created_at | TIMESTAMP | False |
| resolved_at | TIMESTAMP | True |

Foreign keys:
- print_job_id -> print_jobs(id)
- printer_id -> printers(id)
- reported_by_user_id -> users(id)

## `printers`

Receipt, kitchen or label printer configured at a branch, including 58mm and 80mm widths.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| branch_id | INTEGER | False |
| label | VARCHAR(90) | False |
| purpose | VARCHAR(20) | False |
| connection_type | VARCHAR(20) | False |
| paper_width_mm | INTEGER | True |

Foreign keys:
- branch_id -> branches(id)

## `product_barcodes`

Synthetic internal barcode. These are not GS1 registrations.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| product_id | INTEGER | False |
| barcode | VARCHAR(32) | False |
| symbology | VARCHAR(20) | False |
| is_primary | BOOLEAN | False |

Foreign keys:
- business_id -> businesses(id)
- product_id -> products(id)

## `product_performance_snapshots`

Branch product quantity, revenue and estimated gross profit for a run.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| run_id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| product_id | INTEGER | False |
| period_start | DATE | False |
| period_end | DATE | False |
| qty_sold | NUMERIC(14, 3) | False |
| revenue | NUMERIC(14, 2) | False |
| estimated_cost | NUMERIC(14, 2) | False |
| estimated_gross_profit | NUMERIC(14, 2) | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- product_id -> products(id)
- run_id -> ai_analysis_runs(id)

## `product_station_routes`

Which station cooks a product at a branch.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| product_id | INTEGER | False |
| station_id | INTEGER | False |

Foreign keys:
- station_id, branch_id -> kitchen_stations(id, branch_id)
- branch_id -> branches(id)
- business_id -> businesses(id)
- product_id -> products(id)

## `products`

A sellable menu item or retail SKU. It is not the same thing as a raw ingredient.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| category_id | INTEGER | False |
| sku | VARCHAR(35) | False |
| name | VARCHAR(130) | False |
| kind | VARCHAR(20) | False |
| base_cost | NUMERIC(12, 2) | False |
| is_active | BOOLEAN | False |

Foreign keys:
- business_id -> businesses(id)
- category_id -> categories(id)

## `receipt_records`

One receipt per paid ticket. Finalising it again returns the same row.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| order_id | INTEGER | False |
| printer_id | INTEGER | True |
| receipt_number | VARCHAR(50) | False |
| print_status | VARCHAR(20) | False |
| issued_at | TIMESTAMP | False |

Foreign keys:
- order_id -> restaurant_orders(id)
- printer_id -> printers(id)

## `recipe_lines`

Ingredient quantity for one recipe, in the ingredient's stock unit.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| recipe_id | INTEGER | False |
| inventory_item_id | INTEGER | False |
| quantity | NUMERIC(14, 3) | False |
| unit | VARCHAR(24) | False |

Foreign keys:
- inventory_item_id -> inventory_items(id)
- recipe_id -> recipes(id)

## `recipes`

How one serving of a menu product is made from ingredients.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| product_id | INTEGER | False |
| name | VARCHAR(140) | False |
| yield_qty | NUMERIC(10, 3) | False |
| notes | VARCHAR(240) | True |
| is_active | BOOLEAN | False |

Foreign keys:
- business_id -> businesses(id)
- product_id -> products(id)

## `recommendation_feedback`

A person's response to a stored recommendation.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| recommendation_id | INTEGER | False |
| user_id | INTEGER | True |
| decision | VARCHAR(20) | False |
| note | VARCHAR(240) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- recommendation_id -> ai_recommendations(id)
- user_id -> users(id)

## `restaurant_orders`

A ticket: dine-in, takeaway, counter pickup or delivery. Posted totals are not deleted.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| dining_session_id | INTEGER | True |
| order_number | VARCHAR(45) | False |
| order_type | VARCHAR(20) | False |
| status | VARCHAR(24) | False |
| subtotal | NUMERIC(12, 2) | False |
| discount_total | NUMERIC(12, 2) | False |
| tax_total | NUMERIC(12, 2) | False |
| grand_total | NUMERIC(12, 2) | False |
| created_at | TIMESTAMP | False |
| tax_rule_id | INTEGER | True |
| cashier_shift_id | INTEGER | True |
| dataset_code | VARCHAR(40) | True |

Foreign keys:
- cashier_shift_id -> cashier_shifts(id)
- tax_rule_id -> tax_rules(id)
- branch_id -> branches(id)
- business_id -> businesses(id)
- dining_session_id -> dining_sessions(id)

## `role_permissions`

Which permissions a role has.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| role_id | INTEGER | False |
| permission_id | INTEGER | False |

Foreign keys:
- permission_id -> permissions(id)
- role_id -> roles(id)

## `roles`

Named roles: platform admin, owner, manager, cashier, kitchen, inventory.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| code | VARCHAR(40) | False |
| label | VARCHAR(80) | False |
| scope | VARCHAR(20) | False |

## `sales_return_lines`

The returned line and, for an exchange, the replacement product.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| sales_return_id | INTEGER | False |
| order_item_id | INTEGER | False |
| quantity | INTEGER | False |
| amount | NUMERIC(12, 2) | False |
| replacement_product_id | INTEGER | True |

Foreign keys:
- order_item_id -> order_items(id)
- replacement_product_id -> products(id)
- sales_return_id -> sales_returns(id)

## `sales_returns`

A posted refund or even exchange. Void it instead of deleting it.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| order_id | INTEGER | False |
| return_number | VARCHAR(50) | False |
| return_type | VARCHAR(20) | False |
| status | VARCHAR(20) | False |
| reason | VARCHAR(160) | False |
| refund_amount | NUMERIC(12, 2) | False |
| balance_due | NUMERIC(12, 2) | False |
| payment_method_id | INTEGER | True |
| created_at | TIMESTAMP | False |
| posted_at | TIMESTAMP | True |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- order_id -> restaurant_orders(id)
- payment_method_id -> payment_methods(id)

## `scanner_sessions`

A paired camera or USB keyboard-wedge session at a branch.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| user_id | INTEGER | False |
| session_code | VARCHAR(40) | False |
| device_label | VARCHAR(80) | False |
| mode | VARCHAR(20) | False |
| status | VARCHAR(20) | False |
| started_at | TIMESTAMP | False |
| ended_at | TIMESTAMP | True |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- user_id -> users(id)

## `shift_reconciliations`

Counted cash compared with the shift ledger. Variance is kept, not deleted.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| shift_id | INTEGER | False |
| expected_cash | NUMERIC(12, 2) | False |
| counted_cash | NUMERIC(12, 2) | False |
| variance | NUMERIC(12, 2) | False |
| note | VARCHAR(200) | True |
| reconciled_at | TIMESTAMP | False |

Foreign keys:
- shift_id -> cashier_shifts(id)

## `stock_adjustments`

A counted correction. The ledger row uses the same adjustment code.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| item_id | INTEGER | False |
| adjustment_code | VARCHAR(60) | False |
| delta_qty | NUMERIC(14, 3) | False |
| reason | VARCHAR(150) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- item_id -> inventory_items(id)

## `stock_batches`

A received batch, with an expiry date when the ingredient has a demo shelf life.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| item_id | INTEGER | False |
| batch_number | VARCHAR(65) | False |
| received_qty | NUMERIC(14, 3) | False |
| expiry_date | DATE | True |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- item_id -> inventory_items(id)

## `stock_movements`

The stock ledger. Quantity changes only by inserting a movement.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| item_id | INTEGER | False |
| movement_type | VARCHAR(24) | False |
| delta_qty | NUMERIC(14, 3) | False |
| reference_code | VARCHAR(75) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- item_id -> inventory_items(id)

## `stock_transfer_events`

Requested, approved, dispatched and received notes for a transfer.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| transfer_id | INTEGER | False |
| status | VARCHAR(20) | False |
| note | VARCHAR(200) | True |
| created_at | TIMESTAMP | False |

Foreign keys:
- transfer_id -> stock_transfer_requests(id)

## `stock_transfer_items`

The quantity of one item on a transfer.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| transfer_id | INTEGER | False |
| item_id | INTEGER | False |
| quantity | NUMERIC(14, 3) | False |

Foreign keys:
- item_id -> inventory_items(id)
- transfer_id -> stock_transfer_requests(id)

## `stock_transfer_requests`

A move between two branches of the same business.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| from_branch_id | INTEGER | False |
| to_branch_id | INTEGER | False |
| transfer_number | VARCHAR(65) | False |
| status | VARCHAR(20) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- business_id -> businesses(id)
- from_branch_id -> branches(id)
- to_branch_id -> branches(id)

## `subscription_plans`

Platform plan with a coursework monthly fee in PKR.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| code | VARCHAR(40) | False |
| name | VARCHAR(80) | False |
| monthly_fee_pkr | NUMERIC(12, 2) | False |
| max_branches | INTEGER | False |
| description | VARCHAR(240) | False |
| is_active | BOOLEAN | False |

## `supplier_purchase_items`

A line on a purchase order: item, quantity and unit cost.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| purchase_order_id | INTEGER | False |
| item_id | INTEGER | False |
| qty_ordered | NUMERIC(14, 3) | False |
| unit_cost | NUMERIC(12, 2) | False |

Foreign keys:
- item_id -> inventory_items(id)
- purchase_order_id -> supplier_purchase_orders(id)

## `supplier_purchase_orders`

An order placed with a supplier for one receiving branch.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| branch_id | INTEGER | False |
| supplier_id | INTEGER | False |
| po_number | VARCHAR(60) | False |
| status | VARCHAR(20) | False |
| created_at | TIMESTAMP | False |

Foreign keys:
- branch_id -> branches(id)
- business_id -> businesses(id)
- supplier_id -> suppliers(id)

## `suppliers`

A fictional supplier account used for purchases and lead time.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| name | VARCHAR(130) | False |
| city | VARCHAR(80) | False |
| lead_time_days | INTEGER | False |
| is_synthetic | BOOLEAN | False |

Foreign keys:
- business_id -> businesses(id)

## `tax_rules`

Illustrative tax rate. Not an FBR or PRA quotation.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| business_id | INTEGER | False |
| code | VARCHAR(40) | False |
| label | VARCHAR(120) | False |
| rate_percent | NUMERIC(6, 3) | False |
| applies_to | VARCHAR(20) | False |
| is_active | BOOLEAN | False |
| is_demo_rate | BOOLEAN | False |
| notes | VARCHAR(300) | False |

Foreign keys:
- business_id -> businesses(id)

## `users`

A person who can sign in. Demo people are marked synthetic and use example.invalid.

| Column | Type | Nullable |
| --- | --- | --- |
| id | INTEGER | False |
| display_name | VARCHAR(100) | False |
| email | VARCHAR(150) | False |
| password_hash | VARCHAR(255) | False |
| is_active | BOOLEAN | False |
| is_platform_admin | BOOLEAN | False |
| employee_code | VARCHAR(40) | True |
| is_synthetic | BOOLEAN | False |
