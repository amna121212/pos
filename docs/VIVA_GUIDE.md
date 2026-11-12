# Viva guide

A short, honest explanation of what was built and how to defend it.

## The one-paragraph answer

It is a Flask application over a PostgreSQL database that already held a
multi-branch POS schema. The web layer adds sign-in with roles, a till that prices
and pays orders, printable receipts, a kitchen board, stock and purchasing flows,
and reports calculated in SQL. Business rules live in `app/services/`, views only
orchestrate, and every query is scoped to the signed-in business and its branches.

## Architecture in four layers

1. **Models** (`app/models.py` and the five sibling modules) — 65 SQLAlchemy models
   over 65 tables. `app/models.py` imports the others at the end so all models land
   on one metadata for Alembic.
2. **Services** (`app/services/`) — the only place that changes an order, a payment
   or a stock balance. `orders.py` prices and settles, `recipes.py` consumes
   ingredients, `inventory.py` moves stock, `returns.py` reverses a sale,
   `tenancy.py` refuses a row from another business.
3. **Views** (`app/blueprints/`) — nine blueprints. They read the form, call a
   service, translate an exception into a flash message, and redirect. They never
   compute a total.
4. **Templates** (`app/templates/`) — one `base.html`, one folder per area, about
   200 lines of CSS and one 90-line script for the till.

Why this split: a total that is computed in three places will eventually disagree
with itself. Keeping it in `order_totals()` means the cart, the order page and the
receipt cannot diverge.

## The cashier-to-receipt workflow

1. **Sign in.** `POST /login` compares an email with `users.email`, checks the
   password with `check_password_hash`, then clears the session and stores only the
   user id. Everything else is rebuilt per request, so a disabled account loses
   access immediately.
2. **Pick a branch.** The session branch is validated against the user's
   `business_users` row. A manager or cashier with `branch_id` set can only work
   that branch; an owner has no branch and may switch.
3. **Build the basket.** `POST /pos/add` stores `(product_id, quantity, option
   ids)` in the signed session. Prices are *not* stored. On every render
   `price_lines()` re-reads `branch_products.sale_price` and the modifier extras, so
   a stale page or an edited cookie cannot change what is charged.
4. **Checkout.** `create_order()` does the work in one transaction:
   - prices the basket, computes discount, tax from the active `tax_rules` row, and
     the grand total with `Decimal` arithmetic;
   - inserts `restaurant_orders`, then one `order_items` row per line and
     `order_item_modifiers` for the chosen options;
   - writes `order_fulfillments`, an `order_status_events` row, and `order_discounts`
     when a discount was applied;
   - raises a `kitchen_tickets` row plus `kitchen_ticket_items` for a restaurant;
   - captures the payment through `capture_payment()`, which refuses a second full
     payment or an overpayment;
   - when the captured total equals the grand total, sets the status to `paid`,
     calls `post_recipe_consumption()`, and issues the receipt through
     `finalize_receipt()`.
5. **Receipt.** `GET /orders/<id>/receipt` renders an 80 mm sheet from stored line
   prices and `business_settings.receipt_header/footer`. `window.print()` produces
   the paper copy. "Record print job" writes a `print_jobs` row, which is a record of
   intent, not a claim that a printer responded.

## How stock updates

A sale never edits `branch_stocks.quantity` directly. `apply_stock_delta()`:

1. rejects a zero delta,
2. confirms the branch and item belong to the acting business,
3. returns the existing movement if the same `(branch, item, type, reference)`
   is already recorded — that is the idempotency guard,
4. locks the `branch_stocks` row with `SELECT ... FOR UPDATE`,
5. refuses to go negative unless `business_settings.allow_negative_stock` is true,
6. writes the new balance and a `stock_movements` row together.

For a paid order, `post_recipe_consumption()` reads `recipes`/`recipe_lines` and
deducts the ingredients, using the reference `HCONS-<order_number>`. Retail items
without a recipe deduct the linked unit as `retail_sale`. Calling it twice returns
the same movements instead of deducting twice.

A refund goes the other way: `create_posted_return()` writes `sales_returns` and
`sales_return_lines`, then `assert_consumption_exists()` proves the order really
consumed the item before restocking it as `return_restock`.

Worked example from the live system: two Chicken Tikka at Johar Town deducted
`-0.440 ING-TIKKA`, `-0.080 ING-YOGURT`, `-0.016` spices, `-0.030` and `-0.040`
from two more ingredients, and drove `INV-CHICKEN` from 213.340 to 212.900.

## Tenant isolation, in two places

- **Application:** every query filters `business_id`; `require_branch_access()`
  checks the branch against the user's scope; `app/services/tenancy.py` re-checks
  inside the services.
- **Database:** `ON DELETE RESTRICT` foreign keys and triggers on orders, order
  lines, branch prices and transfers.

A manipulated `product_id` from another restaurant returns 404 before anything is
written. That case is exercised by the verification script
(`POST /pos/add` with a foreign product id).

## Security choices you can defend

