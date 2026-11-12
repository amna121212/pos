# Database

One PostgreSQL database, `retail_pos_db`, on `127.0.0.1:5432`, owned by the
`pos_app` role. ParkSphere uses a different database on the same cluster and is not
touched by anything here.

## Current state

Verified against the live server:

| Item | Value |
| --- | --- |
| Connected database | `retail_pos_db` |
| PostgreSQL | 18.6 |
| Alembic revision | `148a58c8d274` (head) |
| Application tables | 65 |
| `alembic_version` | 1 extra table, not an application model |
| SQLAlchemy models | 65, all registered on one metadata |
| Constraints | 727 |
| Indexes | 158 |
| Size | about 42 MB |

The web application adds no table. It writes into the existing ones, so no new
migration is needed for the routes, templates or services.

## Entity groups

The models are split across six modules, all imported by `app/models.py` so one
metadata holds them:

| Module | Tables | Group |
| --- | --- | --- |
| `app/models.py` | 12 | Businesses, branches, users, catalogue, suppliers, printers, registers |
| `app/order_models.py` | 12 | Dining sessions, orders, lines, modifiers, kitchen, payments, receipts |
| `app/inventory_models.py` | 12 | Inventory items, branch stock, batches, movements, purchasing, transfers |
| `app/platform_models.py` | 9 | Plans, subscriptions, settings, opening hours, roles, permissions, tax |
| `app/recipe_models.py` | 4 | Recipes, recipe lines, kitchen stations, station routes |
| `app/operations_models.py` | 11 | Fulfilment, shifts, cash, printing, barcodes, returns, audit |
| `app/intelligence_models.py` | 5 | Dataset manifests, analysis runs, snapshots, recommendations, feedback |

## How the tables relate

```
businesses ─┬─ branches ─┬─ branch_products ── products ── categories
            │            ├─ dining_tables
            │            ├─ printers
            │            ├─ cash_registers
            │            └─ branch_operating_hours
            ├─ users (through business_users, with role and optional branch)
            ├─ payment_methods, tax_rules, business_settings
            ├─ suppliers ── supplier_purchase_orders ── supplier_purchase_items
            └─ inventory_items ─┬─ branch_stocks
                                ├─ stock_movements
                                ├─ stock_batches
                                └─ recipe_lines ── recipes ── products

restaurant_orders ─┬─ order_items ─┬─ order_item_modifiers ── menu_modifier_options
                   │               └─ kitchen_ticket_items
                   ├─ order_payments, order_discounts, order_status_events
                   ├─ order_fulfillments, dining_sessions
                   ├─ kitchen_tickets, receipt_records, print_jobs
                   └─ sales_returns ── sales_return_lines
```

Rules the schema enforces, not the application:

- `business_id` on every tenant row, with `ON DELETE RESTRICT` foreign keys.
- `UNIQUE (branch_id, order_number)`, `UNIQUE (business_id, sku)`,
  `UNIQUE (branch_id, product_id)`, and the other natural keys.
- `CHECK` constraints on order type, order status, payment amounts, stock
  direction, printer purpose, return status, shift status and dataset category.
- `NUMERIC` for money and for stock quantities, never `float`.
- Triggers for tenant consistency on orders, order lines, branch prices and
  transfers.

## Money and time

Money is `NUMERIC(12,2)` in PKR and is handled in Python as `Decimal` through
`app/money.py`. Stock quantities are `NUMERIC(14,3)`. Timestamps are
`timestamptz` storing UTC; every display converts to `Asia/Karachi` (UTC+5, no
daylight saving) through `app/timeutil.py`. Report grouping uses
`date_trunc(... timezone('Asia/Karachi', created_at))` so a "day" matches the
restaurant's day, not the server's.

## Seed data provenance

`dataset_manifests` records where each dataset came from, and every order carries a
`dataset_code`:

