"""Replace placeholder wording that reached business-facing records.

Earlier seeds stored "Demo Lahore Wholesale", "<business> Demo Owner" and a
receipt footer mentioning course work. Those strings are visible on the
purchasing list, the staff directory and printed receipts, so they are replaced
here with the names a manager would expect to read.

What this script does NOT change:

* email addresses, which are login identifiers and deliberately use the reserved
  `example.invalid` domain;
* password hashes for any account;
* `dataset_manifests` and the reports provenance note, which are the honest record
  that the trading history is synthetic.

Idempotent: running it twice changes nothing the second time.

    .venv/bin/python -m scripts.clean_placeholder_names --dry-run
    .venv/bin/python -m scripts.clean_placeholder_names
"""
import argparse
import sys

from sqlalchemy import select

from app import create_app, db
from app.models import Business, Supplier, User
from app.platform_models import BusinessSetting
from app.seeddata.naming import (
    LEGACY_OWNER_NAMES,
    OWNER_NAMES_BY_EMAIL,
    SUPPLIER_RENAMES,
    receipt_footer_for,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    app = create_app()
    changes = []
    with app.app_context():
        for supplier in db.session.scalars(select(Supplier).order_by(Supplier.id)).all():
            replacement = SUPPLIER_RENAMES.get(supplier.name)
            if replacement and replacement != supplier.name:
                changes.append(f"supplier {supplier.id}: {supplier.name!r} -> {replacement!r}")
                if not args.dry_run:
                    supplier.name = replacement

        for email, display_name in OWNER_NAMES_BY_EMAIL.items():
            user = db.session.scalar(select(User).where(User.email == email))
            if user is None:
                continue
            legacy = LEGACY_OWNER_NAMES.get(email)
            if user.display_name == display_name:
                continue  # already renamed
            changes.append(f"user {user.id}: {user.display_name!r} -> {display_name!r}")
            if not args.dry_run:
                user.display_name = display_name

        for business in db.session.scalars(select(Business).order_by(Business.id)).all():
            settings = db.session.scalar(
                select(BusinessSetting).where(BusinessSetting.business_id == business.id)
            )
            if settings is None:
                continue
            footer = receipt_footer_for(business.business_type)
            if "demo" in settings.receipt_footer.lower() or "sample" in settings.receipt_footer.lower():
                changes.append(
                    f"business_settings {business.id}: {settings.receipt_footer!r} -> {footer!r}"
                )
                if not args.dry_run:
                    settings.receipt_footer = footer

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()

    if not changes:
        print("Nothing to change: no placeholder wording found.")
        return 0
    print(f"{len(changes)} change(s):")
    for line in changes:
        print("  " + line)
    print("Dry run only." if args.dry_run else "Applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
