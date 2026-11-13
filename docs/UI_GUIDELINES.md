# UI guidelines

The interface is a plain server-rendered Flask/Jinja2 application with one hand-written
stylesheet (`app/static/css/app.css`) and small vanilla-JS files. There is no CSS
framework, no build step and no component library. This document is the reference for
keeping new screens consistent with what exists.

## 1. Visual system

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#f7f7f4` | page background |
| `--surface` | `#ffffff` | cards, tables, inputs, top bar |
| `--surface-2` | `#fbfbf8` | table headers, totals strip, table footers |
| `--surface-3` | `#f2f3ee` | sidebar, chart tracks, disabled fields |
| `--line` | `#e2e5df` | borders and dividers |
| `--line-strong` | `#ccd2c7` | input and button borders |
| `--text` | `#202722` | primary text |
| `--muted` | `#5d6a61` | secondary text, labels |
| `--faint` | `#8b948c` | metadata, table headers, placeholders |
| `--primary` | `#315c46` | actions, active navigation, chart bars |
| `--primary-dark` | `#264a38` | primary hover |
| `--primary-soft` | `#eaf0ec` | focus ring, avatar background |
| `--ok` / `--ok-bg` | `#2f6b4a` / `#e9f1ec` | paid, active, settled |
| `--warn` / `--warn-bg` | `#8a5a12` / `#faf0de` | held, open shift, attention |
| `--bad` / `--bad-bg` | `#9a3a31` / `#fbeceb` | cancelled, refunded, errors |
| `--info` / `--info-bg` | `#34566e` / `#eaf0f4` | options, super admin, neutral notices |

Radii are `6px` for cards and controls, `4px` for small buttons, badges and inputs.
Shadows are a single token, `--shadow-sm` (`0 1px 2px rgba(32,39,34,.05)`), used on
cards and the active navigation item. Nothing else is elevated.

Colour never carries meaning alone: a status is always a badge with a word in it
(`Paid`, `Held`, `Cancelled`), not just a colour.

## 2. Typography

