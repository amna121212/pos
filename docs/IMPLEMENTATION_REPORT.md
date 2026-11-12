# Database implementation report

Checked on 6 November 2026 against the live database `retail_pos_db` on this server. The application directory is `/opt/student-projects/pos`. ParkSphere was not changed. `parksphere_db` is still present and was not migrated or seeded.

## Result

| Check | Result |
| --- | --- |
| Connected database | `retail_pos_db` |
| Alembic revision | `148a58c8d274` (down revision `c50faa0486e2`) |
| Application tables | 65 |
| `alembic_version` | 1 extra table, not counted as an application model |
| SQLAlchemy models registered | 65 |
| Integrity problems | none (`integrity_problems()` returned an empty list) |
| Pytest | 21 passed in 1.00 seconds |
| Synthetic history manifest | `SYNTHETIC_HISTORY_V1`, status `complete` |
| Analytics runs | 3, engine `deterministic_sql`, same run ids returned on a second execution |

No migration is waiting for approval. `flask db upgrade` has already been applied through phase 4. Do not downgrade this database.

## Tables preserved

Phases 1 to 3 were not recreated. The pre-phase-4 dump was listed with `pg_restore -l` and restored into a temporary database named `retail_pos_restore_check`. That restore showed 3 businesses, 24 orders, 15 stock movements and revision `c50faa0486e2`. The temporary database was then dropped. `retail_pos_db` was not replaced by that restore.

Backup file: `/root/db-backups/retail_pos_pre_phase4_20261106T130015Z.dump` (created 2026-11-06 13:00:15 UTC, custom format, gzip). Older dumps `retail_pos_phase1.dump` and `retail_pos_phase2.dump` are still in `/root/db-backups/`.

These identities are unchanged:

| id | Business | Branches |
| --- | --- | --- |
| 1 | Lahore Grill House | 1 Johar Town (`JT`), 2 DHA Phase 5 (`DHA`) |
| 2 | Urban Bites Lahore | 3 Gulberg III (`GUL`), 4 Model Town (`MT`) |
| 3 | Daily Mart Lahore | 5 Wapda Town (`WT`), 6 Faisal Town (`FT`) |

`businesses.created_at` is still 6 November 2026. `business_settings.trading_since` is 1 May 2025, which is the fictional start used by the simulator. Original sample SKUs are still there, including `BBQ-001` Chicken Tikka, `RIC-001` Chicken Biryani, `BUR-001` Classic Beef Burger, `DAI-001` Milk 1L and `BAK-001` Bread Large.

The original 24 tickets remain `APPLICATION_GENERATED` and `paid`, with order numbers starting `DEMO-`. Their tax was not rewritten.

## Tables added in phase 4

29 tables:

`subscription_plans`, `business_subscriptions`, `business_settings`, `branch_operating_hours`, `roles`, `permissions`, `role_permissions`, `tax_rules`, `recipes`, `recipe_lines`, `kitchen_stations`, `product_station_routes`, `order_fulfillments`, `cashier_shifts`, `cash_movements`, `shift_reconciliations`, `print_jobs`, `printer_issue_reports`, `product_barcodes`, `scanner_sessions`, `sales_returns`, `sales_return_lines`, `discount_approvals`, `audit_events`, `dataset_manifests`, `ai_analysis_runs`, `product_performance_snapshots`, `ai_recommendations`, `recommendation_feedback`.

Migration file: `migrations/versions/148a58c8d274_pos_phase_4_restaurant_operations_and_.py`. It is additive. It also widens order type and status checks, stores `dataset_code` on orders, and adds tenant triggers for orders, order lines, branch prices and transfers.

## Row counts

Counted with `SELECT COUNT(*)` after history generation and snapshot storage.

