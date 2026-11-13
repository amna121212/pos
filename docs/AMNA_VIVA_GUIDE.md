# Amna POS — Viva Guide

A short guide to explain this project in your own words. Every code snippet below is
copied from the real project, with the file name and line area so you can open it
during the viva.

---

## 1. What is this project?

**Amna POS** is a web based Point of Sale system for restaurants that have more than one
branch. It is built with Python (Flask), a PostgreSQL database, and normal HTML pages.

One installation serves many restaurants. Each restaurant has branches. Each branch
sells its own menu, keeps its own stock, has its own staff and its own cash drawer.

**Main features**

| Feature | What it does |
| --- | --- |
| Sign in | Email + password, one account can belong to one restaurant |
| Restaurant / branch switch | Top bar picker; the whole app follows the chosen branch |
| Billing (till) | Pick items, add discount, take payment, print receipt |
| Orders | List, filter, open a bill, hold, resume, cancel, refund |
| Kitchen | Tickets move queued → preparing → ready → served |
| Menu | Products and categories, price per branch, modifiers |
| Inventory | Ingredients, stock per branch, movements, adjustments, transfers |
| Recipes | How much of each ingredient one sold item uses |
| Purchasing | Suppliers, purchase orders, goods received |
| Reports | 16 sections, filters kept in the URL, comparison with the previous period |
| Staff / Shifts | Employees and roles, cash drawer open/close with variance |
| Audit log | Every important action is recorded |
| Super admin | Platform console that can see every restaurant |

**Numbers (from the live database):** 66 tables, 86,579 orders, 680 products,
17 businesses, 63 branches.

---

## 2. Important files

| File | Purpose |
| --- | --- |
| `wsgi.py` | Entry point. Gunicorn imports this; it creates the app |
| `app/__init__.py` | `create_app()` — builds the Flask app, config, CSRF hook, blueprints |
| `app/config.py` | Reads database URL and secret key from environment |
| `app/security.py` | Who is logged in, which restaurant/branch, permissions |
| `app/models.py` | Business, Branch, Product, Category, User, PaymentMethod … |
| `app/order_models.py` | RestaurantOrder, OrderItem, OrderPayment, KitchenTicket |
| `app/inventory_models.py` | InventoryItem, BranchStock, StockMovement, purchase orders |
| `app/recipe_models.py` | Recipe, RecipeLine |
| `app/operations_models.py` | CashierShift, ShiftReconciliation, SalesReturn, AuditEvent |
| `app/blueprints/*.py` | One file per area: `pos`, `orders`, `catalog`, `inventory`, `reports`, `admin`, `auth` … |
| `app/services/*.py` | Business logic: `pos_orders`, `orders`, `inventory`, `reporting`, `audit` |
| `app/templates/` | Jinja2 HTML pages |
| `app/static/css/app.css` | The only stylesheet |
| `app/static/js/` | `till.js`, `reports.js` — small vanilla scripts |
| `tests/` | 88 pytest tests |
| `migrations/` | Alembic database migrations |

**Blueprints (14):** `auth`, `dashboard`, `pos`, `orders`, `kitchen`, `catalog`,
`inventory`, `suppliers`, `reports`, `insights`, `restaurants`, `admin`, `platform`,
`helpers`.

---

## 3. How Flask, SQLAlchemy, PostgreSQL and Jinja2 work together

```
Browser
  │  GET /orders
  ▼
Flask (wsgi.py → create_app)
  │  1. before_request: check CSRF token
  │  2. load_context(): who is logged in, which business/branch
  │  3. route in app/blueprints/orders.py runs
  ▼
SQLAlchemy (Model classes)
  │  select(RestaurantOrder).where(...)   ← Python, not SQL text
  ▼
PostgreSQL (retail_pos_db)
  │  returns rows
  ▼
Python turns rows into template variables
  ▼
Jinja2 (app/templates/orders/index.html) fills the HTML
  ▼
Browser shows the page
```

- **Flask** receives the request and decides which Python function runs (the route).
- **SQLAlchemy** lets us write `select(RestaurantOrder).where(...)` instead of SQL.
  Each model class (`RestaurantOrder`) is one table.
- **PostgreSQL** stores everything and does the counting and summing.
- **Jinja2** is the template engine. `{{ order.grand_total|pkr }}` prints a value, and
  `{% for order in orders %}` repeats HTML. `{% extends "base.html" %}` means every page
  reuses the same shell.

