"""Write docs/DATABASE_DICTIONARY.md from the live SQLAlchemy metadata."""
from pathlib import Path

from sqlalchemy import inspect

from app import create_app, db

PURPOSES = {
    "businesses": "A tenant on the POS platform. One restaurant or shop, not one database.",
    "branches": "A selling location owned by one business. Staff, stock and prices can differ here.",
    "users": "A person who can sign in. Demo people are marked synthetic and use example.invalid.",
    "business_users": "Grants a user a role at a business, optionally limited to one branch.",
    "categories": "Menu or shelf grouping inside one business.",
    "products": "A sellable menu item or retail SKU. It is not the same thing as a raw ingredient.",
    "branch_products": "Branch price and availability for a product defined by the parent business.",
    "dining_tables": "A physical table at a restaurant branch.",
    "payment_methods": "Cash, card or transfer offered by one business.",
    "suppliers": "A fictional supplier account used for purchases and lead time.",
    "printers": "Receipt, kitchen or label printer configured at a branch, including 58mm and 80mm widths.",
    "cash_registers": "A counter drawer at a branch.",
    "dining_sessions": "A seating at one table. Several orders could share it; this demo uses one.",
    "restaurant_orders": "A ticket: dine-in, takeaway, counter pickup or delivery. Posted totals are not deleted.",
    "order_items": "One sold product line. unit_price is the branch price captured at sale time.",
    "menu_modifier_groups": "An optional choice group such as spice level or burger add-ons.",
    "menu_modifier_options": "One choice inside a modifier group, with an extra price.",
    "order_item_modifiers": "The choice actually taken on a line, priced at the time of sale.",
    "kitchen_tickets": "The kitchen copy of a paid restaurant ticket.",
    "kitchen_ticket_items": "Preparation status for one order line on a kitchen ticket.",
    "order_discounts": "A discount amount that was actually applied to a ticket.",
    "order_payments": "A captured tender. Split payments are several rows. The sum cannot exceed the grand total.",
    "order_status_events": "Status history. Cancelled tickets stay in this history.",
    "receipt_records": "One receipt per paid ticket. Finalising it again returns the same row.",
    "inventory_items": "A stocked ingredient or retail unit. Restaurant plates are not stocked here.",
    "branch_stocks": "Current on-hand quantity. It must match the sum of stock movements.",
    "stock_batches": "A received batch, with an expiry date when the ingredient has a demo shelf life.",
    "stock_movements": "The stock ledger. Quantity changes only by inserting a movement.",
    "stock_adjustments": "A counted correction. The ledger row uses the same adjustment code.",
    "supplier_purchase_orders": "An order placed with a supplier for one receiving branch.",
    "supplier_purchase_items": "A line on a purchase order: item, quantity and unit cost.",
    "goods_receipts": "Proof that a purchase was received at a branch.",
    "goods_receipt_items": "How much of each purchase line was received.",
    "stock_transfer_requests": "A move between two branches of the same business.",
    "stock_transfer_items": "The quantity of one item on a transfer.",
    "stock_transfer_events": "Requested, approved, dispatched and received notes for a transfer.",
    "subscription_plans": "Platform plan with a coursework monthly fee in PKR.",
    "business_subscriptions": "The current plan for one business. Changing it updates this row.",
    "business_settings": "Currency, Pakistan timezone, fictional trading start and margin floor.",
    "branch_operating_hours": "Opening hours for each weekday. Stored as local times, not as sales.",
    "roles": "Named roles: platform admin, owner, manager, cashier, kitchen, inventory.",
    "permissions": "An action the server may allow, such as order.refund.",
    "role_permissions": "Which permissions a role has.",
    "tax_rules": "Illustrative tax rate. Not an FBR or PRA quotation.",
    "recipes": "How one serving of a menu product is made from ingredients.",
    "recipe_lines": "Ingredient quantity for one recipe, in the ingredient's stock unit.",
    "kitchen_stations": "A prep area in a branch, such as the grill or the pizza oven.",
    "product_station_routes": "Which station cooks a product at a branch.",
    "order_fulfillments": "How the guest receives the ticket: table, counter, takeaway or a synthetic delivery drop.",
    "cashier_shifts": "One cashier session on one register, with an opening float.",
    "cash_movements": "Cash in or out of a shift. The amount is always positive; the type gives the direction.",
    "shift_reconciliations": "Counted cash compared with the shift ledger. Variance is kept, not deleted.",
    "print_jobs": "A receipt, kitchen or barcode print, with retry attempts.",
    "printer_issue_reports": "A paper-out or other printer problem linked to a job when one exists.",
    "product_barcodes": "Synthetic internal barcode. These are not GS1 registrations.",
    "scanner_sessions": "A paired camera or USB keyboard-wedge session at a branch.",
    "sales_returns": "A posted refund or even exchange. Void it instead of deleting it.",
    "sales_return_lines": "The returned line and, for an exchange, the replacement product.",
    "discount_approvals": "Manager approval or rejection of a discount. Rejected amounts are not applied.",
    "audit_events": "Append-only note of a meaningful action.",
    "dataset_manifests": "Where a dataset came from: curated, generated or synthetic history.",
    "ai_analysis_runs": "One deterministic snapshot pass. Grok is not called here.",
    "product_performance_snapshots": "Branch product quantity, revenue and estimated gross profit for a run.",
    "ai_recommendations": "Rule-written suggestions. They explain stored figures; they do not invent them.",
    "recommendation_feedback": "A person's response to a stored recommendation.",
}


def main():
    app = create_app()
    lines = [
        "# Database dictionary",
        "",
        "The POS uses one PostgreSQL database, `retail_pos_db`.",
        "A business is a tenant. A branch belongs to that business.",
        "Money is `NUMERIC` and timezone-aware timestamps are stored in UTC.",
        "Display times in Asia/Karachi.",
        "",
        "Posted sales, payments, receipts, returns and stock movements are not hard-deleted.",
        "The application voids, reverses or deactivates them instead.",
        "Foreign keys use `ON DELETE RESTRICT`, so a parent with children cannot be removed.",
        "",
    ]
    with app.app_context():
        inspector = inspect(db.engine)
        tables = sorted(name for name in inspector.get_table_names() if name != "alembic_version")
        lines.append(f"Application tables: {len(tables)}.")
        lines.append("")
        for name in tables:
            lines.append(f"## `{name}`")
            lines.append("")
            lines.append(PURPOSES.get(name, "Application table."))
            lines.append("")
            lines.append("| Column | Type | Nullable |")
            lines.append("| --- | --- | --- |")
            for column in inspector.get_columns(name):
                lines.append(f"| {column['name']} | {column['type']} | {column['nullable']} |")
            fks = inspector.get_foreign_keys(name)
            if fks:
                lines.append("")
                lines.append("Foreign keys:")
                for fk in fks:
                    cols = ", ".join(fk["constrained_columns"])
                    target = fk["referred_table"] + "(" + ", ".join(fk["referred_columns"]) + ")"
                    lines.append(f"- {cols} -> {target}")
            lines.append("")
    path = Path("/opt/student-projects/pos/docs/DATABASE_DICTIONARY.md")
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines))
    print(f"Wrote {path} ({len(tables)} tables)")


if __name__ == "__main__":
    main()
