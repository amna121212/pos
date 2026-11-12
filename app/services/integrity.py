"""Read-only consistency checks for retail_pos_db.

Each check returns human-readable problem strings. An empty list means the
check passed. These queries do not update the database.
"""
from sqlalchemy import text

from app import db


def _rows(sql, **params):
    return db.session.execute(text(sql), params).all()


def integrity_problems():
    problems = []
    current = db.session.execute(text("SELECT current_database()")).scalar()
    if current != "retail_pos_db":
        problems.append(f"Connected to {current}, expected retail_pos_db")
        return problems
    problems.extend(_payment_problems())
    problems.extend(_cancelled_payment_problems())
    problems.extend(_total_problems())
    problems.extend(_tenant_problems())
    problems.extend(_stock_problems())
    problems.extend(_transfer_problems())
    problems.extend(_tax_problems())
    return problems


def _payment_problems():
    rows = _rows(
        """
        SELECT o.id, o.order_number, o.grand_total,
               COALESCE(SUM(p.amount) FILTER (WHERE p.status = 'captured'), 0) AS paid
        FROM restaurant_orders o
        LEFT JOIN order_payments p ON p.order_id = o.id
        WHERE o.status = 'paid'
        GROUP BY o.id, o.order_number, o.grand_total
        HAVING o.grand_total <> COALESCE(SUM(p.amount) FILTER (WHERE p.status = 'captured'), 0)
        LIMIT 20
        """
    )
    return [f"Paid order {row.order_number} grand {row.grand_total} paid {row.paid}" for row in rows]


def _cancelled_payment_problems():
    rows = _rows(
        """
        SELECT o.order_number
        FROM restaurant_orders o
        JOIN order_payments p ON p.order_id = o.id
        WHERE o.status IN ('cancelled', 'held')
        LIMIT 20
        """
    )
    return [f"{row.order_number} is cancelled or held but has a payment" for row in rows]


def _total_problems():
    rows = _rows(
        """
        SELECT o.order_number
        FROM restaurant_orders o
        WHERE o.grand_total <> (o.subtotal - o.discount_total + o.tax_total)
           OR o.discount_total > o.subtotal
        LIMIT 20
        """
    )
    problems = [f"{row.order_number} totals do not reconcile" for row in rows]
    rows = _rows(
        """
        SELECT o.order_number
        FROM restaurant_orders o
        JOIN (
            SELECT order_id, SUM(line_total) AS lines
            FROM order_items
            GROUP BY order_id
        ) li ON li.order_id = o.id
        LEFT JOIN (
            SELECT oi.order_id, COALESCE(SUM(m.price_at_sale), 0) AS mods
            FROM order_items oi
            LEFT JOIN order_item_modifiers m ON m.order_item_id = oi.id
            GROUP BY oi.order_id
        ) mo ON mo.order_id = o.id
        WHERE o.subtotal <> li.lines + COALESCE(mo.mods, 0)
        LIMIT 20
        """
    )
    problems.extend(f"{row.order_number} subtotal does not match lines" for row in rows)
    return problems


def _tenant_problems():
    checks = [
        (
            "order branch",
            """
            SELECT o.order_number AS label
            FROM restaurant_orders o
            JOIN branches b ON b.id = o.branch_id
            WHERE b.business_id <> o.business_id
            LIMIT 10
            """,
        ),
        (
            "order product",
            """
            SELECT o.order_number AS label
            FROM order_items i
            JOIN restaurant_orders o ON o.id = i.order_id
            JOIN products p ON p.id = i.product_id
            WHERE p.business_id <> o.business_id
            LIMIT 10
            """,
        ),
        (
            "payment method",
            """
            SELECT o.order_number AS label
            FROM order_payments pay
            JOIN restaurant_orders o ON o.id = pay.order_id
            JOIN payment_methods m ON m.id = pay.payment_method_id
            WHERE m.business_id <> o.business_id
            LIMIT 10
            """,
        ),
        (
            "dining session",
            """
            SELECT o.order_number AS label
            FROM restaurant_orders o
            JOIN dining_sessions s ON s.id = o.dining_session_id
            WHERE s.branch_id <> o.branch_id OR s.business_id <> o.business_id
            LIMIT 10
            """,
        ),
        (
            "branch product",
            """
            SELECT bp.id::text AS label
            FROM branch_products bp
            JOIN branches b ON b.id = bp.branch_id
            JOIN products p ON p.id = bp.product_id
            WHERE bp.business_id <> b.business_id OR bp.business_id <> p.business_id
            LIMIT 10
            """,
        ),
    ]
    problems = []
    for name, sql in checks:
        rows = _rows(sql)
        problems.extend(f"{name} tenant mismatch on {row.label}" for row in rows)
    return problems


def _stock_problems():
    rows = _rows(
        """
        SELECT bs.branch_id, bs.item_id, bs.quantity,
               COALESCE(SUM(sm.delta_qty), 0) AS ledger
        FROM branch_stocks bs
        LEFT JOIN stock_movements sm
          ON sm.branch_id = bs.branch_id AND sm.item_id = bs.item_id
        GROUP BY bs.id, bs.branch_id, bs.item_id, bs.quantity
        HAVING bs.quantity <> COALESCE(SUM(sm.delta_qty), 0)
        LIMIT 20
        """
    )
    return [
        f"Stock ledger mismatch branch {row.branch_id} item {row.item_id}: balance {row.quantity} ledger {row.ledger}"
        for row in rows
    ]


def _transfer_problems():
    rows = _rows(
        """
        SELECT reference_code, SUM(delta_qty) AS net
        FROM stock_movements
        WHERE movement_type IN ('transfer_out', 'transfer_in')
        GROUP BY reference_code
        HAVING SUM(delta_qty) <> 0
        LIMIT 20
        """
    )
    return [f"Transfer {row.reference_code} does not conserve quantity ({row.net})" for row in rows]


def _tax_problems():
    rows = _rows(
        """
        SELECT o.order_number
        FROM restaurant_orders o
        JOIN tax_rules t ON t.id = o.tax_rule_id
        WHERE o.tax_total <> round((o.subtotal - o.discount_total) * t.rate_percent / 100, 2)
        LIMIT 20
        """
    )
    return [f"{row.order_number} tax does not match its tax rule" for row in rows]


def preserved_demo_counts():
    """Anchor counts the later phases must not wipe."""
    row = _rows(
        """
        SELECT
          (SELECT COUNT(*) FROM businesses) AS businesses,
          (SELECT COUNT(*) FROM branches) AS branches,
          (SELECT COUNT(*) FROM restaurant_orders WHERE order_number LIKE 'DEMO-%') AS demo_orders
        """
    )[0]
    return {"businesses": row.businesses, "branches": row.branches, "demo_orders": row.demo_orders}
