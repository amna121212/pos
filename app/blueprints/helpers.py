"""Small helpers shared by the view modules."""
from datetime import date, datetime, timedelta

from flask import abort, current_app, request
from sqlalchemy import func, select

from app import db


def parse_date(value, fallback=None):
    if not value:
        return fallback
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return fallback


def int_arg(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def decimal_arg(name, default=0):
    raw = request.form.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return default


def page_args():
    page = int_arg("page", 1, minimum=1) or 1
    size = current_app.config["PAGE_SIZE"]
    return page, size, (page - 1) * size


def total_pages(count, size):
    if count <= 0:
        return 1
    return (count + size - 1) // size


def period_args(default_days=30):
    """Read start/end from the query string, defaulting to the last N days."""
    today = date.today()
    end = parse_date(request.args.get("end"), today)
    start = parse_date(request.args.get("start"), end - timedelta(days=default_days - 1))
    if start > end:
        start, end = end, start
    if (end - start).days > 366:
        start = end - timedelta(days=365)
    return start, end


def branch_scope():
    """Branch ids the signed-in user may read, or every branch when unpicked."""
    from app.security import context

    return context().allowed_branch_ids


def require_tenant():
    from app.security import require_business_id

    return require_business_id()


def count_rows(model, *conditions):
    return int(db.session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def get_or_404(model, identifier):
    row = db.session.get(model, identifier)
    if row is None:
        abort(404)
    return row
