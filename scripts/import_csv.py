"""Import a student CSV into retail_pos_db.

Example:
  python -m scripts.import_csv --kind products --file data/csv_examples/products.csv --dry-run
"""
import argparse
import json

from app import create_app
from app.services.csv_import import import_file
from scripts.common import require_pos_database


def main():
    parser = argparse.ArgumentParser(description="Validate and import a POS CSV file")
    parser.add_argument("--kind", required=True, choices=[
        "businesses", "branches", "categories", "products", "branch_prices",
        "ingredients", "recipes", "suppliers", "staff", "opening_inventory",
    ])
    parser.add_argument("--file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        require_pos_database()
        result = import_file(args.file, args.kind, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    if result["status"] == "rejected":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
