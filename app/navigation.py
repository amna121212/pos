"""Workspace tabs.

A workspace is a group of routes that belong to one job, such as Inventory. Every
page inside the workspace shows the same tab bar, so moving between tabs never
loses the other tabs. The active tab comes from `request.endpoint`.
"""
from flask import request, url_for
from werkzeug.routing import BuildError

from app.security import has_permission

# Each entry: (visible label, endpoint, extra permission needed or None).
WORKSPACES = [
    (
        "inventory",
        (
            ("Stock", "inventory.index", None),
            ("Ingredients", "inventory.ingredients", None),
            ("Recipes", "inventory.recipes", None),
            ("Movements", "inventory.movements", None),
            ("Adjust", "inventory.adjust", "inventory.adjust"),
            ("Transfers", "inventory.transfers", "inventory.transfer"),
        ),
        (
            "inventory.index",
            "inventory.ingredients",
            "inventory.movements",
            "inventory.adjust",
            "inventory.recipes",
            "inventory.transfers",
            "inventory.transfer_new",
            "inventory.ingredient_new",
            "inventory.ingredient_edit",
            "inventory.recipe_new",
            "inventory.recipe_edit",
        ),
    ),
    (
        "purchasing",
        (
            ("Purchase orders", "inventory.purchases", "inventory.purchase"),
            ("Suppliers", "suppliers.index", "inventory.purchase"),
        ),
        (
            "inventory.purchases",
            "inventory.purchase_new",
            "suppliers.index",
            "suppliers.detail",
            "suppliers.new",
            "suppliers.edit",
        ),
    ),
    (
        "menu",
        (
            ("Items", "catalog.products", None),
            ("Categories", "catalog.categories", None),
        ),
        (
            "catalog.products",
            "catalog.product_new",
            "catalog.product_edit",
            "catalog.categories",
        ),
    ),
    (
        "orders",
        (
            ("All orders", "orders.index", None),
            ("Kitchen", "kitchen.index", None),
            ("Returns", "orders.returns", "order.refund"),
        ),
        (
            "orders.show",
            "orders.receipt",
            "orders.returns",
            "kitchen.index",
        ),
    ),
    (
        "settings",
        (
            ("Business", "admin.settings", None),
            ("Payment methods", "admin.payment_methods", "business.settings"),
            ("Shifts", "admin.shifts", "shift.manage"),
            ("Audit log", "admin.audit", None),
        ),
        (
            "admin.settings",
            "admin.payment_methods",
            "admin.shifts",
            "admin.shift_open",
            "admin.audit",
        ),
    ),
    (
        "reports",
        (
            ("Reports", "reports.index", "report.view"),
            ("Insights", "insights.index", "ai.view"),
        ),
        ("reports.index", "insights.index"),
    ),
    (
        "branches",
        (
            ("Directory", "admin.branches", None),
            ("Restaurants", "restaurants.index", None),
        ),
        (
            "admin.branches",
            "admin.branch_new",
            "restaurants.index",
            "restaurants.detail",
        ),
    ),
]

# Endpoints that own a richer, page-specific tab bar (status filters, for example).
# They render their own tabs, so the shared bar stays out of the way.
OWN_TABS = {"orders.index"}

# Form and detail pages belong to a tab, so that tab stays highlighted on them.
ALIASES = {
    "inventory.ingredient_new": "inventory.ingredients",
    "inventory.ingredient_edit": "inventory.ingredients",
    "inventory.recipe_new": "inventory.recipes",
    "inventory.recipe_edit": "inventory.recipes",
    "inventory.transfer_new": "inventory.transfers",
    "inventory.purchase_new": "inventory.purchases",
    "catalog.product_new": "catalog.products",
    "catalog.product_edit": "catalog.products",
    "suppliers.detail": "suppliers.index",
    "suppliers.new": "suppliers.index",
    "suppliers.edit": "suppliers.index",
    "admin.shift_open": "admin.shifts",
    "admin.branch_new": "admin.branches",
    "restaurants.detail": "restaurants.index",
    "orders.show": "orders.index",
    "orders.receipt": "orders.index",
}


def workspace_tabs():
    """Return [(label, url, is_active)] for the current page, or [] when there is none."""
    endpoint = request.endpoint or ""
    if endpoint in OWN_TABS:
        return []

    current = ALIASES.get(endpoint, endpoint)

    for _name, tabs, endpoints in WORKSPACES:
        if endpoint not in endpoints:
            continue
        rows = []
        for label, target, permission in tabs:
            if permission and not has_permission(permission):
                continue
            try:
                url = url_for(target)
            except BuildError:
                continue
            rows.append((label, url, target == current))
        return rows if len(rows) > 1 else []

    return []