One family: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, ...`.
Monospace (`--mono`) is reserved for identifiers — order numbers, SKUs, receipt sheets —
and for tabular figures where columns must line up.

| Role | Size / weight |
| --- | --- |
| Page title (`h1`) | 20px / 650, `-0.02em` |
| Card title (`h2`) | 13px / 600 |
| Body, table cells | 13.5px / 400 |
| Table cells (dense lists) | 12.5px |
| Labels | 12px / 500 in `--muted` |
| Table headers | 10.5px / 600, uppercase, `0.05em` |
| Metadata (`.sub`, `.hint`, `.faint`) | 11–12px in `--muted`/`--faint` |

Numbers always use `font-variant-numeric: tabular-nums` (`.num`, `.v`, `td.num`) so
amounts align down a column.

## 3. Layout

```
+----------+--------------------------------------------------+
| sidebar  | top bar: context picker · role · account · sign out |
| 225px    +--------------------------------------------------+
|          | content: page title, actions, then data           |
+----------+--------------------------------------------------+
```

- Sidebar is fixed width (`--sidebar-w`, 225px), sticky, full height, scrollable with the
  scrollbar hidden. Below 1000px it narrows to 196px; below 860px it becomes a
  horizontally scrolling strip above the content.
- Top bar is 54px (`--topbar-h`), sticky, and holds the restaurant/branch picker, the
  active role or `Super admin` badge, the account chip and sign out.
- Content is capped at 1320px, or 1680px when a page sets
  `{% block content_class %}wide{% endblock %}` (till, reports, dense tables).
- Page rhythm: 20px padding, 16px between the heading and the first block, 14px between
  cards. Vertical gaps inside a card are 10–14px.

## 4. Components

All of these are defined once in `app.css`; reuse the class rather than restyling in a
template.

| Component | Markup | Notes |
| --- | --- | --- |
| Card | `.card` > `header` (optional `h2` + `.hint`) + `.body` (or `.body.flush`) | `.flush` removes padding for tables |
| Stat | `.stats` > `.stat` (`.stat-link` when clickable) with `.k`, `.v`, `.n` | 6 maximum per row; no icons inside |
| Table | `.table-wrap` > `table` | `th.num` / `td.num` right-aligns, `td.actions` holds row buttons |
| Toolbar | `.toolbar` with `.field` children | search field uses `.field.search`, wide inputs `.field.wide` |
| Form | `.form-grid` > `.form-row` (label + input) | three columns via `.form-grid.three` |
| Badge | `.badge.ok` `.warn` `.bad` `.info` `.muted` | always contains a word |
| Button | `.btn` plus `.primary`, `.ghost`, `.danger`, `.small`, `.block`, `.btn-lg` | one primary action per screen |
| Empty state | `.empty` > `strong` + one line or link | says what is missing, not how to feel about it |
| Flash | `.flash.success` `.error` `.warn` `.info` | rendered by `base.html` from Flask flashes |
| Bar chart | `.cols-chart` (vertical) or `.bar-list` (horizontal) | CSS only, no chart library |
| Key/value | `.kv` with `dt`/`dd` | summary panels |

Icons are inline 16px strokes from `_icons.html` (`icon('cart')`). There are no emoji and
no icon fonts. Icons appear in navigation and in a few buttons; they are never used as
decoration inside form fields.

## 5. The till

The cashier screen is deliberately not a dashboard. It is a two-panel billing surface:

- **Left** — search, barcode field, category chips, product grid. A product that has
  modifiers links to `pos.configure`; everything else posts straight into the basket.
- **Right** — a sticky bill panel: line items with quantity controls, a totals strip
  ending in the grand total, then the payment block (type, table, discount, method,
  received, note) and one full-width `Take payment` button.

Product tiles are 146px minimum, two lines of name, price on the left and SKU on the
right. Nothing animates on hover except the border colour.

## 6. Copy rules

The interface states facts. It does not explain itself, welcome the user, or sell
anything.

- Do not put a sentence under a page heading. `.page-head .sub` is for state only —
  the active date range, the order number on a receipt — never for prose.
- Do not add helper text under fields or cards. Required input is enforced by the
  backend, which returns a specific message; that message is the help.
- Table and card headers carry a count or a range (`.hint`), not an instruction.
- Allowed text: field labels, validation errors, empty-state facts, confirmation
  messages, permission notices, destructive-action confirmations.

Wrong: *"Manage your inventory effortlessly."*
Right: *"Inventory"*, and a table of rows with quantities.

## 7. State and interaction

- Report filters live in the URL and in the session; `reports.js` uses
  `history.pushState` and re-renders from JSON without a reload. Keep new filters inside
  the same mechanism (`FILTER_IDS`, `serialise()`), or they will reset on navigation.
- The restaurant/branch picker is a draft form: changing a select only repopulates, and
  `Apply` posts to `/context` once. Do not add auto-submit.
- Cart actions post with `X-CSRF-Token`, swap the returned `#cart-panel` HTML and update
  the amount hint. Full-page reloads are a fallback, not the normal path.
- Destructive actions use `onsubmit="return confirm(...)"` and are refused by the server
  when records reference the row.

## 8. Responsive rules

| Breakpoint | Behaviour |
| --- | --- |
| ≥1180px | two-column `.cols`, till keeps a 372px bill panel |
| ≤1180px | `.cols` collapses to one column, bill panel narrows to 330px |
| ≤1000px | sidebar 196px, till stacks (bill below products), account email hidden |
| ≤860px | sidebar becomes a horizontal strip, top bar wraps, page head stacks |
| ≤620px | category chips scroll horizontally, form grids become single column, product grid drops to 126px tiles |

Tables never reflow into cards; they scroll inside `.table-wrap`. Print styles hide the
sidebar, top bar, actions and toolbars so receipts and reports print cleanly.

## 9. Adding a screen

1. Extend `base.html`, set `{% block title %}`. Use `content_class` `wide` only for
   dense tables, the till or reports.
2. Start with `.page-head` holding an `h1` and `.page-actions` (one primary action).
3. Put data in `.card`s. Filters go in a `.toolbar` above the table, inside the card or
   directly above it.
4. Use `.btn` for every action; `primary` once per screen.
5. Use `.empty` for the zero-row case and name the missing thing.
6. Do not add a subtitle, an intro paragraph, or an explanatory line under anything.
7. Check the page at 1440px, 1024px and 390px before calling it done.

## 10. What to avoid

- Gradients, glass effects, large corner radii, floating shapes, drop shadows beyond
  `--shadow-sm`.
- Identical card grids repeated on every page, or KPI tiles larger than a table row.
- Decorative progress bars, donut charts, fake or hardcoded statistics.
- Emoji in navigation or headings.
- Skeleton loaders for server-rendered pages; use real empty states.
- Marketing language, onboarding tours, or AI-style helper copy anywhere in the UI.
- A second accent colour. Forest green is the only accent; statuses have their own
  semantic colours.