| Dataset | Meaning |
| --- | --- |
| `SYNTHETIC_HISTORY_V1` | 8,604 generated tickets, 1 May 2025 to 31 October 2026, labelled as synthetic |
| `APPLICATION_GENERATED` | Orders keyed in through this application, including the verification orders below |
| `MANUALLY_CURATED` | The Lahore catalogue, recipes and staff personas |

The synthetic history is coursework data. It is never presented as real trading,
and the reports page labels the demo share of any period it covers. See
`docs/DATA_PROVENANCE.md` for the planted patterns.

Verification during implementation created four real orders at Johar Town
(`ORD-JT-01451` and `ORD-JT-01452` paid, `ORD-JT-01453` cancelled, `ORD-JT-01454`
paid then refunded as `RET-00036`), one stock adjustment, one purchase order and
one transfer. They are genuine `APPLICATION_GENERATED` rows and are left in place
rather than deleted, because posted documents are reversed, not removed. The 24
`DEMO-` orders from the original seed are also `APPLICATION_GENERATED`.

## Migrations applied

| Revision | Purpose |
| --- | --- |
| `48ea53b715e6` | Phase 1 master data |
| `7ada4cd15c29` | Phase 2 orders, kitchen, payments |
| `c50faa0486e2` | Phase 3 inventory and purchasing |
| `148a58c8d274` | Phase 4 restaurant operations, recipes, snapshots |

```bash
cd /opt/student-projects/pos
.venv/bin/flask --app wsgi db current     # 148a58c8d274
.venv/bin/flask --app wsgi db upgrade     # no-op when already at head
```

## Backup

The `postgres` system user cannot write under `/root`, so dump as the application
role or dump to `/tmp` and move the file.

```bash
set -a; . /root/project-db-credentials.env; set +a
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
PGPASSWORD="$POS_DB_PASSWORD" pg_dump -h 127.0.0.1 -U pos_app -d retail_pos_db \
  -Fc -f "/root/db-backups/retail_pos_${STAMP}.dump"

# prove the archive is readable
PGPASSWORD="$POS_DB_PASSWORD" pg_restore -l "/root/db-backups/retail_pos_${STAMP}.dump" | wc -l
PGPASSWORD="$POS_DB_PASSWORD" pg_restore -l "/root/db-backups/retail_pos_${STAMP}.dump" | grep -c 'TABLE DATA'
```

The `TABLE DATA` count should be 66 for the current schema. A dump taken before the
web phase returned exactly that.

## Restore

Restore into a scratch database first. Never restore straight over the live one.

```bash
sudo -u postgres createdb retail_pos_restore_check
PGPASSWORD="$POS_DB_PASSWORD" pg_restore -h 127.0.0.1 -U pos_app \
  -d retail_pos_restore_check --no-owner --no-privileges \
  /root/db-backups/retail_pos_<stamp>.dump
psql -h 127.0.0.1 -U pos_app -d retail_pos_restore_check \
  -c 'select version_num from alembic_version;' \
  -c 'select count(*) from restaurant_orders;'
sudo -u postgres dropdb retail_pos_restore_check
```

Only swap the live database after that check passes, and only with the service
stopped:

```bash
sudo systemctl stop pos.service
sudo -u postgres psql -c "alter database retail_pos_db rename to retail_pos_old_$(date -u +%Y%m%d);"
sudo -u postgres createdb -O pos_app retail_pos_db
PGPASSWORD="$POS_DB_PASSWORD" pg_restore -h 127.0.0.1 -U pos_app -d retail_pos_db \
  --no-owner --no-privileges /root/db-backups/<chosen>.dump
sudo systemctl start pos.service
```

## Nothing destructive

- Do not run `db.drop_all()`.
- Do not `alembic stamp` over an applied revision.
- Do not downgrade a database that already holds recorded sales.
- Do not point `POS_DB_NAME` at `parksphere_db`; the app refuses to start if the
  name is not `retail_pos_db`, and it re-checks `current_database()` on every new
  connection.