| Table | Rows |
| --- | ---: |
| businesses | 3 |
| branches | 6 |
| users | 23 |
| business_users | 22 |
| categories | 30 |
| products | 195 |
| branch_products | 390 |
| dining_tables | 24 |
| payment_methods | 9 |
| suppliers | 9 |
| printers | 22 |
| cash_registers | 6 |
| dining_sessions | 3264 |
| restaurant_orders | 8628 |
| order_items | 19861 |
| menu_modifier_groups | 18 |
| menu_modifier_options | 56 |
| order_item_modifiers | 696 |
| kitchen_tickets | 5835 |
| kitchen_ticket_items | 14564 |
| order_discounts | 765 |
| order_payments | 9128 |
| order_status_events | 17182 |
| receipt_records | 8219 |
| inventory_items | 204 |
| branch_stocks | 406 |
| stock_batches | 3813 |
| stock_movements | 34979 |
| stock_adjustments | 4 |
| supplier_purchase_orders | 115 |
| supplier_purchase_items | 3813 |
| goods_receipts | 115 |
| goods_receipt_items | 3813 |
| stock_transfer_requests | 6 |
| stock_transfer_items | 6 |
| stock_transfer_events | 24 |
| subscription_plans | 2 |
| business_subscriptions | 3 |
| business_settings | 3 |
| branch_operating_hours | 42 |
| roles | 6 |
| permissions | 18 |
| role_permissions | 62 |
| tax_rules | 3 |
| recipes | 50 |
| recipe_lines | 186 |
| kitchen_stations | 22 |
| product_station_routes | 274 |
| order_fulfillments | 8604 |
| cashier_shifts | 3255 |
| cash_movements | 6412 |
| shift_reconciliations | 3255 |
| print_jobs | 14018 |
| printer_issue_reports | 387 |
| product_barcodes | 195 |
| scanner_sessions | 12 |
| sales_returns | 137 |
| sales_return_lines | 137 |
| discount_approvals | 799 |
| audit_events | 146 |
| dataset_manifests | 5 |
| ai_analysis_runs | 3 |
| product_performance_snapshots | 390 |
| ai_recommendations | 11 |
| recommendation_feedback | 11 |

## Catalog and history

| Business | Categories | Products | Recipes | Inventory rows |
| --- | ---: | ---: | ---: | ---: |
| Lahore Grill House | 12 | 72 menu items | 27 | 73 ingredients |
| Urban Bites Lahore | 10 | 65 menu items | 23 | 73 ingredients |
| Daily Mart Lahore | 8 | 58 retail items | 0 | 58 retail units linked to products |

Recipes are representative popular plates, not every SKU. Retail sales deduct the linked unit. Modifier extras change the price and do not deduct extra stock.

Synthetic tickets: 8604, from 1 May 2025 through 31 October 2026 (Asia/Karachi). Stored instants run from 2025-05-01 04:52 UTC to 2026-10-31 17:05 UTC.

| Status | Tickets | Meaning |
| --- | ---: | --- |
| paid | 8195 | Payments equal the grand total. Counted in snapshots. |
| cancelled | 262 | Kept. No payment. Not counted as sales. |
| held | 74 | Kept. No payment. |
| partially_paid | 73 | A captured payment exists and is less than the grand total. |

The successful resume inserted 8522 tickets. 82 tickets from the earlier interrupted run were already committed, so the generator did not insert them again. A later run printed `SKIP: synthetic history is already complete`.

Paid-order payments reconcile. Cancelled and held tickets have no payments. Stock balances match the movement ledger. Transfers conserve quantity. Those checks are in `app/services/integrity.py` and in `tests/test_database_integrity.py`.

Prices are curated demo PKR amounts, including the PKR 20 difference at the second branch. They are not market quotations. Planted patterns are described in `docs/DATA_PROVENANCE.md`.

## Tests that passed

`tests/test_history_plan.py` checks Decimal totals, split-payment rounding, empty payments for cancelled and held tickets, and the margin guardrail.

`tests/test_database_integrity.py` checks the database name, 65 models, readable relationships, preserved businesses and the 24 demo orders, clean integrity queries, Decimal money, repeatable analytics, a reporting query under 5 seconds, refused deletion of a posted business, cross-tenant payment and transfer blocks, a second full payment refused, idempotent receipt lookup, recipe consumption that does not add a second `HCONS-` movement, hold and resume, and CSV dry-runs that do not persist.

Command:

```bash
cd /opt/student-projects/pos
.venv/bin/python -m pytest -q
```

Observed: `21 passed in 1.00s`.

## Student import

Templates are in `data/csv_templates/`, including `businesses.csv` and `branches.csv`. The importer skips an existing slug, branch code, SKU or email and does not overwrite it. `--dry-run` rolls back. Emails must use `@example.invalid`.

## Refinement pass

A second pass repaired the parts that made the product feel unfinished. Nothing was
rebuilt from scratch; the existing models, services and authentication were kept.

