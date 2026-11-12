"""Pure helpers for the synthetic history generator.

Nothing here talks to the database. The seed script supplies branch prices
and a deterministic random.Random instance.
"""
from decimal import Decimal

from app.money import money
from app.services.orders import compute_discount, order_totals


def weighted_choice(rng, rows, weight_of):
    pool = [row for row in rows if weight_of(row) > 0]
    if not pool:
        raise ValueError("No selectable rows")
    total = sum(weight_of(row) for row in pool)
    pick = rng.randrange(total)
    running = 0
    for row in pool:
        running += weight_of(row)
        if pick < running:
            return row
    return pool[-1]


def choose_status(rng):
    roll = rng.random()
    if roll < 0.03:
        return "cancelled"
    if roll < 0.04:
        return "held"
    if roll < 0.05:
        return "partially_paid"
    return "paid"


def choose_order_type(rng, kind):
    if kind != "restaurant":
        return "counter_pickup" if rng.random() < 0.75 else "takeaway"
    roll = rng.random()
    if roll < 0.55:
        return "dine_in"
    if roll < 0.80:
        return "takeaway"
    if roll < 0.92:
        return "counter_pickup"
    return "delivery"


def price_lines(lines, *, discount_kind, discount_value, tax_rate_percent):
    """Price lines and return totals. Each line needs unit_price, quantity, modifier_amount."""
    priced = []
    subtotal = money(0)
    for line in lines:
        line_total = money(money(line["unit_price"]) * int(line["quantity"]))
        modifier_amount = money(line.get("modifier_amount", 0))
        subtotal = money(subtotal + line_total + modifier_amount)
        priced.append({**line, "line_total": line_total, "modifier_amount": modifier_amount})
    discount = compute_discount(subtotal, discount_kind, discount_value) if discount_kind else money(0)
    totals = order_totals(subtotal=subtotal, discount=discount, tax_rate_percent=tax_rate_percent)
    return priced, totals


def payment_plan(*, grand, status, cash_fraction=None, card_code="card"):
    """Build payment rows. Paid plans sum to the grand total. The last slice absorbs rounding."""
    grand = money(grand)
    if status in ("cancelled", "held") or grand <= 0:
        return []
    if status == "partially_paid":
        amount = money(grand * Decimal("0.50"))
        if amount <= 0 or amount >= grand:
            return [{"code": "cash", "amount": grand, "partial": False}]
        return [{"code": "cash", "amount": amount, "partial": True}]
    if cash_fraction is None:
        return [{"code": "cash", "amount": grand, "partial": False}]
    cash_fraction = Decimal(str(cash_fraction))
    cash_amount = money(grand * cash_fraction)
    card_amount = money(grand - cash_amount)
    rows = []
    if cash_amount > 0:
        rows.append({"code": "cash", "amount": cash_amount, "partial": False})
    if card_amount > 0:
        rows.append({"code": card_code, "amount": card_amount, "partial": False})
    return rows
