"""Shared helpers for idempotent POS seed scripts."""
from sqlalchemy import func, select

from app import db


def require_pos_database():
    name = db.session.scalar(select(func.current_database()))
    if name != "retail_pos_db":
        raise RuntimeError("Refusing to write to unexpected database: " + str(name))
    return name


def get_or_create(model, lookups, **defaults):
    found = db.session.scalar(select(model).filter_by(**lookups))
    if found is not None:
        return found
    row = model(**lookups, **defaults)
    db.session.add(row)
    db.session.flush()
    return row
