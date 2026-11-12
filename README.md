# Amna — Multi-Branch POS

A working Flask point of sale for three fictional Lahore businesses, built on one
PostgreSQL database (`retail_pos_db`) for every tenant. ParkSphere is a separate
project with its own database; nothing here touches it.

The site runs at <https://amna.areeenaa.com> behind Nginx with Gunicorn on
`127.0.0.1:8001`.

## What the application does

Implemented and exercised end to end:

- **Accounts** — email and password sign-in with hashed passwords, server-side
  sessions, role checks from the `roles`/`permissions`/`role_permissions` tables,
  and a signed-in branch that is re-checked on every request.
- **Registration** — `/signup` creates a new business, its settings, its first
  branch, three payment methods and the owner login in one transaction, then signs
  that owner straight in. Close it with `POS_SIGNUP_ENABLED=0`.
- **Till** — branch-priced products, category filter, search, barcode field,
  per-item modifiers, a session basket, dine-in / takeaway / counter pickup,
  manager discount, payment capture, and a printable 80 mm receipt.
- **Orders** — filtered history, order detail with payments and status history,
  hold, resume, cancel, remaining payment on a part-paid bill, and refunds that
  restock what was consumed.
- **Kitchen** — a ticket is raised per restaurant order, with ticket and item
  status on a board.
- **Stock** — on-hand by branch, reorder indicator, movements ledger, adjustments,
  supplier purchase orders with receiving, and inter-branch transfers.
- **Ingredients and recipes** — the stock items and the recipe lines that decide what
  a paid sale consumes.
- **Suppliers** — a directory with create and update, purchase-order history, goods
  received and ordered value per supplier.
- **Restaurants** — one place listing every restaurant the account may act for, with
  search, branch counts, opening hours and a one-click switch to any branch.
- **Catalogue** — product list plus create, edit, retire, and category management.
- **Reports** — fifteen database-backed reports on one page: sales overview, daily,
  weekly and monthly series, branch comparison, product and category performance,
  payment methods, cancelled and refunded work, cashier performance, stock
  consumption, low stock, purchases, discounts, operational summary and data
  provenance. Filters live in the URL and update in place without reloading.
- **Administration** — employees and roles, cashier shifts with drawer variance, an
  audit log, branches and operating hours, receipt and stock settings, and a platform
  console with a data-integrity check.
- **Insights** — stored deterministic snapshots and rule-written recommendations per
  business, refreshed on demand. No language model is called.
- **Administration** — staff roles, branches, receipt and stock settings, and a
  platform console with a data-integrity check.

Not built, and deliberately not faked: physical printer drivers, a phone camera
scanner, shift close-out screens, and an AI narration layer. The printer records a
print job; the browser produces the paper copy.

## Requirements

