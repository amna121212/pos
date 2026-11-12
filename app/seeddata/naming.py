"""Business-facing names for the seeded Lahore dataset.

Earlier seeds used placeholder wording ("Demo Lahore Wholesale",
"<business> Demo Owner", a receipt footer mentioning course work). Those names
reached the purchasing list, the staff directory and printed receipts, which is
what made the product look unfinished.

The dataset is still synthetic; that fact belongs in `docs/DATA_PROVENANCE.md`,
`dataset_manifests`, the platform console and the reports note — not in the
name of a supplier a manager reads on a purchase order.
"""
from app.seeddata.catalog import EXTRA_SUPPLIERS

# Old placeholder name -> name shown in the application.
SUPPLIER_RENAMES = {
    "Demo Lahore Wholesale": "Lahore Wholesale Traders",
    "Baghbanwala Poultry Demo Yard": "Baghbanwala Poultry Farm",
    "Canal Road Produce Demo": "Canal Road Produce Market",
    "Gulberg Bakery Supply Demo": "Gulberg Bakery Supplies",
    "Shahdara Grocery Demo Depot": "Shahdara Grocery Depot",
    "Ichhra Cold Store Demo": "Ichhra Cold Storage",
}

PRIMARY_SUPPLIER = SUPPLIER_RENAMES["Demo Lahore Wholesale"]

# Owner display names for the three seeded businesses, keyed by slug.
OWNER_NAMES = {
    "lahore-grill-house": "Imran Qureshi",
    "urban-bites-lahore": "Mariam Shah",
    "daily-mart-lahore": "Adnan Raza",
}

# Old owner display names, so the repair script can find rows by either form.
LEGACY_OWNER_NAMES = {
    "demo-owner-lahore-grill-house@example.invalid": "Lahore Grill House Demo Owner",
    "demo-owner-urban-bites-lahore@example.invalid": "Urban Bites Lahore Demo Owner",
    "demo-owner-daily-mart-lahore@example.invalid": "Daily Mart Lahore Demo Owner",
}

OWNER_NAMES_BY_EMAIL = {
    f"demo-owner-{slug}@example.invalid": name for slug, name in OWNER_NAMES.items()
}

RECEIPT_FOOTERS = {
    "restaurant": "Thank you for dining with us",
    "cafe": "Thank you for visiting",
    "retail": "Thank you for shopping with us",
}

LEGACY_RECEIPT_FOOTER = "Coursework demo receipt. Sample prices are not a market survey."


def receipt_footer_for(business_type):
    return RECEIPT_FOOTERS.get(business_type, RECEIPT_FOOTERS["retail"])


def extra_suppliers(slug):
    """The secondary suppliers for a business, with placeholder wording removed."""
    rows = EXTRA_SUPPLIERS.get(slug, [])
    return [(SUPPLIER_RENAMES.get(name, name), lead) for name, lead in rows]
