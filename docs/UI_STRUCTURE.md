# UI structure

How the interface is put together, which template renders which screen, and which
JavaScript file does what. Written so it can be explained out loud.

## 1. The shell

Every signed-in page extends `app/templates/base.html`. The shell has four fixed parts:

```
+---------------------------------------------------------------+
| top bar: mark · business · [restaurant][branch][Apply] · role · user · sign out |
+----------+----------------------------------------------------+
| left rail| page bar: breadcrumb / title / page actions          |
| 196px    +----------------------------------------------------+
|          | tabs (optional)                                     |
|          +----------------------------------------------------+
|          | content: panels, tables, forms                      |
+----------+----------------------------------------------------+
```

- **Top bar** (`<header class="topbar">`) holds identity and the working context. The
  restaurant and branch selects are a draft form: changing the restaurant refills the
  branch list in JavaScript, and only `Apply` posts to `auth.switch_context`.
- **Left rail** (`<aside class="side">`) is grouped into Sales, Catalogue, Stock,
  Business, and Platform (super admin only). Ten destinations in total.
- **Page bar** (`<div class="pagebar">`) is filled by three blocks: `section`
  (breadcrumb), `heading` (page title) and `actions`.
- **Tabs** (`{% block tabs %}`) turn a group of related routes into one workspace. The
  macro lives in `_tabs.html` and takes a list of `(label, url, is_active)`.

### Blocks a page can fill

| Block | Purpose |
| --- | --- |
| `title` | browser tab title |
| `section` | breadcrumb text, e.g. `Sales` or `Stock / Purchasing` |
| `heading` | page title in the page bar |
| `page_sub` | optional small line under the title (state only) |
| `actions` | buttons on the right of the page bar |
| `tabs` | workspace tab bar |
| `content_class` | `wide` for dense tables |
| `content` | the page body |
| `scripts` | page-specific JavaScript |

## 2. Navigation map

| Rail item | Route | Template |
| --- | --- | --- |
| Overview | `GET /` | `dashboard/index.html` |
| Billing | `GET /pos` | `pos/index.html` + `pos/_cart.html` |
| Orders | `GET /orders` | `orders/index.html` |
| Orders → detail | `GET /orders/<id>` | `orders/show.html` |
| Orders → Kitchen tab | `GET /kitchen` | `kitchen/index.html` |
| Orders → Returns tab | `GET /orders/returns` | `orders/returns.html` |
| Menu | `GET /products` | `catalog/products.html` |
| Menu → Categories tab | `GET /categories` | `catalog/categories.html` |
| Inventory | `GET /inventory` | `inventory/index.html` |
| Inventory → tabs | `/inventory/ingredients`, `/recipes`, `/movements`, `/adjust`, `/transfers` | `inventory/*.html` |
| Purchasing | `GET /inventory/purchases` | `inventory/purchases.html` |
| Purchasing → Suppliers tab | `GET /suppliers` | `suppliers/index.html` |
| Branches | `GET /branches` | `admin/branches.html` |
| Reports | `GET /reports` | `reports/index.html` |
| Reports → Insights tab | `GET /insights` | `insights/index.html` |
| Staff | `GET /staff` | `admin/staff.html` |
| Settings | `GET /settings` | `admin/settings.html` |
| Settings → tabs | `/payment-methods`, `/shifts`, `/audit` | `admin/*.html` |
| Platform | `/platform`, `/platform/integrity` | `platform/*.html` |

No route was added, renamed or removed for the interface work. The tabs are ordinary
links to the existing routes.

## 3. Page patterns

Three layouts cover almost every screen.

**Figure strip + panels** — Overview. A single bordered strip of five figures (`net
sales`, `average`, `tax`, `open orders`, `kitchen queue`), then a two-column grid of
panels: recent sales, trend, branch performance on the left; popular items, low stock,
payments, day totals on the right.

**Filters + table** — Orders, Menu, Inventory, Suppliers, Staff, Branches. A
`.filters` strip sits directly on top of a `.panel` (they share a border, so they read
as one block), then a `table.data`, then a `.pager`.

**Split workspace** — Billing and Orders detail. A main column plus a 320px side rail
(`.split`).

Billing is its own thing: `.pos` is a three-column grid — category rail, item grid,
bill — and the bill column is sticky so the total and the payment button stay visible.

## 4. CSS

One file: `app/static/css/app.css`.