Example of the last step — the template filter that formats money
(`app/filters.py`):

```python
def pkr(value):
    """Format a Decimal rupee amount as Rs 1,234.50."""
    if value is None or value == "":
        return Markup("&mdash;")
    amount = money(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}Rs {abs(amount):,.2f}"
```

So in the template, `{{ quote.grand|pkr }}` prints `Rs 1,354.50`.

---

## 4. Important database tables and relationships

```
businesses ──< branches ──< branch_products >── products >── categories
     │             │                              │
     │             │                              └──< recipes ──< recipe_lines
     │             │                                                │
     │             ├──< branch_stocks >────────────────────────── inventory_items
     │             │
     │             ├──< cashier_shifts ──1 shift_reconciliations
     │             │
     │             └──< restaurant_orders ──< order_items
     │                          │            ──< order_payments >── payment_methods
     │                          │            ──1 receipt_records
     │                          │            ──< kitchen_tickets ──< kitchen_ticket_items
     │                          └────────────── sales_returns
     │
     ├──< business_users >── users
     ├──< suppliers ──< supplier_purchase_orders ──< supplier_purchase_items
     ├──  tax_rules, business_settings
     └──< audit_events
```

| Table | One row means | Important columns |
| --- | --- | --- |
| `businesses` | one restaurant | `name`, `business_type`, `is_demo` |
| `branches` | one location | `business_id`, `code`, `name`, `area`, `city` |
| `products` | one menu item | `business_id`, `sku`, `name`, `category_id`, `kind` |
| `branch_products` | price of that item at that branch | `branch_id`, `product_id`, `sale_price`, `is_available` |
| `restaurant_orders` | one bill | `branch_id`, `order_number`, `order_type`, `status`, `subtotal`, `tax_total`, `grand_total` |
| `order_items` | one line on the bill | `order_id`, `product_id`, `quantity`, `unit_price`, `line_total` |
| `order_payments` | one payment against a bill | `order_id`, `payment_method_id`, `amount`, `status` |
| `inventory_items` | one ingredient | `sku`, `name`, `unit`, `reorder_level` |
| `branch_stocks` | current stock at a branch | `branch_id`, `item_id`, `quantity` |
| `stock_movements` | one stock change (ledger) | `movement_type`, `delta_qty`, `reference_code` |
| `recipes` / `recipe_lines` | how a product is made | `product_id`, `inventory_item_id`, `quantity` |
| `users` / `business_users` | login + membership | `email`, `password_hash`, `role`, `branch_id` |
| `roles` / `permissions` / `role_permissions` | who may do what | `role`, `code` |
| `audit_events` | who did what and when | `action`, `entity_type`, `actor_user_id` |

**Three rules in the data model**

1. Almost every table has `business_id` (and often `branch_id`). That is what keeps two
   restaurants apart.
2. Foreign keys are `ON DELETE RESTRICT` — a row that is used by something else cannot
   be deleted. This is why "delete" sometimes says *disable it instead*.
3. Money is `NUMERIC(12,2)`, never a float. Python reads it as `Decimal`.

---

## 5. Workflows

### 5.1 Login

1. `GET /login` shows the form with a hidden `_csrf` token.
2. `POST /login` → `auth.login()` looks the user up by email and checks the password
   hash with `check_password_hash`.
3. On success it writes `session["uid"]` (and `bid` / `branch_id` from the membership).
4. `load_context()` is called; every later request rebuilds the context from the session.

### 5.2 Billing (till)

```
pick item → POST /pos/add → saved in the session cart (app/cart.py)
          → quote() prices the cart (subtotal, discount, tax)
          → Take payment → POST /pos/checkout
          → create_order() writes the order, items, payment
          → stock is reduced through recipes
          → receipt + kitchen ticket are created
          → redirect to the receipt page
```

The cart lives in the browser session, not in the database. Only a finished sale is
written to the database.

### 5.3 Orders

`GET /orders` lists bills for the current branch with optional status, order number and
date filters. Opening a bill (`GET /orders/<id>`) shows its items, payments, history and
the actions allowed by the account's permissions (pay, hold, resume, cancel, refund).

### 5.4 Payments

