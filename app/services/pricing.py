"""Discount scenarios and the minimum-margin guardrail. All figures are Decimal PKR."""
from app.money import money


def gross_margin_pct(price, cost):
    price = money(price)
    cost = money(cost)
    if price <= 0:
        return None
    return money((price - cost) / price * money(100))


def discount_scenarios(*, unit_price, unit_cost, percents, min_margin_pct):
    """Compare a few percentage discounts. A scenario is allowed when margin stays at or above the guardrail."""
    unit_price = money(unit_price)
    unit_cost = money(unit_cost)
    floor = money(min_margin_pct)
    rows = []
    for percent in percents:
        percent = money(percent)
        discounted = money(unit_price * (money(100) - percent) / money(100))
        profit = money(discounted - unit_cost)
        margin = gross_margin_pct(discounted, unit_cost)
        allowed = margin is not None and margin >= floor
        rows.append(
            {
                "percent": percent,
                "discounted_price": discounted,
                "gross_profit": profit,
                "gross_margin_pct": margin,
                "allowed": allowed,
            }
        )
    return rows