| Layer | Contents |
| --- | --- |
| Tokens | `:root` colours, rail width, top-bar height, fonts |
| Shell | `.topbar`, `.side`, `.pagebar`, `.tabs`, `.content` |
| Blocks | `.panel`, `.panel-h`, `.panel-b`, `.figs`, `.filters`, `.split` |
| Data | `table.data`, `.rows`, `.badge`, `.pager`, `.kv` |
| Forms | `.field`, `.grid-form`, `.form-act`, `.check` |
| Billing | `.pos`, `.pos-cats`, `.pos-grid`, `.pos-item`, `.pos-bill`, `.bill-*` |
| Compatibility | `.page-head`, `.card`, `.toolbar`, `.stats` — used by the few pages still on the older markup |

Rules of thumb: borders instead of shadows, no gradients, one accent colour
(`--green`), status colour only inside `.badge`, numbers always tabular.

## 5. JavaScript

| File | Used by | Does |
| --- | --- | --- |
| inline in `base.html` | every page | refills the branch select when the restaurant changes; dismisses flash messages |
| `static/js/till.js` | Billing | posts cart forms without a reload, swaps `#cart-panel`, keeps the line count and amount hint in sync, re-prices when the discount changes |
| `static/js/reports.js` | Reports | loads report sections from `/reports/api/data`, writes filters to the URL with `history.pushState`, restores them on `popstate` |
| `static/js/insights.js` | Insights | small chart helpers |

Everything else is a normal HTML form. No build step, no framework.

## 6. Where each action posts

| Screen | Action | Route |
| --- | --- | --- |
| Billing | add item | `POST /pos/add` |
| Billing | change quantity | `POST /pos/set-quantity` |
| Billing | remove line | `POST /pos/remove` |
| Billing | discount re-price | `POST /pos/quote` |
| Billing | take payment | `POST /pos/checkout` |
| Orders | record payment | `POST /orders/<id>/pay` |
| Orders | hold / resume | `POST /orders/<id>/hold`, `/resume` |
| Orders | cancel | `POST /orders/<id>/cancel` |
| Orders | refund | `POST /orders/<id>/refund` |
| Menu | add / edit item | `POST /products/new`, `/products/<id>/edit` |
| Menu | retire item | `POST /products/<id>/toggle` |
| Inventory | adjust stock | `POST /inventory/adjust` |
| Inventory | add ingredient | `POST /inventory/ingredients/new` |
| Purchasing | raise order | `POST /inventory/purchases/new` |
| Branches | add branch | `POST /branches/new` |
| Staff | add employee | `POST /staff/new` |
| Settings | save business | `POST /settings` |
| Settings | payment method | `POST /payment-methods/new`, `/<id>/edit`, `/<id>/delete` |
| Settings | shift open/close | `POST /shifts/open`, `/shifts/<id>/close` |
| Any | switch restaurant/branch | `POST /context` |

## 7. Template inheritance

```
base.html
├── dashboard/index.html
├── pos/index.html → includes pos/_cart.html
├── orders/index.html, show.html, receipt.html, returns.html
├── catalog/products.html, product_form.html, categories.html
├── inventory/*.html
├── suppliers/*.html
├── admin/*.html
├── reports/index.html
├── insights/index.html
├── platform/*.html
└── errors/error.html
```

Two macros: `_icons.html` (inline stroke icons) and `_tabs.html` (workspace tabs).

## 8. Copy rules

The interface states facts:

- No sentence under a heading. `page_sub` carries the date range or order number only.
- No helper text under fields. The server returns a specific message when input is
  wrong; that message is the help.
- No tutorial paragraphs in empty states. `No orders found` and a reset link is enough.
- Buttons are verbs: `Save`, `Apply`, `Reset`, `Take payment`, `New item`.

## 9. Responsive behaviour

| Width | Result |
| --- | --- |
| ≥1240px | full three-column billing, two-column overview |
| ≤1240px | overview collapses to one column, billing narrows |
| ≤1040px | billing drops the category rail, item grid takes the space |
| ≤900px | rail becomes a horizontal strip under the top bar; billing stacks |
| ≤560px | forms become one column, item grid drops to 112px tiles |

Tables never turn into cards; they scroll inside `.tbl-wrap`.

## 10. Adding a page

1. `{% extends "base.html" %}`.
2. Fill `section`, `heading`, and if needed `actions`, `tabs`, `page_sub`.
3. Put data in `.panel`s, filters in `.filters`, rows in `table.data`.
4. Add the route's link to the rail in `base.html` if it is a new destination.
5. Check the page at 1440px, 1024px and 390px.
