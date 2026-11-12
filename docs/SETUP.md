# Setup

How to run Amna POS locally, and where its configuration lives.

## Prerequisites

| Requirement | Version on the server |
| --- | --- |
| Python | 3.14 (3.12+ works) |
| PostgreSQL | 18.6 (16+ works) |
| Git | optional; the deployed copy is not a git checkout |
| A browser with JavaScript | the reports page needs it |

## Local install

```bash
git clone <repository> amna-pos      # or copy the project folder
cd amna-pos
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
POS_DB_USER=pos_app
POS_DB_PASSWORD=<the password>
POS_DB_HOST=127.0.0.1
POS_DB_PORT=5432
POS_DB_NAME=retail_pos_db
POS_SESSION_COOKIE_SECURE=0
```

`POS_SESSION_COOKIE_SECURE=0` is required locally: with `1`, the browser refuses to
send the session cookie over plain HTTP and every request looks signed out.

Apply the schema, then start the server:

```bash
flask --app wsgi db upgrade
flask --app wsgi run --debug --port 8000
```

Open <http://127.0.0.1:8000/login>.

## Configuration reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `POS_DB_USER` | PostgreSQL role | `pos_app` |
| `POS_DB_PASSWORD` | Its password | none — the app refuses to start without it |
| `POS_DB_HOST` | Database host | `127.0.0.1` |
| `POS_DB_PORT` | Database port | `5432` |
| `POS_DB_NAME` | Must be `retail_pos_db` | `retail_pos_db` |
| `POS_SECRET_KEY` | Session signing key; generated into `instance/secret_key` when unset | random |
| `POS_SESSION_COOKIE_SECURE` | `1` behind HTTPS, `0` for local HTTP | `1` |
| `POS_SIGNUP_ENABLED` | `0` closes `/signup` | `1` |

The password is resolved in this order: environment variable, `/etc/pos/pos.env`,
then the legacy root-only file `/root/project-db-credentials.env`. A database name
other than `retail_pos_db` is refused at startup and re-checked on every new
connection, so a wrong `.env` cannot quietly reach another project.

## Database

The application needs the schema at head, not an empty database. To create one from
scratch:

```bash
flask --app wsgi db upgrade          # 4 revisions, 65 application tables
python -m scripts.seed_phase1        # businesses, branches, catalogue
python -m scripts.seed_phase4        # operations, recipes, synthetic history
```

`docs/DATABASE.md` covers the relationships, the synthetic dataset and
backup/restore.

## Accounts

| Account | Role | Notes |
| --- | --- | --- |
| `superadmin@areeenaa.com` | Super admin | password in `/root/pos-admin-credentials.env`; `scripts/manage_superadmin.py --create\|--reset` |
| `demo-owner-lahore-grill-house@example.invalid` | Owner | seeded persona, password set with `scripts/set_demo_passwords.py` |
| `lgh.mgr.jt@example.invalid` | Branch manager | Johar Town |
| `lgh.csh.jt@example.invalid` | Cashier | till and orders |
| `lgh.kit.jt@example.invalid` | Kitchen | kitchen board only |
| `lgh.inv.01@example.invalid` | Inventory | stock, purchasing, suppliers |

New businesses can register at `/signup`, which creates the business, its settings,
one branch, three payment methods and the owner account in one transaction.

## Common commands

```bash
.venv/bin/python -m pytest -q                 # test suite
.venv/bin/flask --app wsgi db current         # applied migration
.venv/bin/flask --app wsgi routes             # every route
.venv/bin/python -m scripts.clean_placeholder_names --dry-run
.venv/bin/python -m scripts.set_demo_passwords --dry-run
.venv/bin/python -m scripts.manage_superadmin --reset
```

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `POS_DB_PASSWORD is missing` | `.env` not loaded or `/etc/pos/pos.env` unreadable |
| Every request looks signed out | `POS_SESSION_COOKIE_SECURE=1` over plain HTTP |
| `Refusing unexpected database` | `POS_DB_NAME` is not `retail_pos_db` |
| Reports show `HTTP 403` | the filter names a branch or record outside the account |
| `Negative stock is not allowed` | the recipe needs stock the branch does not hold |
| 502 from Nginx | Gunicorn is down: `systemctl status pos.service` |
