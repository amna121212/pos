# Reports

The reports page is a single shell (`/reports`) plus one JSON endpoint
(`/reports/api/data`). Every panel is drawn from that endpoint with the same
filter set, so nothing on the page can disagree with anything else.

## Why it is built this way

The previous version rendered reports server-side. Changing a filter submitted a
form, which reloaded the page, and the navigation link pointed at bare `/reports`,
so leaving the page and coming back reset the dates to the last 30 days. Clicking
anything meant starting again.

The current design fixes that at the root:

| Requirement | Implementation |
| --- | --- |
| Filter changes must not reload the page | Filters call `fetch()` against `/reports/api/data` and re-render panels in place |
| Filters must survive refresh, back, forward and bookmarking | The filter state lives in the query string; `history.pushState` on every change, `popstate` re-reads it |
| The URL must describe the view | `replaceState` normalises the URL on load so it always lists the active filters |
| Filter changes must not reset on navigation | The last resolved filter set is kept in the session, so the **Reports** nav link reopens it |

## Filters

| Parameter | Values | Default |
| --- | --- | --- |
| `from` | `YYYY-MM-DD` | 30 days before `to` |
| `to` | `YYYY-MM-DD` | today (Pakistan time) |
| `branch` | `all` or a branch id the account may read | the only branch for a single-branch account, else `all` |
| `group` | `day`, `week`, `month` | `day` |
| `status` | `paid`, `settled` (paid + part paid), `all` | `paid` |
| `category` | category id | all |
| `payment` | payment method id | all |
| `employee` | user id of a member of this business | everyone |
| `supplier` | supplier id | all |
| `compare` | `1` / `0` | `1` |
| `limit` | 5–50 rows per list | 15 |

Rules enforced on the server (`app/blueprints/reports.py`):

- A span longer than 366 days is trimmed to 366 days from `to`.
- `from` later than `to` is swapped.
- A branch, category, payment method, supplier or employee that does not belong
  to the acting business, or a branch outside the account's scope, returns **403**
  rather than silently falling back to a default.
- An unknown `sections` value returns **400**.
- The account needs `report.view`.

## Changing business or branch from the top bar

The picker in the top bar chooses the *working context*. It is a **draft form**:
picking a restaurant only refills the branch dropdown from data already embedded in
the page, picking a branch changes nothing on the server, and nothing is committed
until **Apply** is pressed. One `POST /context` carries the restaurant and the branch
together, so there is no reload between the two choices and no jump to a default.

It used to submit on every change and always land on the dashboard, which is why an
open report used to be lost. Everything now survives because:

- the form carries a hidden `next` field with the current path and query string, so
  the server returns you to the exact view;
- the branch list for every selectable restaurant ships once in the page
  (`<script id="context-branches">`), so changing restaurant costs no request;
- on the reports page `reports.js` intercepts the Apply and posts to `/context` with
  `X-Requested-With: fetch`, which answers JSON. The page then redraws the brand, the
  branch list and the reports in place — no reload at all.

After a restaurant switch every record filter is cleared (branch, category, payment
method, employee, supplier) because those ids belong to the previous tenant. The date
range, granularity, status, comparison and row limit are preserved. A branch switch
inside the same restaurant leaves the report's own branch filter alone, since that
filter is explicit and visible.

## Calculations

Money is `NUMERIC` and handled as `Decimal` in Python. Totals are produced by
PostgreSQL aggregation, never by summing rows in the browser.

| Figure | Definition |
| --- | --- |
| gross | `SUM(restaurant_orders.grand_total)` |
| net sales | `SUM(grand_total - tax_total)` |
| tax | `SUM(tax_total)` |
| discounts | `SUM(discount_total)` |
| average order | `net sales ÷ paid orders` |
| items sold | `SUM(order_items.quantity)` for those orders |