A payment is a row in `order_payments` with a status (`captured`, `refunded`).
`captured_total()` sums the captured rows and compares it with `grand_total`:
paid in full → order status `paid`; partially paid → `partially_paid`.

### 5.5 Inventory

Selling does not change stock directly. `create_order()` reads the recipe of each
product, and for every ingredient calls `apply_stock_delta()`. That function writes one
row in `stock_movements` and adjusts `branch_stocks.quantity`. The same function is used
by adjustments, purchases and transfers, so there is only one place that can change
stock.

### 5.6 Reports

`GET /reports` sends the page shell plus the filter values. `reports.js` then calls
`GET /reports/api/data?section=...` and fills the sections with JSON. Filters are read by
`resolve_filters()` in this order: **URL → session → defaults**, so a refresh or a
back button keeps the same report.

---

## 6. Ten important functions (with real code)

### 1. `create_app()` — `app/__init__.py` (line 118)

Builds the application. This is the "factory" pattern: nothing is created at import
time, so tests can make their own app.

```python
def create_app():
    load_credentials_into_environment()
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri()
    app.config["SECRET_KEY"] = _secret_key(app)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 12

    db.init_app(app)
    from app import models  # noqa: F401 - register every model on metadata
    migrate.init_app(app, db)

    _register_template_helpers(app)
    _register_request_hooks(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    return app
```

**Say this:** "Flask app factory hai. Config set karta hai, database aur migrations
attach karta hai, phir helpers, hooks aur blueprints register karta hai."

### 2. `_enforce_csrf()` — `app/__init__.py` (line 165)

Runs before every request that can change data. Without the token from the form, the
request is rejected.

```python
@app.before_request
def _enforce_csrf():
    """Reject state changes without the session form token."""
    if request.method in SAFE_METHODS:
        return None
    expected = session.get("_csrf")
    supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, description="Your form session expired. Reload the page and try again.")
```

**Say this:** "CSRF attack se bachne ke liye har POST form mein token aata hai, aur
server `compare_digest` se check karta hai."

### 3. `login()` — `app/blueprints/auth.py` (line 44)

```python
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = db.session.scalar(select(User).where(User.email == email))
        if user is None or not user.is_active or not check_password_hash(user.password_hash, password):
            flash("Email or password is not correct.", "error")
            return render_template("auth/login.html", email=email), 401

        session.clear()
        session.permanent = True
        session["uid"] = user.id
        ...
        load_context()
        return redirect(url_for("dashboard.index"))
```

**Say this:** "Password hash se compare hota hai, plain password save nahi hota.
Login ke baad session mein user id jaati hai."

### 4. `load_context()` — `app/security.py` (line 62)

Decides who the user is, which restaurant and branch they are working in, and what they
may do. It is cached on `flask.g` for the request.

```python
def load_context():
    """Build the request context once and cache it on flask.g."""
    cached = g.get("ctx")
    if cached is not None and g.get("ctx_key") == _fingerprint():
        return cached
    g.ctx = _build_context()
    g.ctx_key = _fingerprint()
    return g.ctx


def _fingerprint():
    return (session.get("uid"), session.get("bid"), session.get("branch_id"))
```

**Say this:** "Har request par context banta hai — user, business, branch, permissions.
Cache ki key session values hain, is liye branch switch karne par purana context nahi
rehta."

### 5. `permission_required()` — `app/security.py` (line 272)

A decorator. Any route can demand a permission.

```python
def permission_required(code):
    """Server-side permission gate. Permissions come from role_permissions."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            ctx = load_context()
            if not ctx.authenticated:
                return redirect(url_for("auth.login"))
            if code not in ctx.permissions:
                abort(403, description="This account does not have the required permission.")
            return view(*args, **kwargs)

        return wrapped

    return decorator
```

Used like this: `@bp.post("/payment-methods/new")` + `@permission_required("business.settings")`.

**Say this:** "Permission server par check hoti hai, sirf button hide karne se kaam nahi
chalta. 14 permission codes hain jaise `order.discount`, `inventory.adjust`,
`report.view`."

### 6. `quote()` — `app/services/pos_orders.py` (line 108)

Prices the cart: item prices, discount, tax, total. No database writes — it only
calculates.