- Python 3.12 or newer (the server runs 3.14)
- PostgreSQL 16 or newer (the server runs 18.6)
- The dependencies in `requirements.txt`

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in the database values
flask --app wsgi db upgrade
flask --app wsgi run --debug
```

The app refuses to start if it connects to any database other than
`retail_pos_db`, so a stray `DATABASE_URL` cannot silently point at ParkSphere.

### Environment variables

Names only; values live in `/etc/pos/pos.env` on the server and are never committed.

| Name | Purpose |
| --- | --- |
| `POS_DB_USER` | PostgreSQL role, `pos_app` |
| `POS_DB_PASSWORD` | That role's password |
| `POS_DB_HOST` | `127.0.0.1` |
| `POS_DB_PORT` | `5432` |
| `POS_DB_NAME` | Must be `retail_pos_db` |
| `POS_SECRET_KEY` | Session signing key; a random one is generated if unset |
| `POS_SESSION_COOKIE_SECURE` | `1` behind HTTPS, `0` for plain-HTTP local work |
| `POS_SIGNUP_ENABLED` | `1` to allow `/signup`, `0` to close registration |

The password is read from the environment first, then `/etc/pos/pos.env`, then the
legacy root-only file `/root/project-db-credentials.env`. `config/pos.env.example`
is the secret-free template.

### Migrations

```bash
.venv/bin/flask --app wsgi db upgrade      # apply to head
.venv/bin/flask --app wsgi db current      # show the applied revision
```

Head is `148a58c8d274`. The web layer adds no table, so no new revision is required.

### Tests

```bash
.venv/bin/python -m pytest -q
```

83 tests. They read the live database, sign a session cookie directly, and never
store an account password in the suite. Registration and the switch routes are
exercised through their guards only, so the suite creates no tenant and no user.
`docs/TESTING.md` lists what each test proves.

### Demo accounts

Every seeded account is a coursework persona with an `@example.invalid` address.
Passwords are not written in this repository. The operator sets one with:

```bash
.venv/bin/python -m scripts.set_demo_passwords --dry-run            # list accounts
.venv/bin/python -m scripts.set_demo_passwords --password '<value>'  # apply
```

Useful roles at Lahore Grill House, Johar Town:

| Account | Role | Sees |
| --- | --- | --- |
| `demo-owner-lahore-grill-house@example.invalid` | Owner | Every branch, reports, staff, settings |
| `lgh.mgr.jt@example.invalid` | Manager | One branch, reports, refunds, staff |
| `lgh.csh.jt@example.invalid` | Cashier | Till, orders, kitchen, reports (read) |
| `lgh.kit.jt@example.invalid` | Kitchen | Kitchen board only |
| `lgh.inv.01@example.invalid` | Inventory | Stock, purchasing, transfers, reports |

`platform.admin@example.invalid` is a platform-only account with no branch.

### Creating your own business

Open `/signup` (linked from the sign-in page) and fill in the business, its first
branch and the owner login. Registration writes, in one transaction:

| Row | Why |
| --- | --- |
| `businesses` | The new tenant, `is_demo = false` |
| `business_settings` | Currency, timezone, receipt header and footer, margin floor |
| `branches` | One branch, code `MAIN`, so the till has somewhere to sell |
| `payment_methods` | Cash, Card, Bank Transfer, so checkout can take money |
| `tax_rules` | Only when a tax rate above 0 is entered |
| `business_subscriptions` | A trial on the cheapest active plan, when plans exist |
| `users`, `business_users` | The owner account and its `owner` membership |

That account starts with an empty catalogue. Add a category, then products, and the
till is live. Set `POS_SIGNUP_ENABLED=0` in the environment to close public
registration; `/signup` then answers 404 and the link disappears from sign-in.

## Super Admin access

One dedicated account operates across every tenant. It is not a member of any
business (`business_users` has no row for it); its authority comes from
`users.is_platform_admin`, which the application treats as the `platform_admin` role
and therefore grants every permission row.

| | |
| --- | --- |
| Login URL | <https://amna.areeenaa.com/login> |
| Account | `superadmin@areeenaa.com` |
| Password | generated, stored in `/root/pos-admin-credentials.env` (root only, mode `600`); read it with `sudo cat /root/pos-admin-credentials.env` |

The password exists only in that file and as a scrypt hash in `users.password_hash`.
It is never printed by the command, never written to the repository, and never
logged.

### Creating or resetting the account

```bash
cd /opt/student-projects/pos
.venv/bin/python -m scripts.manage_superadmin --create    # fails if the account exists
.venv/bin/python -m scripts.manage_superadmin --reset     # new password, same account
```

Both actions touch only `superadmin@areeenaa.com`. `--create` refuses to overwrite an
existing login; `--reset` refuses to run if the account is missing. Each run writes a
fresh password to the credentials file. Every other user is left untouched.

### How the switching works

After sign-in the top bar shows a **business** picker and a **branch** picker. Only
the super admin sees the business picker, because only that account can act outside
one tenant.

- The choice lives in the session as `bid` (business) and `branch_id` (branch).
- `app/security.py` rebuilds the request context from those two values on every
  request. A super admin's business is read from the picker; every other account's
  business is read from its membership row, and a session value that does not match
  one of its own memberships is discarded.
- Every query already filters on `ctx.business_id` and `ctx.allowed_branch_ids`, so
  the dashboard, till, products, orders, kitchen, inventory and reports all follow
  the selection without extra code.
- Switching business drops the old `branch_id` and empties the basket, because both
  are tenant and price specific.
- Each switch by the super admin writes an `audit_events` row
  (`switch_business` / `switch_branch`).
- Both switch routes are `POST` only, require the session CSRF token, and re-check
  the target against the account's own scope. A cashier posting `business_id=2`
  receives 403, and a manager posting another branch receives 403.

### Closing the older platform login

The seed also contains `platform.admin@example.invalid`, an active platform admin
whose password was set to the shared demo value during the earlier build. Once the
Super Admin is in use, disable it:

```bash
sudo -u postgres psql retail_pos_db -c \
  "update users set is_active = false where email = 'platform.admin@example.invalid';"
