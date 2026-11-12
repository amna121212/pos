"""Create or reset the single dedicated Super Admin account.

This command manages one account only, identified by `SUPERADMIN_EMAIL`. It never
touches another user, never prints the password to stdout, and keeps the generated
password in a root-only credentials file. The database stores only the hash.

    .venv/bin/python -m scripts.manage_superadmin --create
    .venv/bin/python -m scripts.manage_superadmin --reset

`--create` refuses to run if the account already exists, so it cannot silently
overwrite a working login. `--reset` refuses to run if it does not exist.
"""
import argparse
import os
import secrets
import string
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User

SUPERADMIN_EMAIL = "superadmin@areeenaa.com"
SUPERADMIN_NAME = "Super Admin"
LOGIN_URL = "https://amna.areeenaa.com/login"
DEFAULT_CREDENTIALS_FILE = "/root/pos-admin-credentials.env"
LEGACY_PLATFORM_ADMIN = "platform.admin@example.invalid"

LETTERS = string.ascii_letters
DIGITS = string.digits
# No '=', '$', quotes or backticks: the value must survive an env file and a shell.
SYMBOLS = "!#%*+-?_@"


def generate_password(length=22):
    """A random password with lower, upper, digit and symbol characters."""
    while True:
        alphabet = LETTERS + DIGITS + SYMBOLS
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(character.islower() for character in candidate)
            and any(character.isupper() for character in candidate)
            and any(character.isdigit() for character in candidate)
            and any(character in SYMBOLS for character in candidate)
        ):
            return candidate


def _existing_created(path):
    """Keep the original creation stamp when the file is rewritten."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("POS_SUPERADMIN_CREATED="):
                return line.split("=", 1)[1].strip()
    return None


def write_credentials_file(path, password, created):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = (
        "# Amna POS - Super Admin credentials. Root only, mode 600.\n"
        "# Do not commit this file and do not copy it into the repository.\n"
        f"POS_SUPERADMIN_URL={LOGIN_URL}\n"
        f"POS_SUPERADMIN_EMAIL={SUPERADMIN_EMAIL}\n"
        f"POS_SUPERADMIN_PASSWORD={password}\n"
        f"POS_SUPERADMIN_CREATED={created}\n"
        f"POS_SUPERADMIN_UPDATED={now}\n"
    )
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(body)
    os.chmod(path, 0o600)


def main():
    parser = argparse.ArgumentParser(description="Create or reset the Super Admin account.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--create", action="store_true", help="create the account (fails if it exists)")
    action.add_argument("--reset", action="store_true", help="reset the password of the existing account")
    parser.add_argument("--file", default=DEFAULT_CREDENTIALS_FILE, help="where to write the password")
    parser.add_argument("--length", type=int, default=22, help="password length (default 22)")
    args = parser.parse_args()

    if not args.create and not args.reset:
        parser.print_help()
        print("\nChoose --create or --reset.", file=sys.stderr)
        return 2
    if args.length < 16:
        print("Refusing to generate a password shorter than 16 characters.", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == SUPERADMIN_EMAIL))

        if args.create and user is not None:
            print(
                f"{SUPERADMIN_EMAIL} already exists (id {user.id}). "
                "Use --reset to issue a new password.",
                file=sys.stderr,
            )
            return 1
        if args.reset and user is None:
            print(f"{SUPERADMIN_EMAIL} does not exist. Use --create.", file=sys.stderr)
            return 1

        password = generate_password(args.length)
        digest = generate_password_hash(password)

        if user is None:
            user = User(
                display_name=SUPERADMIN_NAME,
                email=SUPERADMIN_EMAIL,
                password_hash=digest,
                is_active=True,
                is_platform_admin=True,
                is_synthetic=False,
            )
            db.session.add(user)
            verb = "Created"
        else:
            user.password_hash = digest
            user.is_platform_admin = True
            user.is_active = True
            user.is_synthetic = False
            user.display_name = user.display_name or SUPERADMIN_NAME
            verb = "Reset"

        db.session.commit()

        created = _existing_created(args.file) or datetime.now(timezone.utc).isoformat(timespec="seconds")
        write_credentials_file(args.file, password, created)

        legacy = db.session.scalar(select(User).where(User.email == LEGACY_PLATFORM_ADMIN))
        legacy_note = legacy is not None and legacy.is_active

    print(f"{verb} the Super Admin account.")
    print(f"  login URL : {LOGIN_URL}")
    print(f"  account   : {SUPERADMIN_EMAIL}")
    print(f"  password  : written to {args.file} (mode 600, root only)")
    print(f"  read it   : sudo cat {args.file}")
    print("  the password is not printed here and is never stored in the database")
    if legacy_note:
        print()
        print(f"NOTE: {LEGACY_PLATFORM_ADMIN} is still an active platform admin.")
        print("      Close it after the walkthrough with:")
        print("      sudo -u postgres psql retail_pos_db -c \\")
        print(f"        \"update users set is_active = false where email = '{LEGACY_PLATFORM_ADMIN}';\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