```python
def quote(*, business_id, branch_id, lines, discount_kind=None, discount_value=0):
    """Everything the cart panel needs to render, including tax and discount."""
    priced = price_lines(business_id=business_id, branch_id=branch_id, lines=lines)
    subtotal = money(sum((line["line_total"] for line in priced), money(0)))
    rule = active_tax_rule(business_id)
    rate = money(rule.rate_percent) if rule is not None else money(0)

    discount = money(0)
    if discount_kind in ("percent", "fixed") and money(discount_value) > 0:
        discount = compute_discount(subtotal, discount_kind, discount_value)

    totals = order_totals(subtotal=subtotal, discount=discount, tax_rate_percent=rate)
    return {
        "lines": priced,
        "subtotal": subtotal,
        "discount": totals["discount"],
        "tax": totals["tax"],
        "grand": totals["grand"],
        ...
    }
```

The maths itself is in `order_totals()` in `app/services/orders.py`:

```python
def order_totals(*, subtotal, discount, tax_rate_percent):
    """Return discount, tax and grand total as Decimal rupees."""
    subtotal = money(subtotal)
    discount = money(discount)
    if discount > subtotal:
        raise PaymentError("Discount cannot exceed the subtotal")
    taxable = subtotal - discount
    tax = money(taxable * money(tax_rate_percent) / money(100))
    grand = money(taxable + tax)
    return {"subtotal": subtotal, "discount": discount, "tax": tax, "grand": grand}
```

**Say this:** "Pehle discount lagta hai, uske baad tax. Isi liye `tax = (subtotal −
discount) × rate / 100`. Sab `Decimal` mein hai, float mein nahi, warna paisa round
galat ho jata."

### 7. `create_order()` — `app/services/pos_orders.py` (line 201)

The most important function. It writes one complete sale (excerpt — the `try:`
block and the payment/stock steps after the order row are shortened with `...`).

```python
def create_order(*, business_id, branch, order_type, lines, table_id=None,
                 discount_kind=None, discount_value=0, payment_method_id=None,
                 amount_paid=None, note="", cashier_shift_id=None, actor_user_id=None):
    """Create and optionally settle one order. Commits on success, rolls back on failure."""
    if order_type not in ORDER_TYPES:
        raise PaymentError("Choose dine-in, takeaway or counter pickup.")
    quote_result = quote(business_id=business_id, branch_id=branch.id, lines=lines,
                         discount_kind=discount_kind, discount_value=discount_value)
    priced = quote_result["lines"]
    if not priced:
        raise PaymentError("Add at least one item before taking payment.")

    amount_paid = resolve_amount_paid(quote_result["grand"], amount_paid)
    if amount_paid > quote_result["grand"]:
        raise PaymentError("Received amount is more than the total due.")

    order = RestaurantOrder(
        business_id=business_id, branch_id=branch.id,
        order_number=next_order_number(branch), order_type=order_type,
        status="open",
        subtotal=quote_result["subtotal"], discount_total=quote_result["discount"],
        tax_total=quote_result["tax"], grand_total=quote_result["grand"],
        cashier_shift_id=cashier_shift_id, created_at=utcnow(),
    )
    db.session.add(order)
    db.session.flush()
    ...
```

After this it adds `order_items`, modifiers, the payment, then reduces stock from the
recipes, then commits.

**Say this:** "Ek function poora bill likhta hai — order, items, payment, stock,
receipt, kitchen ticket. Agar beech mein error aaye to rollback ho jata hai, adhoora
bill database mein nahi rehta."

### 8. `checkout()` — `app/blueprints/pos.py` (line 305)

The route. It only validates the form, then hands the real work to `create_order()`.

```python
def checkout():
    ctx = context()
    cart = basket.get_cart()
    if not cart["lines"]:
        flash("The basket is empty.", "warn")
        return _back_to_till()

    order_type = request.form.get("order_type") or "dine_in"
    table_id = request.form.get("table_id", type=int)

    try:
        discount = Decimal("0")
        discount_kind = request.form.get("discount_kind") or "percent"
        if request.form.get("discount_value"):
            if not can("order.discount"):
                raise PaymentError("This account cannot apply a discount.")
            discount = _money_value(request.form.get("discount_value"))
            ...
        amount_paid = None
        if (request.form.get("amount_paid") or "").strip():
            amount_paid = _money_value(request.form.get("amount_paid"))
        ...
