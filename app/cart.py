"""The till basket, kept in the signed session.

Only product ids, quantities and modifier option ids are stored. Prices are
always looked up again from branch_products at render and checkout time, so a
tampered cookie or stale page can never set the amount charged.
"""
from flask import session

STORE_KEY = "cart"


def _empty():
    return {"lines": []}


def get_cart():
    cart = session.get(STORE_KEY)
    if not isinstance(cart, dict) or "lines" not in cart:
        cart = _empty()
        session[STORE_KEY] = cart
    return cart


def _save(cart):
    session[STORE_KEY] = cart
    session.modified = True


def clear():
    session[STORE_KEY] = _empty()
    session.modified = True


reset_cart = clear


def line_key(product_id, option_ids):
    return f"{int(product_id)}:{','.join(str(int(option)) for option in sorted(option_ids))}"


def add_line(product_id, qty, option_ids=(), note=""):
    cart = get_cart()
    qty = max(1, int(qty))
    options = sorted({int(option) for option in option_ids})
    key = line_key(product_id, options)
    for line in cart["lines"]:
        if line_key(line["product_id"], line.get("options", [])) == key:
            line["qty"] = min(999, line["qty"] + qty)
            _save(cart)
            return line
    line = {"product_id": int(product_id), "qty": qty, "options": options, "note": (note or "")[:150]}
    cart["lines"].append(line)
    _save(cart)
    return line


def set_qty(key, qty):
    cart = get_cart()
    qty = int(qty)
    if qty <= 0:
        return remove_line(key)
    for line in cart["lines"]:
        if line_key(line["product_id"], line.get("options", [])) == key:
            line["qty"] = min(999, qty)
            _save(cart)
            return line
    return None


def remove_line(key):
    cart = get_cart()
    cart["lines"] = [line for line in cart["lines"] if line_key(line["product_id"], line.get("options", [])) != key]
    _save(cart)
    return None


def is_empty():
    return not get_cart()["lines"]