| Problem found | Fix |
| --- | --- |
| Report filters were a `GET` form, so every change reloaded the page | Reports are now a shell plus `/reports/api/data`, rendered by `app/static/js/reports.js` |
| The navigation link pointed at bare `/reports`, resetting the dates | The resolved filter set is kept in the session and the URL is the source of truth |
| Fifteen reports were missing or combined into five panels | All fifteen now exist, each with an honest empty state |
| Suppliers were nine "… Demo …" records shown only in a dropdown | Renamed in the database and in the seeds; a supplier directory now has list, detail, create and update |
| Three owners were named "… Demo Owner" | Renamed to person names; emails are untouched because they are login identifiers |
| Receipt footers read "Coursework demo receipt…" | Replaced with normal receipt text; provenance stays in reports, manifests and docs |
| No page listed the restaurants or their branches | `/restaurants` with search, hours, branch counts and one-click switching |
| Ingredients and recipes had no screen | `/inventory/ingredients` and `/inventory/recipes` |
| Shifts and the audit log were invisible | `/shifts` and `/audit`, read-only |
| Dashboard showed six numbers and one table | Today's trading, seven-day trend, payments, top products, low stock, branch performance, each linking to its detail view |
| Navigation mixed unrelated modules | Five groups with icons, clear active state, and a horizontal strip on narrow screens |

Verified after the pass: 72 tests pass, every page returns 200 for a super admin and
a branch manager, the filtered report survives navigation, the JSON API answers a
full 18-month range in about 210 ms, unauthorised branches and foreign records return
403/404, and a real sale still posts payment, stock and a receipt correctly.

The one remaining cosmetic compromise is that the seeded login emails keep the
reserved `example.invalid` domain, because changing them would break the documented
demo accounts.

## Web application phase

The database phase left routes, templates and sign-in unbuilt. They now exist, and
the ledger rules in `docs/CRUD_LIFECYCLE.md` were not changed to add them.

| Added | Detail |
| --- | --- |
| Application factory | `app/__init__.py`: session key, CSRF, ProxyFix, error pages, blueprint registration |
| Security context | `app/security.py`: acting user, business, branch, permission gates |
| Till basket | `app/cart.py`: session basket, no prices stored client-side |
| Checkout service | `app/services/pos_orders.py`: pricing, order, payment, consumption, receipt in one transaction |
| Reporting | `app/services/reporting.py`: period-bounded SQL reports |
| Views | thirteen blueprints, 64 application routes, 41 templates, one stylesheet, a till script and a reports renderer |
| Registration | `app/services/signup.py`: business, settings, branch, payment methods, tax rule, trial plan, owner and membership in one transaction |
| Super admin | `is_platform_admin` account with business and branch pickers, session-scoped tenant, audited switches; `scripts/manage_superadmin.py` owns that one account |
| Account passwords | `scripts/set_demo_passwords.py` replaces the random seed hashes for synthetic accounts |
| Tests | `tests/test_web.py` 37, `tests/test_reports.py` 14; suite total 72 |

Verified on the live server against `retail_pos_db`, revision `148a58c8d274`:

| Check | Result |
| --- | --- |
| `pytest -q` | 52 passed |
| Cashier sign-in, dashboard, till | pass |
| Super admin switching | all four businesses and their branches listed correctly; pages followed the picker; cross-business order returned 404; switches written to `audit_events` |
| Registration to first sale | signup created business, branch, settings, payment methods, tax rule and trial; added category and product; sold 3 × Rs 400 with 5% tax = Rs 1,260 |
| Checkout with payment | order paid, payment captured, receipt issued |
| Recipe consumption | `HCONS-` movements written, branch stock reduced |
| Kitchen ticket | raised per order |
| Hold, resume, cancel | pass |
| Refund | posted, stock restored to the pre-sale figure |
| Stock adjustment, purchase receipt, transfer | pass, quantity conserved across branches |
| Reports, staff, inventory, platform pages | pass |

Four orders from that verification remain in the database as
`APPLICATION_GENERATED` rows, alongside one adjustment, one purchase order and one
transfer. They were not deleted, because posted documents are reversed rather than
removed.

Still not built, and hidden rather than faked: shift close-out and cash
reconciliation screens, batch and expiry tracking, a camera scanner pairing flow, a
discount approval queue, printer failure reports, station-split kitchen routing, and
a language-model narration layer. Grok is not called; recommendations stay
`rule_engine` rows that describe the stored SQL totals.

Remaining work, in the order it would be useful: a shift open/close screen built on
`cashier_shifts` and `shift_reconciliations`, then batch tracking on receiving, then
the approval queue.