```

**Say this:** "Route patla rakha hai — form padho, check karo, service ko do. Business
logic service mein hai, is liye test karna aasan hai."

### 9. `apply_stock_delta()` — `app/services/inventory.py` (line 13)

The only function that changes stock. Every sale, purchase, transfer and adjustment
goes through it.

```python
def apply_stock_delta(*, business_id, branch_id, item_id, movement_type,
                      delta_qty, reference_code, created_at=None):
    """Apply one stock change. Repeating the same reference returns the original movement."""
    delta = quantity(delta_qty)
    if delta == 0:
        raise StockPolicyError("Stock movement quantity cannot be zero")
    ...
    existing = db.session.scalar(
        select(StockMovement).where(
            StockMovement.branch_id == branch_id,
            StockMovement.item_id == item_id,
            StockMovement.movement_type == movement_type,
            StockMovement.reference_code == reference_code,
        )
    )
    if existing is not None:
        return existing
    stock = db.session.scalar(
        select(BranchStock).where(BranchStock.branch_id == branch_id,
                                  BranchStock.item_id == item_id).with_for_update()
    )
    settings = db.session.scalar(
        select(BusinessSetting).where(BusinessSetting.business_id == business_id))
    allow_negative = bool(settings.allow_negative_stock) if settings is not None else False
    new_qty = quantity(stock.quantity + delta)
    if new_qty < 0 and not allow_negative:
        raise StockPolicyError(f"Negative stock is not allowed for item {item.sku}")
    stock.quantity = new_qty
    db.session.add(StockMovement(..., movement_type=movement_type, delta_qty=delta,
                                 reference_code=reference_code))
```

**Say this:** "Do cheezein important hain — `with_for_update()` se row lock hoti hai
taake do cashier ek saath sale karein to stock galat na ho, aur `reference_code` se
duplicate movement nahi banti."

### 10. `resolve_filters()` — `app/blueprints/reports.py` (line 112)

Decides which filters a report uses, and refuses anything outside the user's branches.

```python
def resolve_filters(ctx):
    """Explicit query string, else the session copy, else defaults.
    Raises 403 for a branch or record that belongs to another tenant."""
    if any(key in request.args for key in FILTER_KEYS):
        raw = {key: request.args.get(key, "") for key in FILTER_KEYS}
    elif isinstance(session.get(SESSION_KEY), dict):
        raw = {key: session[SESSION_KEY].get(key, "") for key in FILTER_KEYS}
    else:
        raw = _defaults(ctx)
    ...
    branch_value = raw.get("branch") or "all"
    if branch_value not in ("all", ""):
        branch_id = _int_or_none(branch_value)
        if branch_id is None or branch_id not in ctx.allowed_branch_ids:
            abort(403, description="That branch is outside your access.")
        branch_ids = [branch_id]
    else:
        branch_ids = list(ctx.allowed_branch_ids)
