# Major relationships

There are 65 application tables. The diagrams below show the relationships a student is expected to explain. Column lists are in `DATABASE_DICTIONARY.md`.

## Tenant and access

```mermaid
erDiagram
  businesses ||--o{ branches : owns
  businesses ||--o{ business_users : employs
  users ||--o{ business_users : joins
  branches ||--o{ business_users : limits
  businesses ||--|| business_settings : configures
  businesses ||--|| business_subscriptions : subscribes
  subscription_plans ||--o{ business_subscriptions : offers
  roles ||--o{ role_permissions : grants
  permissions ||--o{ role_permissions : allows
  businesses ||--o{ tax_rules : defines
  branches ||--o{ branch_operating_hours : opens
```

## Menu, recipe and kitchen

```mermaid
erDiagram
  businesses ||--o{ categories : groups
  categories ||--o{ products : contains
  products ||--o{ branch_products : priced_at
  branches ||--o{ branch_products : sells
  products ||--o| recipes : made_by
  recipes ||--o{ recipe_lines : uses
  inventory_items ||--o{ recipe_lines : consumed_as
  branches ||--o{ kitchen_stations : has
  products ||--o{ product_station_routes : routed
  kitchen_stations ||--o{ product_station_routes : cooks
  products ||--o{ menu_modifier_groups : offers
  menu_modifier_groups ||--o{ menu_modifier_options : contains
```

## Orders, kitchen, payment and cash

```mermaid
erDiagram
  branches ||--o{ restaurant_orders : rings
  dining_sessions ||--o{ restaurant_orders : seats
  restaurant_orders ||--o{ order_items : contains
  products ||--o{ order_items : sold_as
  order_items ||--o{ order_item_modifiers : customises
  restaurant_orders ||--o{ order_payments : tendered_by
  restaurant_orders ||--o| receipt_records : prints
  restaurant_orders ||--o{ kitchen_tickets : sends
  kitchen_tickets ||--o{ kitchen_ticket_items : lists
  restaurant_orders ||--o| order_fulfillments : handed_over
  restaurant_orders ||--o{ sales_returns : reversed_by
  cashier_shifts ||--o{ restaurant_orders : rung_during
  cashier_shifts ||--o{ cash_movements : moves
  cashier_shifts ||--o| shift_reconciliations : counted_in
```

## Stock

```mermaid
erDiagram
  inventory_items ||--o{ branch_stocks : stored_as
  branches ||--o{ branch_stocks : holds
  inventory_items ||--o{ stock_movements : ledger
  supplier_purchase_orders ||--o{ supplier_purchase_items : orders
  supplier_purchase_orders ||--o{ goods_receipts : received_by
  goods_receipts ||--o{ goods_receipt_items : counts
  stock_transfer_requests ||--o{ stock_transfer_items : moves
  stock_transfer_requests ||--o{ stock_transfer_events : tracks
```

A finished plate is a `products` row. Flour and chicken are `inventory_items`. `recipe_lines` connects them. Paying an order posts `recipe_consumption` movements once. Repeating the same order reference does not deduct again.

Transfers are allowed only when both branches belong to the transfer's business. The database trigger `trg_pos_transfer_business` enforces that, and the service checks it before writing.
