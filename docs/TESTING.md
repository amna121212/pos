# Testing

```bash
cd /opt/student-projects/pos
.venv/bin/python -m pytest -q
```

83 tests, all passing. The suite reads the live `retail_pos_db`; it does not create
tenants, users or orders, and it never writes a business record. Session cookies are
signed directly, so no account password is stored in the test code.

| File | Tests | Covers |
| --- | --- | --- |
| `tests/test_database_integrity.py` | 17 | database name, model registration, preserved seed data, ledger integrity, money types, tenant blocks, CSV dry runs |
| `tests/test_history_plan.py` | 4 | pure pricing helpers for the synthetic history |
| `tests/test_web.py` | 48 | sign-in, CSRF, permissions, every manager page, super admin switching, tenant isolation, dashboard figures, context switching |
| `tests/test_reports.py` | 14 | report API contract, filter persistence, reconciliation with SQL, empty periods, isolation |

Accounts are **resolved by role at run time** through `tests/support.py`, never hard
coded. An administrator can disable or re-scope a seeded person from the Employees
page at any time, and the suite must keep testing the rule rather than one person's
row. Where a test needs a branch id it asks for the account's own branch, or for a
branch outside its scope, so the assertion stays meaningful after any staff change.
If a role has no active account at all, those tests skip with a clear message instead
of failing.

## The reported bug and its regression test

**Symptom reported:** opening a filtered report and then clicking around reloaded
the page and reset the dates to the default period.

**Reproduced before the fix** (13 Nov 2026, against production):

```
/reports?start=2026-01-01&end=2026-01-31   -> period 01 Jan 2026
click "Reports" in the navigation          -> period 14 Oct 2026   (reset)
GET /reports form                          -> full page reload, 0 fetch() calls, 0 JSON endpoints
```

**Root causes:** the report filters were a plain `GET` form (so every change
reloaded the page), the navigation link pointed at bare `/reports`, and nothing
stored the chosen range anywhere.

**Regression test:** `tests/test_reports.py::test_regression_report_filters_survive_navigation`

```python
first = client.get("/reports?from=2026-01-01&to=2026-01-31&branch=1")
state = bootstrap(first.get_data(as_text=True))["raw"]
assert state["from"] == "2026-01-01"

again = client.get("/reports")          # exactly what the navigation link does
restored = bootstrap(again.get_data(as_text=True))["raw"]
assert restored["from"] == "2026-01-01" # failed before the fix
assert restored["branch"] == "1"
```

**Verified after the fix** on the live site:

```
filtered report    : from 2026-01-01, to 2026-01-31, branch 1
navigation click   : from 2026-01-01, to 2026-01-31, branch 1   -> FILTERS PRESERVED
JSON endpoint      : ok, 17 sections, 100 paid orders, Rs 257,093.00 net
unauthorised branch: 403      unknown section: 400
```

## What each area proves

### Authentication and isolation

- Anonymous visitors are redirected to `/login`; a wrong password returns 401.
- A POST without the CSRF token returns 400, including on the switch routes.
- A cashier cannot POST another business (403) or another branch (403), and sees no
  business dropdown.
- A branch manager cannot report on another branch (403), cannot open another
  restaurant (403), cannot read another tenant's supplier (404) or order (404).
- A tampered `bid` or `branch_id` in the session falls back to the account's own
  membership instead of granting the target.
- The kitchen role is refused by `/reports` and `/reports/api/data` (403).

### Super admin

- Sees every restaurant on `/restaurants`; a manager sees only their own.
- Switching business re-scopes the dashboard, till, products, orders, inventory and
  reports to that tenant's branches only.
- Switching branch resets the basket and re-selects within the new business.
- Every switch writes an `audit_events` row.

### Reports

| Test | Asserts |
| --- | --- |
| `test_api_returns_every_section` | 17 sections present and non-trivial for a populated period |
| `test_totals_reconcile_with_the_database` | overview orders, gross and tax equal a direct SQL sum for the same rows |
| `test_date_range_changes_the_numbers` | a one-day window is smaller than a month but non-zero |
| `test_empty_period_is_reported_honestly` | 2024 returns zero orders and empty lists, not defaults |
| `test_category_filter_narrows_the_result` | fewer orders, and only that category in the category table |
| `test_unknown_section_is_rejected` | 400 instead of a half-built payload |
| `test_super_admin_reports_follow_the_selected_business` | branch codes come only from the chosen tenant |

### Pages

`test_every_manager_page_loads` requests 25 manager pages and fails on any non-200,
so a template error cannot reach production unnoticed.

`test_dashboard_numbers_come_from_the_database` recomputes today's net sales with
SQL and asserts the figure printed on the dashboard matches it.

## Manual verification performed

Run against `https://amna.areeenaa.com` after each deploy:

| Check | Result |
| --- | --- |
| Super admin sign-in and business/branch switching | pass |
| Branch picker lists only the selected business's branches | pass (4 businesses checked) |
| Cross-business order and receipt access | 404 |
| Cashier and manager restrictions | 403 / redirect as expected |
| POS: add item, take payment, stock deduction, receipt | pass (`ORD-JT-0145x`, `HCONS-` movements) |
| Hold, resume, cancel, refund | pass (`RET-00036` restored stock) |
| Supplier create and update | pass (verification row removed afterwards) |
| All module pages (super admin and manager) | 200 |
| Reports: filtered view, nav click, JSON endpoint, 403/400 paths | pass |
| Large range: full synthetic history | returns in well under a second |
| Empty period (2024) | zeroes and empty states |
| Invalid branch id (`branch=999`) | 403 |
| Mobile layout (`max-width: 900px` / `560px`) | sidebar becomes a scroll strip, tables scroll, forms stack |

### Context switching from the top bar

| Test | Asserts |
| --- | --- |
| `test_switch_form_carries_the_current_page` | the picker embeds the current path and query in `next`, and renders the Apply button |
| `test_context_picker_does_not_submit_on_change` | no `onchange` submit inside the context form; only Apply commits |
| `test_context_switch_applies_business_and_branch_together` | one POST to `/context` sets both and redirects back to the same page |
| `test_context_switch_returns_json_for_fetch` | the reports page receives JSON describing the new context |
| `test_context_switch_refuses_a_foreign_branch` | a branch outside scope is 403 even through the combined route |
| `test_switch_returns_to_the_page_you_were_on` | the plain POST redirects back to the same filtered report |
| `test_switch_ignores_an_external_next` | `next=https://evil.example` is refused, so the form is not an open redirect |
| `test_json_switch_refuses_another_business` | a manager switching to another tenant gets 403 |
| `test_switch_without_csrf_is_refused` | the switch routes are CSRF-protected |

## Not covered by automated tests

- Real browser interaction (the suite uses Flask's test client, not a headless
  browser), so `history.pushState`/`popstate` are verified manually and by asserting
  the served JavaScript.
- Printing, physical scanners and email delivery.
- PostgreSQL backups and restores.