```

## Deploying to the server

The deployed copy is the source of truth for this project. From a machine with SSH
access to the VPS:

```bash
cd /opt/student-projects/pos
.venv/bin/pip install -r requirements.txt
sudo systemctl restart pos.service
```

`docs/DEPLOYMENT.md` has the unit file, the Nginx block, rollback and log paths.
`docs/DATABASE.md` has backup and restore instructions.

## Backups

Create a dump before any schema change and prove it restores:

```bash
set -a; . /root/project-db-credentials.env; set +a
PGPASSWORD="$POS_DB_PASSWORD" pg_dump -h 127.0.0.1 -U pos_app -d retail_pos_db \
  -Fc -f /root/db-backups/retail_pos_$(date -u +%Y%m%dT%H%M%SZ).dump
PGPASSWORD="$POS_DB_PASSWORD" pg_restore -l /root/db-backups/<file>.dump | head
```

Restore into a scratch database first, never straight over the live one.
Do not run `drop_all()`, do not stamp over an applied revision, and do not
downgrade this database to tidy it.

## CSV import

Templates are in `data/csv_templates/`, with a small example in `data/csv_examples/`.
An existing slug, branch code, SKU or email is skipped, never overwritten.

```bash
.venv/bin/python -m scripts.import_csv --kind products --file data/csv_examples/products.csv --dry-run
```

## Documentation

| File | Contents |
| --- | --- |
| `docs/SETUP.md` | Local install, configuration names, seeding, common commands |
| `docs/DATABASE.md` | Schema groups, relationships, provenance, backup and restore |
| `docs/ROUTES_AND_CRUD.md` | Every route, permission and CRUD coverage per table |
| `docs/REPORTS.md` | Report calculations, filters, URL behaviour and the JSON API |
| `docs/TESTING.md` | Test inventory, results and the report-filter regression |
| `docs/DEPLOYMENT.md` | Gunicorn, systemd, Nginx, HTTPS, rollback |
| `docs/VIVA_GUIDE.md` | Plain explanation of the architecture and workflows |

## Project layout

| Path | Role |
| --- | --- |
| `app/__init__.py` | Application factory, CSRF, error pages |
| `app/security.py` | Session, acting business/branch, permission gates |
| `app/cart.py` | Basket held in the signed session |
| `app/numbering.py` | Order, PO, transfer and return numbers |
| `app/filters.py` | PKR money, Pakistan time, status badges |
| `app/blueprints/` | `auth`, `dashboard`, `pos`, `orders`, `kitchen`, `catalog`, `inventory`, `reports`, `insights`, `restaurants`, `suppliers`, `admin`, `platform` |
| `app/templates/` | Jinja2 templates, one folder per area, all extending `base.html` |
| `app/static/` | One stylesheet, the till script and the reports renderer |
| `app/models.py` and `*_models.py` | The 65 SQLAlchemy models |
| `app/services/` | Tenancy, stock, recipes, orders, returns, reporting, analytics |
| `scripts/` | Seeds, CSV import, password and placeholder repair, dictionary builder |
| `migrations/versions/` | Alembic revisions |
| `docs/` | Dictionary, ER diagram, routes, deployment, viva guide |

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `POS_DB_PASSWORD is missing` | `/etc/pos/pos.env` is absent or unreadable by the app user |
| `Refusing unexpected database` | `POS_DB_NAME` is not `retail_pos_db` |
| `Refusing non-POS database name` | The env file names another project's database |
| Sign-in says the password is not correct | The demo password was never set; run `scripts.set_demo_passwords` |
| 502 from Nginx | Gunicorn is down: `systemctl status pos.service` |
| `Negative stock is not allowed` | The recipe would consume stock the branch does not hold; receive or adjust stock first |
| Session keeps dropping | `POS_SESSION_COOKIE_SECURE=1` while browsing over plain HTTP |