Only orders with the selected status are counted. `paid` is the default so
cancelled, held and part-paid tickets never inflate takings. `status_mix` in the
provenance panel deliberately ignores that filter and reports every status, which
is how cancelled and unsettled work is kept visible.

Day, week and month buckets use
`date_trunc(... timezone('Asia/Karachi', created_at))`, so a "day" is a Pakistan
day, not a UTC day.

## The fifteen reports

| Panel | What it shows | Source |
| --- | --- | --- |
| Sales overview | net sales, orders, average order, items, tax, discounts, with % change against the previous equal-length period | `restaurant_orders` |
| Daily sales | column chart and total for each trading day in the period | `restaurant_orders` |
| Weekly sales | same, grouped by week (`date_trunc('week')`) | `restaurant_orders` |
| Monthly sales | same, grouped by month | `restaurant_orders` |
| Branch comparison | orders, net, average and gross per branch | `restaurant_orders` × `branches` |
| Product performance | quantity and revenue per product, top `limit` | `order_items` × `products` |
| Category performance | revenue per category | `order_items` × `products` × `categories` |
| Payment methods | captured payments, amount and share per method | `order_payments` × `payment_methods` |
| Cancelled and refunded | cancelled orders and value, unsettled statuses, posted refunds and exchanges | `restaurant_orders`, `sales_returns` |
| Cashier performance | per cashier: orders, net, average, discounts | `restaurant_orders` → `cashier_shifts` → `users` |
| Stock consumption | movement counts and net quantity by type, plus the most consumed items | `stock_movements` × `inventory_items` |
| Low stock | items at or below their reorder level at the branch | `branch_stocks` × `inventory_items` |
| Purchases and suppliers | goods received, value per supplier, recent purchase orders | `supplier_purchase_orders`, `supplier_purchase_items`, `goods_receipts` |
| Discounts | discounted orders, total and average discount, largest discounts | `restaurant_orders` |
| Operational summary | order type mix, busiest hours, busiest weekdays, kitchen tickets | `restaurant_orders`, `kitchen_tickets` |
| Data provenance | synthetic vs till-entered order counts and the full status mix | `restaurant_orders.dataset_code` |

The category filter is applied twice on purpose: order-level figures count orders
that *contain* the category, while the product and category tables narrow to lines
of that category. Filtering "BBQ" therefore shows BBQ items rather than the whole
basket of every order that included one.

Low stock is not period-bound: it reports current stock at the selected branch, and
returns nothing when the filter is "All branches" because a reorder level is a
branch fact.

## API

```
GET /reports/api/data?from=2026-01-01&to=2026-01-31&branch=1
GET /reports/api/data?from=...&sections=overview,payments
```

```json
{
  "ok": true,
  "filters": { "from": "2026-01-01", "to": "2026-01-31", "branch": "1", "...": "" },
  "labels": { "business": "Lahore Grill House", "branch": "Johar Town", "period": "01 Jan 2026 – 31 Jan 2026" },
  "period": { "from": "2026-01-01", "to": "2026-01-31", "days": 31 },
  "sections": { "overview": { "...": "..." }, "daily": [], "…": {} }
}
```

A query failure returns HTTP 500 with `{"ok": false, "error": "…"}` and logs the
exception. The page shows that message and keeps the previous filters; it never
substitutes default figures.

## Front-end behaviour

`app/static/js/reports.js`:

1. On load it reads the embedded state, fills the filter controls, renders every
   panel, and normalises the URL with `replaceState` — no extra request.
2. A filter change collects the controls, pushes the new URL, and fetches. Only one
   request is in flight: a new change aborts the previous one with
   `AbortController`.
3. `popstate` restores state from the URL, so browser back and forward move between
   report views instead of leaving the page.
4. While loading, a thin status strip appears and the panels dim. A failure shows a
   red banner with the reason; the old values stay on screen rather than being
   replaced by zeros.

Charts are plain HTML and inline CSS bars — no charting dependency, so nothing has
to be fetched from a CDN and the page works offline.
