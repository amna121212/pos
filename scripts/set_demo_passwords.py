"""Set a known demo password on the seeded synthetic accounts.

The phase 1 and phase 4 seeds stored `generate_password_hash(os.urandom(24).hex())`,
so no human could ever sign in. This script replaces those hashes with a hash of a
chosen password for accounts flagged `is_synthetic` only; a real account added
later is left untouched.

Usage:
    .venv/bin/python -m scripts.set_demo_passwords --password 'choose-one'
    .venv/bin/python -m scripts.set_demo_passwords --password 'choose-one' --dry-run
"""
import argparse
import sys

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User

# Personas handed out for the review walkthrough.
KEY_ACCOUNTS = (
    "demo-owner-lahore-grill-house@example.invalid",
    "lgh.mgr.jt@example.invalid",
    "lgh.csh.jt@example.invalid",
    "lgh.kit.jt@example.invalid",
    "lgh.inv.01@example.invalid",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--password", help="password to set on every synthetic account")
    parser.add_argument("--dry-run", action="store_true", help="list the accounts and change nothing")
    parser.add_argument("--only-key-accounts", action="store_true", help="limit to the five demo personas")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        query = User.query.filter(User.is_synthetic.is_(True))
        if args.only_key_accounts:
            query = query.filter(User.email.in_(KEY_ACCOUNTS))
        users = query.order_by(User.id).all()
        if not users:
            print("No synthetic accounts matched.")
            return 1
        print(f"{len(users)} synthetic account(s):")
        for user in users:
            print(f"  {user.id:>3}  {user.email:<46} {user.display_name}")
        if args.dry_run:
            print("Dry run: no password was changed.")
            return 0
        if not args.password:
            print("Refusing to write: pass --password or --dry-run.", file=sys.stderr)
            return 2
        if len(args.password) < 8:
            print("Use at least 8 characters.", file=sys.stderr)
            return 2
        digest = generate_password_hash(args.password)
        for user in users:
            user.password_hash = digest
        db.session.commit()
        print(f"Password updated for {len(users)} account(s).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
