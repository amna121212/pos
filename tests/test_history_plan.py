"""Money tests that do not need the database."""
from decimal import Decimal

from app.services.history_plan import payment_plan, price_lines
from app.services.pricing import discount_scenarios


def test_order_math_uses_decimal_and_balances():
    lines, totals = price_lines(
        [
            {"unit_price": "650", "quantity": 2, "modifier_amount": "80"},
            {"unit_price": "70", "quantity": 1, "modifier_amount": "0"},
        ],
        discount_kind="percent",
        discount_value="10",
        tax_rate_percent="5",
    )
    assert all(isinstance(line["line_total"], Decimal) for line in lines)
    assert totals["grand"] == totals["subtotal"] - totals["discount"] + totals["tax"]
    assert totals["subtotal"] == Decimal("1450.00")
    assert totals["discount"] == Decimal("145.00")
    assert totals["tax"] == Decimal("65.25")


def test_split_payments_absorb_rounding():
    payments = payment_plan(grand="100.01", status="paid", cash_fraction="0.60")
    assert sum(row["amount"] for row in payments) == Decimal("100.01")
    assert all(isinstance(row["amount"], Decimal) for row in payments)


def test_cancelled_orders_have_no_payments():
    assert payment_plan(grand="500", status="cancelled") == []
    assert payment_plan(grand="500", status="held") == []


def test_discount_guardrail_blocks_a_deep_cut():
    rows = discount_scenarios(
        unit_price="1000",
        unit_cost="700",
        percents=["5", "10", "40"],
        min_margin_pct="15",
    )
    by_percent = {row["percent"]: row["allowed"] for row in rows}
    assert by_percent[Decimal("5.00")] is True
    assert by_percent[Decimal("40.00")] is False
