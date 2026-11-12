The current project guide is README.md. This file is the original phase 1 note.

POS SaaS PostgreSQL bootstrap — Phase 1
=======================================
Scope: Only POS database retail_pos_db; ParkSphere is not referenced.
Tables: 12 master-data models, not the final 60. No fake sales transactions.
Sample businesses, branches, menus and prices are fictional Lahore-oriented demonstration data.

On VPS as root:
 cd /opt/student-projects/pos
 unzip -n /path/to/pos_db_phase1.zip  # do not overwrite any existing files
 .venv/bin/pip install Flask Flask-SQLAlchemy Flask-Migrate 'psycopg[binary]' python-dotenv
 .venv/bin/flask --app wsgi db init
 .venv/bin/flask --app wsgi db migrate -m 'pos phase 1 master tables'
 .venv/bin/flask --app wsgi db upgrade
 .venv/bin/python -m scripts.seed_phase1

If app, wsgi.py or migrations already exist, DO NOT merge blindly. Stop and review conflicts.
The seed is idempotent. It creates original fictional demo entries, NOT real Lahore restaurant records.
BusinessUser role is simple starter design; authorization is NOT implemented yet.
Future: implement 48 more useful relational models, invoice/stock workflows, seed sales from valid transactions.
