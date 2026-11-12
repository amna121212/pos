"""Jinja filters. Display formatting only; no business rules live here."""
from datetime import datetime, timezone

from markupsafe import Markup, escape

from app.money import money
from app.timeutil import as_pakistan


def pkr(value):
    """Format a Decimal rupee amount as Rs 1,234.50."""
    if value is None or value == "":
        return Markup("&mdash;")
    amount = money(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}Rs {abs(amount):,.2f}"


def qty(value):
    """Stock quantity with up to three decimals and no trailing zeros."""
    if value is None:
        return Markup("&mdash;")
    number = float(value)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.3f}".rstrip("0").rstrip(".")


def localtime(value, pattern="%d %b %Y, %H:%M"):
    """Render a stored UTC instant in Pakistan time."""
    if value is None:
        return Markup("&mdash;")
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return as_pakistan(moment).strftime(pattern)
    return value.strftime(pattern)


def localdate(value):
    return localtime(value, "%d %b %Y")


def clock(value):
    return localtime(value, "%H:%M")


def timesince(value):
    """Short relative time such as 4m or 2h, for the kitchen board."""
    if value is None:
        return Markup("&mdash;")
    moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - moment).total_seconds())
    if seconds < 60:
        return f"{max(seconds, 0)}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def status_badge(status):
    """Map a lifecycle status to a CSS modifier."""
    mapping = {
        "paid": "ok",
        "open": "info",
        "held": "warn",
        "partially_paid": "warn",
        "cancelled": "muted",
        "voided": "muted",
        "queued": "info",
        "preparing": "warn",
        "ready": "ok",
        "served": "ok",
        "posted": "ok",
        "draft": "muted",
        "received": "ok",
        "sent": "info",
        "printed": "ok",
        "failed": "bad",
        "pending": "warn",
        "approved": "ok",
        "rejected": "bad",
    }
    return mapping.get((status or "").lower(), "muted")


def label(value):
    """cost_price -> Cost price."""
    if not value:
        return ""
    return str(value).replace("_", " ").capitalize()


def initials(name):
    if not name:
        return "?"
    parts = [part for part in str(name).split() if part]
    return "".join(part[0] for part in parts[:2]).upper()


def cart_key(line):
    """Stable identifier for one basket line, matching app.cart.line_key."""
    options = sorted(option.id for option in line.get("options") or [])
    return f"{line['product_id']}:{','.join(str(option) for option in options)}"


def register_filters(app):
    app.jinja_env.filters.update(
        {
            "pkr": pkr,
            "qty": qty,
            "localtime": localtime,
            "localdate": localdate,
            "clock": clock,
            "timesince": timesince,
            "badge": status_badge,
            "label": label,
            "initials": initials,
            "cartkey": cart_key,
        }
    )
    app.jinja_env.globals["escape"] = escape
