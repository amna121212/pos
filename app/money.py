"""Money helpers. Currency in this project is PKR, stored as PostgreSQL NUMERIC.

Python Decimal is the only type used for money. Float is intentionally unused.
Quantities that are not money use three decimal places (kilograms, litres).
"""
from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")
THREEPLACES = Decimal("0.001")


def money(value):
    """Round a rupee amount half-up to paisas."""
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def quantity(value):
    """Round a stock quantity to three decimal places."""
    return Decimal(str(value)).quantize(THREEPLACES, rounding=ROUND_HALF_UP)