- Passwords are hashed with Werkzeug's default (`scrypt`), never stored in clear.
- The session holds a user id, not a role, so a role change applies on the next
  request. `clear_permission_cache()` runs when a role is edited.
- CSRF: one token per session, compared with `hmac.compare_digest` on every POST.
  Sign-in clears the session, which rotates the token.
- Permissions are rows (`role_permissions`), not `if role == 'admin'` in a template.
- Money is `Decimal` end to end; no `float` touches an amount.
- Transactions wrap checkout, payment, refund, receive and transfer, with
  `rollback()` on any exception.

## Which data is demo

The catalogue, staff and prices are curated coursework data. 8,604 of the orders
are generated history (`SYNTHETIC_HISTORY_V1`) covering 1 May 2025 to
31 October 2026, with planted weekday and hour patterns. Orders taken through this
application carry `APPLICATION_GENERATED`. The reports page prints the split, and
`dataset_manifests` records the provenance. Nothing in the system claims the
synthetic rows are real trading.

## Likely questions

**"Where is the tax rate?"** In `tax_rules`, one active row per business. The rate
is read at checkout, stored on the order as `tax_rule_id`, and the tax amount is
saved on the order so a later rate change does not rewrite history.

**"What stops a double payment?"** `capture_payment()` sums captured payments
inside the transaction and rejects a payment that would exceed the grand total. A
second full payment raises `PaymentError` before SQL sees it.

**"What stops a double receipt?"** `receipt_records.order_id` is unique, and
`finalize_receipt()` returns the existing row instead of inserting a second one.

**"How does a new business get created?"** `/signup` calls
`app/services/signup.py`, which writes the business, its settings, one branch,
three payment methods, an optional tax rule and a trial subscription, then the owner
user and an `owner` membership — in one transaction, so a half-registered tenant
cannot exist. The owner role then comes from `role_permissions`, exactly like the
seeded accounts. Set `POS_SIGNUP_ENABLED=0` to close it.

**"Why is nothing deleted?"** A POS is a ledger. Deleting a paid order destroys the
audit trail. Orders are cancelled or refunded, products are retired with
`is_active`, stock is reversed with an opposing movement. `ON DELETE RESTRICT` makes
accidental deletion fail loudly.

**"How is a branch chosen?"** From the user's membership. `business_users.branch_id`
set means that one branch; empty means every branch of the business. The picker only
lists branches the server will accept, and `select_branch()` re-checks on POST.

**"What is the kitchen ticket for?"** It is the station-facing document. The till
creates it, the kitchen board moves it through `queued → preparing → ready →
served`, and each item carries its own status.

**"What happens if stock is insufficient?"** `apply_stock_delta()` raises
`StockPolicyError`, the transaction rolls back, and the till reports the item that
would go negative. The sale is not silently allowed to break the ledger.

**"Where are the reports calculated?"** In SQL, in `app/services/reporting.py`.
Period boundaries convert local dates to UTC instants, so a "day" is a Pakistan
day. No figure is cached or estimated. The page is drawn by
`app/static/js/reports.js` from `/reports/api/data`, which is why changing a filter
does not reload anything. `docs/REPORTS.md` has the full list.

**"How do you know the report numbers are right?"** Every figure is a SQL aggregate
over `restaurant_orders`, `order_items`, `order_payments` and friends.
`tests/test_reports.py::test_totals_reconcile_with_the_database` recomputes the same
period with a raw SQL `SUM` and asserts the API returns identical values.

**"Why does the report URL keep the filters?"** The state is written into the query
string with `history.pushState`, the shell renders from it, and `popstate` re-reads
it. The session also remembers the last resolved filters so the Reports link
reopens the same view. An older design submitted a form and reset everything on
navigation; that is the bug the regression test covers.

**"How does the super admin work?"** `users.is_platform_admin` grants the
`platform_admin` permission set and lets the business picker choose any tenant. The
branch list is then limited to that tenant, so a branch id from another tenant
returns 403. Each switch writes an `audit_events` row.

**"Why no Bootstrap?"** One stylesheet of about 500 lines keeps the markup
readable and the page weight low. The layout is a fixed sidebar and a card grid,
which is the familiar convention this kind of tool uses, and it costs no CDN
request.

## If you have five minutes

1. Sign in as the Johar Town manager.
2. Open Till, add two Chicken Tikka, take payment.
3. Print the receipt.
4. Open Reports, set a date range, then click Products and come back — the dates
   survive, and the URL shows the whole view.
5. Open Restaurants as the super admin and switch to another restaurant's branch.
6. Open Stock, filter to below the reorder level, and post a small adjustment.
5. Open Reports for the last 30 days and point at the demo-data note.
6. Sign in as the kitchen account and show that Reports is refused.

## Known limits, stated plainly

No shift close-out screen, no batch or expiry tracking, no camera scanner, no
printer driver, no live language model. The tables for shifts, batches, scanner
sessions and approvals exist; the screens do not, and the navigation does not
pretend otherwise.