```

**Say this:** "Filter ka order hai URL → session → default. Isi liye page refresh karne
par filter reset nahi hote. Aur doosre branch ka id bhejo to 403 milta hai."

---

## 7. CRUD examples from the real code

All four examples are the payment methods screen (`app/blueprints/admin.py`), because it
shows the full pattern in a small space.

### Create — `payment_method_new()`

```python
@bp.post("/payment-methods/new")
@permission_required("business.settings")
def payment_method_new():
    ctx = context()
    code = (request.form.get("code") or "").strip().lower()
    label = (request.form.get("label") or "").strip()
    try:
        if not CODE_PATTERN.match(code):
            raise ValueError("Code must be 2-30 characters: letters, digits, dash or underscore.")
        if db.session.scalar(select(PaymentMethod.id).where(
                PaymentMethod.business_id == ctx.business_id,
                PaymentMethod.code == code)):
            raise ValueError("That code is already used in this business.")
        method = PaymentMethod(business_id=ctx.business_id, code=code, label=label[:70], enabled=True)
        db.session.add(method)
        db.session.flush()
        write_audit(action="create_payment_method", entity_type="payment_method",
                    entity_id=method.id, business_id=ctx.business_id,
                    actor_user_id=ctx.user.id, message=f"Added payment method {label}")
        db.session.commit()
        flash(f"{label} added.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
```

### Read — `payment_methods()`

```python
rows = db.session.execute(
    select(PaymentMethod, func.count(OrderPayment.id),
           func.coalesce(func.sum(OrderPayment.amount), 0))
    .outerjoin(OrderPayment, OrderPayment.payment_method_id == PaymentMethod.id)
    .where(PaymentMethod.business_id == ctx.business_id)
    .group_by(PaymentMethod.id)
    .order_by(PaymentMethod.id)
).all()
```

**Say this:** "Yahan SQLAlchemy se join, count aur sum kar rahe hain — har method ke
saath kitne payment aur kitna paisa."

### Update — `payment_method_edit()`

```python
method = db.session.get(PaymentMethod, method_id)
if method is None or method.business_id != ctx.business_id:
    abort(404)
method.label = label[:70]
method.enabled = bool(request.form.get("enabled"))
db.session.commit()
```

**Say this:** "Pehle row load hoti hai, phir check hota hai ke woh isi business ki hai —
nahi to 404. Uske baad columns badal kar commit."

### Delete — `payment_method_delete()` with a guard

```python
used = int(db.session.scalar(
    select(func.count()).select_from(OrderPayment)
    .where(OrderPayment.payment_method_id == method.id)) or 0)
if used:
    flash(f"{method.label} is used by {used} payment(s). Disable it instead of deleting.", "error")
    return redirect(url_for("admin.payment_methods"))
db.session.delete(method)
```

**Say this:** "Agar payment already ho chuki hai to delete nahi hota, kyunki history
kharab ho jati. Option `enabled = False` hai."

**More CRUD in the project:** branches (`branch_new`), employees (`staff_new`,
`staff_edit`, `staff_delete`), ingredients (`ingredient_new`, `ingredient_edit`),
recipes (`recipe_new`, `recipe_edit`), shifts (`shift_open`, `shift_close`).

---

## 8. Fifteen likely viva questions

**1. What is this project?**
A multi-branch restaurant POS. One database serves many restaurants; each restaurant has
branches, menus, stock, staff, and reports.

**2. Which technologies did you use and why?**
Flask (small, readable), SQLAlchemy (Python objects instead of raw SQL), PostgreSQL
(money type `NUMERIC`, strong constraints), Jinja2 (server-rendered HTML), plain CSS and
a little vanilla JavaScript. No React or build step.

**3. What is a blueprint?**
A way to split routes into files. `app/blueprints/pos.py` handles `/pos`, `orders.py`
handles `/orders`, and so on. They are registered in `create_app()`.

**4. What is the app factory pattern?**
`create_app()` builds the app instead of creating it at import time. Tests can create
their own app with a different configuration.

**5. How do you stop one restaurant from seeing another's data?**
Every table has `business_id`. `load_context()` gives the current business and the
allowed branch ids, every query filters by them, and an id from another tenant returns
403 or 404. Example: `resolve_filters()` aborts with 403 for a foreign branch.

**6. How does login work?**
`auth.login()` finds the user by email, compares the password with
`check_password_hash`, then stores `uid`, `bid` and `branch_id` in the session. Passwords
are stored as a hash, never as plain text.

**7. What is CSRF and how did you handle it?**
A site could submit a form to your app using your cookie. We put a random token in the
session and in every form (`_csrf`), and a `before_request` hook rejects POST/PUT/DELETE
requests that do not match.

**8. Why `Decimal` and not `float`?**
`float` cannot represent 0.1 exactly, so totals drift by a paisa. The database stores
`NUMERIC(12,2)` and Python uses `Decimal`. The `money()` helper rounds to 2 places.

**9. Write the order total formula.**
`taxable = subtotal − discount`, `tax = taxable × rate / 100`,
`grand = taxable + tax`. Then `grand` is compared with the amount received.

**10. How does stock decrease when something is sold?**
The recipe says how much of each ingredient a product uses. `create_order()` reads
`recipe_lines` and calls `apply_stock_delta()` for each ingredient, which writes a
`stock_movements` row and updates `branch_stocks`.

**11. Why keep a `stock_movements` table if `branch_stocks` already has quantity?**
`branch_stocks` is only the current number. The movements table is the history, so you
can answer "why did chicken go down by 12 kg" and check for mistakes.

**12. What happens if two cashiers sell the last item at the same time?**
`apply_stock_delta()` locks the stock row with `with_for_update()` and checks the new
quantity, so the second sale either waits or fails with a stock error.

**13. How do report filters survive a refresh?**
Filters are written to the URL by `reports.js` using `history.pushState`, and
`resolve_filters()` reads URL first, then the session copy. Nothing resets silently.

**14. How do you know the data is demo data?**
There is a `dataset_manifests` table (7 rows) that records each load, with codes like
`SYNTHETIC_HISTORY_V1`. The report "provenance" section shows it. Nothing pretends the
synthetic history is real.

**15. How did you test it?**
88 pytest tests: pages load, login and permissions, tenant isolation, report totals
recomputed with SQL, discount maths, and database integrity (ledger balanced, demo rows
preserved). Tests read the live database but do not change it.

---

## 9. Three-minute live demonstration

**Before you start** — browser open at `https://amna.areeenaa.com`, signed in as the
super admin. Keep this order; it tells a story from restaurant to report.

**0:00 – 0:20 | Overview**
Open **Overview**. Point at the figure strip and say:
"Ye aaj ka net sales, average order, tax, open orders aur kitchen queue hai. Ye numbers
database se aate hain, koi hardcoded nahi."

**0:20 – 0:35 | Context switching**
In the top bar change **restaurant**, then **branch**, press **Apply**.
Say: "Restaurant badalne par branch list update hoti hai. Apply dabane se poora app us
branch ka data dikhata hai — koi full page reload nahi."

**0:35 – 1:30 | Billing (the main part)**
Open **Billing**. Click two items on the left.
Say: "Basket session mein hai, database mein nahi. Yahan har line ka quantity badal
sakte hain."
Enter a discount, for example `10` with **Percent**.
Say: "Discount pehle lagta hai, phir tax. 10% of 1,300 = 130, tax 5% of 1,170 = 58.50,
total 1,228.50."
Leave **Received** empty and press **Take payment**.
Say: "Khali chhodne ka matlab poora due bill ho jaye. Order save hua, receipt bana,
stock recipes se kam hua, kitchen ticket bhi bana."
You land on the receipt.

**1:30 – 1:50 | Orders**
Go to **Orders**. Point at the status tabs.
Say: "Har status ka tab hai. Search aur date filter URL mein hain." Open the order you
just made and show Items, Payments and the totals block.

**1:50 – 2:20 | Inventory and recipe**
Open **Inventory → Ingredients**, then **Recipes** (one product).
Say: "Recipe batati hai ke ek plate mein kitna chicken aur chawal lagta hai. Sale ke
waqt `apply_stock_delta()` stock kam karta hai aur `stock_movements` mein ek row likhta
hai — poori history."

**2:20 – 2:50 | Reports**
Open **Reports**. Change the date range. Show the overview figures and the sales chart.
Say: "Filters URL mein hain, is liye refresh karne par bhi wahi rehte hain. Numbers ek
JSON endpoint se aate hain, page reload nahi hota."

**2:50 – 3:00 | Close**
Say: "Backend Flask aur SQLAlchemy, database PostgreSQL, UI Jinja2 se bana hai. 88 tests
pass hain, aur poora system live chal raha hai."

**If the teacher asks for code**, open these four files in this order:
`app/__init__.py` → `app/security.py` (`load_context`) →
`app/services/pos_orders.py` (`quote`, `create_order`) →
`app/services/inventory.py` (`apply_stock_delta`).

---

## 10. Last-minute revision sheet

| Question | One-line answer |
| --- | --- |
| Entry point | `wsgi.py` → `create_app()` |
| Route for the till | `app/blueprints/pos.py` |
| Business logic | `app/services/*.py` |
| Session stores | `uid`, `bid`, `branch_id`, `_csrf` |
| Permissions stored in | `permissions` + `role_permissions`, checked by `@permission_required` |
| Money type | `NUMERIC(12,2)` / `Decimal` |
| Tax order | discount first, then tax |
| Stock history | `stock_movements` |
| Report filter order | URL → session → default |
| Test count | 88 pytest tests |
| Tables | 66 |
| Demo data label | `dataset_manifests` (7 rows) |

**Three sentences to open the viva**

1. "Amna POS ek multi-branch restaurant ka point of sale hai, Flask aur PostgreSQL par
   bana hua."
2. "Har restaurant ka data `business_id` se alag hai, aur har sale order, items, payment
   aur stock movement ek hi transaction mein likhi jati hai."
3. "Har cheez ka record rehta hai — audit log, stock ledger aur payment history — is liye
   kuch bhi gum nahi hota."
