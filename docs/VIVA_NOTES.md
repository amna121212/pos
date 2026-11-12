# Viva notes for the database phase

Use these notes to explain the schema. Do not describe the synthetic history as real sales.

## 1. A business owns its branches

`businesses` is the tenant. `branches.business_id` points at it. Lahore Grill House has Johar Town and DHA. The owner membership has a null `branch_id`, so it is business-wide. A cashier membership stores one `branch_id`.

## 2. Each restaurant keeps its own menu and prices

`categories` and `products` belong to a business. `branch_products` stores the price and whether the item is available at a branch. The second demo branch is PKR 20 higher. That difference is a coursework choice.

An order line copies `unit_price` onto `order_items`. Later price edits do not rewrite old tickets.

## 3. Orders connect to the kitchen and to payments

`restaurant_orders` can be dine-in, takeaway, counter pickup or delivery. Dine-in can point at a `dining_sessions` row and a table. Paid restaurant tickets get a `kitchen_tickets` row and `kitchen_ticket_items`. `product_station_routes` says which station should cook the item.

`order_payments` can be split. For a status of `paid`, the captured payments equal `grand_total`. Cancelled and held tickets have no payments. A receipt is one `receipt_records` row. Calling finalise again returns that same row.

## 4. Ingredients, recipes and stock

A chicken karahi is a product. Chicken, tomato and oil are inventory items. `recipes` and `recipe_lines` say how much of each ingredient one serving uses. When the order becomes paid, the service posts `recipe_consumption` movements and lowers `branch_stocks`. The movement reference is `HCONS-` plus the order number, so a repeat call does not deduct twice.

Retail items at Daily Mart are different. The inventory row points at the product, and a sale posts `retail_sale` for the number of pieces. A finished plate is never stored as if it were the raw ingredient.

## 5. Purchases and transfers

A supplier purchase is received through `goods_receipts`. The receipt posts `purchase_receipt` movements. A transfer posts `transfer_out` at the source and `transfer_in` at the destination for the same quantity. Both branches must belong to the same business. The sum of those two movements is zero.

`branch_stocks.quantity` must equal the sum of `stock_movements` for that branch and item. Adjustments and refunds are also movements (`stock_adjustment`, `return_restock`).

## 6. Why the history can support a later AI explanation

`SYNTHETIC_HISTORY_V1` is a labelled simulation from May 2025 through October 2026. Snapshots in `product_performance_snapshots` are SQL totals: quantity, net revenue and estimated cost. `ai_recommendations` rows say `source = rule_engine`. A later Grok feature should explain these stored numbers. It should not invent totals or run arbitrary SQL.

Cancelled orders are excluded from paid sales. Refunds reduce the snapshot quantity and the ex-tax line amount. Tax is not treated as revenue.

## 7. Flask, SQLAlchemy and foreign keys

Models live under `app/`. `create_app()` registers them and points at `retail_pos_db`. Alembic migrations in `migrations/versions/` create the tables. Seeds use the models, not hand-written inserts for each row.

`ON DELETE RESTRICT` means a posted business cannot be deleted while branches and orders exist. That is the Delete behaviour for posted data: the database refuses the delete, and the service cancels, voids or reverses instead.

## Time and money

Timestamps are `timestamptz` in UTC. Build a Lahore local time with `Asia/Karachi` and store that instant. Pakistan has no daylight saving.

Money uses `Numeric(12, 2)` and Python `Decimal`. Do not use `float` for rupees.

## Security points worth saying

- Restaurant A cannot pay or transfer Restaurant B's records. The service checks `business_id`, and triggers repeat the check for orders, lines, branch prices and transfers.
- Passwords in the demo are random hashes. There is no password in the source.
- The database listens on 127.0.0.1 only. Use an SSH tunnel from a laptop. Do not open port 5432 to the internet.
- ParkSphere uses a different database and user. This project never connects to it.
