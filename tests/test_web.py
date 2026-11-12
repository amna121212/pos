"""Web layer checks: routing, sign-in, permissions and page rendering.

These tests are read-only. They sign a session cookie directly instead of
posting credentials, so no account password is stored in the test suite.
"""
import pytest
from sqlalchemy import select, text

from app import db
from app.models import Product, Supplier, User
from app.security import _role_permissions, clear_permission_cache

from tests import support
from app.services.orders import compute_discount, order_totals


@pytest.fixture()
def client(app):
    previous = app.config["SESSION_COOKIE_SECURE"]
    app.config["SESSION_COOKIE_SECURE"] = False
    with app.test_client() as test_client:
        yield test_client
    app.config["SESSION_COOKIE_SECURE"] = previous


def sign_in(client, app, who):
    """Sign in as a role name, or as an explicit email.

    Role names resolve against the live database so the suite does not break when
    an administrator disables or re-scopes a seeded person.
    """
    with app.app_context():
        if "@" in who:
            user = db.session.scalar(select(User).where(User.email == who))
        else:
            user = support.require(who)
        user_id = user.id
    with client.session_transaction() as session:
        session["uid"] = user_id


def _token(client):
    """Give the client a CSRF token it can submit.

    A signed-in client is not shown the sign-in page, so the token is written
    directly into the session instead of scraped from a form.
    """
    with client.session_transaction() as session:
        token = session.get("_csrf")
        if token:
            return token
        token = "test-csrf-token"
        session["_csrf"] = token
        return token


def test_anonymous_visitor_is_sent_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Amna POS" in body
    assert "_csrf" in body


def test_login_rejects_wrong_password(client):
    response = client.post(
        "/login",
        data={
            "email": "lgh.csh.jt@example.invalid",
            "password": "definitely-not-it",
            "_csrf": _token(client),
        },
    )
    assert response.status_code == 401
    assert "not correct" in response.get_data(as_text=True)


def test_post_without_csrf_is_refused(client):
    response = client.post("/login", data={"email": "x@example.invalid", "password": "x"})
    assert response.status_code == 400


def test_signup_page_renders(client):
    response = client.get("/signup")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Create account" in body
    assert "First branch name" in body


def test_signup_rejects_a_short_password(client):
    response = client.post(
        "/signup",
        data={
            "business_name": "Test Kitchen",
            "business_type": "restaurant",
            "city": "Lahore",
            "branch_name": "Main",
            "owner_name": "Test Owner",
            "email": "brand-new-owner@example.invalid",
            "password": "short",
            "password_confirm": "short",
            "tax_percent": "0",
            "_csrf": _token(client),
        },
    )
    assert response.status_code == 400
    assert "at least 8" in response.get_data(as_text=True)


def test_signup_rejects_a_duplicate_email(client, app):
    response = client.post(
        "/signup",
        data={
            "business_name": "Test Kitchen",
            "business_type": "restaurant",
            "city": "Lahore",
            "branch_name": "Main",
            "owner_name": "Test Owner",
            "email": "lgh.csh.jt@example.invalid",
            "password": "long-enough-password",
            "password_confirm": "long-enough-password",
            "tax_percent": "0",
            "_csrf": _token(client),
        },
    )
    assert response.status_code == 400
    assert "already exists" in response.get_data(as_text=True)


def test_signup_can_be_closed(client, app):
    previous = app.config["SIGNUP_ENABLED"]
    app.config["SIGNUP_ENABLED"] = False
    try:
        assert client.get("/signup").status_code == 404
    finally:
        app.config["SIGNUP_ENABLED"] = previous


def test_cashier_dashboard_renders(client, app):
    sign_in(client, app, CASHIER)
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Dashboard" in body
    assert "Till" in body
    assert "Staff" not in body


def test_till_page_lists_branch_products(client, app):
    sign_in(client, app, CASHIER)
    response = client.get("/pos")
    assert response.status_code == 200
    assert "Current bill" in response.get_data(as_text=True)


def test_cashier_can_read_reports(client, app):
    sign_in(client, app, CASHIER)
    response = client.get("/reports")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    # The panels are drawn from the embedded state, so the shell carries the filters
    # and the JSON endpoint rather than pre-rendered figures.
    assert "Sales overview" in body
    assert "/reports/api/data" in body or "report-bootstrap" in body


def test_cashier_cannot_manage_staff(client, app):
    sign_in(client, app, CASHIER)
    assert client.get("/staff").status_code == 403


def test_cashier_cannot_adjust_stock(client, app):
    sign_in(client, app, CASHIER)
    assert client.get("/inventory/adjust").status_code == 403


def test_cashier_cannot_open_platform_console(client, app):
    sign_in(client, app, CASHIER)
    assert client.get("/platform").status_code == 403


def test_manager_can_open_reports_and_staff(client, app):
    sign_in(client, app, JT_MANAGER)
    assert client.get("/reports").status_code == 200
    assert client.get("/staff").status_code == 200


def test_kitchen_staff_see_the_board_but_not_reports(client, app):
    sign_in(client, app, KITCHEN)
    response = client.get("/kitchen")
    assert response.status_code == 200
    assert "Kitchen" in response.get_data(as_text=True)
    assert client.get("/reports").status_code == 403


def test_inventory_staff_see_stock(client, app):
    sign_in(client, app, "inventory")
    response = client.get("/inventory")
    assert response.status_code == 200
    assert "Stock" in response.get_data(as_text=True)


def test_every_rule_has_a_unique_endpoint(app):
    names = [rule.endpoint for rule in app.url_map.iter_rules() if rule.endpoint != "static"]
    assert len(names) == len(set(names))


def test_permission_matrix_matches_the_database(app):
    with app.app_context():
        clear_permission_cache()
        cashier = _role_permissions("cashier")
        manager = _role_permissions("manager")
        kitchen = _role_permissions("kitchen")
        inventory = _role_permissions("inventory")
        clear_permission_cache()
    assert {"order.create", "payment.capture", "report.view"} <= cashier
    assert "menu.manage" not in cashier
    assert "staff.manage" not in cashier
    assert {"report.view", "order.refund", "staff.manage"} <= manager
    assert kitchen == frozenset({"kitchen.update"})
    assert {"inventory.adjust", "inventory.purchase", "inventory.transfer"} <= inventory


# ------------------------------------------------------- module page coverage


MANAGER_PAGES = [
    "/",
    "/pos",
    "/orders",
    "/orders/returns",
    "/kitchen",
    "/products",
    "/products/new",
    "/categories",
    "/inventory",
    "/inventory/ingredients",
    "/inventory/recipes",
    "/inventory/movements",
    "/inventory/adjust",
    "/inventory/purchases",
    "/inventory/purchases/new",
    "/inventory/transfers",
    "/suppliers",
    "/suppliers/new",
    "/reports",
    "/insights",
    "/restaurants",
    "/staff",
    "/shifts",
    "/audit",
    "/settings",
]


def test_every_manager_page_loads(client, app):
    sign_in(client, app, JT_MANAGER)
    broken = []
    for path in MANAGER_PAGES:
        status = client.get(path).status_code
        if status != 200:
            broken.append((path, status))
    assert broken == [], broken


def test_restaurants_page_lists_the_visible_business(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        manager = support.require("manager")
        allowed = set(support.allowed_branches(manager))
        names = {
            row[0]: row[1]
            for row in db.session.execute(
                text("SELECT id, name FROM branches WHERE business_id = :b"),
                {"b": support.BUSINESS_ID},
            ).all()
        }
    body = client.get("/restaurants").get_data(as_text=True)
    assert "Lahore Grill House" in body
    for branch_id in allowed:
        assert names[branch_id] in body
    for branch_id, name in names.items():
        if branch_id not in allowed:
            assert name not in body, f"{name} should not be offered to this manager"
    # A branch manager must not see another tenant's restaurant.
    assert "Urban Bites Lahore" not in body


def test_manager_cannot_open_another_restaurant(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        foreign_business = support.other_business_id()
    assert foreign_business is not None
    assert client.get(f"/restaurants/{foreign_business}").status_code == 403
    assert client.get("/restaurants/1").status_code == 200


def test_supplier_from_another_business_is_refused(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        foreign = db.session.scalar(
            select(Supplier.id)
            .where(Supplier.business_id != support.BUSINESS_ID)
            .order_by(Supplier.id)
        )
    assert foreign is not None
    assert client.get(f"/suppliers/{foreign}").status_code == 404
    assert client.get(f"/suppliers/{foreign}/edit").status_code == 404


def test_super_admin_restaurant_page_lists_every_tenant(client, app):
    sign_in(client, app, SUPER_ADMIN)
    body = client.get("/restaurants").get_data(as_text=True)
    for name in ("Lahore Grill House", "Urban Bites Lahore", "Daily Mart Lahore"):
        assert name in body


def test_dashboard_numbers_come_from_the_database(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        user = support.require("manager")
        branch_id = support.scope_branch_id(user) or support.BUSINESS_ID
        row = db.session.execute(
            text(
                """
                SELECT COALESCE(SUM(grand_total - tax_total), 0)
                FROM restaurant_orders
                WHERE business_id = :business AND branch_id = :branch AND status = 'paid'
                  AND (created_at AT TIME ZONE 'Asia/Karachi')::date = (now() AT TIME ZONE 'Asia/Karachi')::date
                """
            ),
            {"business": support.BUSINESS_ID, "branch": branch_id},
        ).scalar()
    body = client.get("/").get_data(as_text=True)
    expected = f"Rs {float(row):,.2f}"
    assert expected in body, f"dashboard does not show today's net sales {expected}"


def test_totals_use_decimal_rupees():
    totals = order_totals(subtotal="1000", discount="100", tax_rate_percent="16")
    assert str(totals["tax"]) == "144.00"
    assert str(totals["grand"]) == "1044.00"
    assert str(compute_discount("1000", "percent", "12.5")) == "125.00"
    assert str(compute_discount("100", "fixed", "150")) == "100.00"


# ---------------------------------------------------------------- super admin


SUPER_ADMIN = "super_admin"
CASHIER = "cashier"
JT_MANAGER = "manager"
KITCHEN = "kitchen"


def _select_business(client, business_id):
    with client.session_transaction() as session:
        session["bid"] = business_id
        session.pop("branch_id", None)


def _select_branch(client, branch_id):
    with client.session_transaction() as session:
        session["branch_id"] = branch_id


def _unique_product(app, business_id, other_business_id):
    """A product name that exists in one business only, so the page test is exact."""
    other_names = set(
        db.session.scalars(select(Product.name).where(Product.business_id == other_business_id)).all()
    )
    return db.session.scalar(
        select(Product)
        .where(Product.business_id == business_id, Product.name.notin_(other_names))
        .order_by(Product.id)
        .limit(1)
    )


def test_super_admin_sees_a_business_it_does_not_belong_to(client, app):
    sign_in(client, app, SUPER_ADMIN)
    _select_business(client, 2)
    body = client.get("/").get_data(as_text=True)
    assert "Urban Bites Lahore" in body
    assert "Super admin" in body


def test_super_admin_branch_picker_lists_only_the_selected_business(client, app):
    sign_in(client, app, SUPER_ADMIN)
    _select_business(client, 2)
    body = client.get("/").get_data(as_text=True)
    assert "&middot; Gulberg III" in body
    assert "&middot; Model Town" in body
    assert "&middot; Johar Town" not in body


def test_super_admin_till_shows_the_selected_business_catalogue(client, app):
    sign_in(client, app, SUPER_ADMIN)
    _select_business(client, 2)
    with app.app_context():
        mine = _unique_product(app, 2, 1)
        theirs = _unique_product(app, 1, 2)
        assert mine is not None and theirs is not None
        mine_name, theirs_name = mine.name, theirs.name
    body = client.get("/pos").get_data(as_text=True)
    assert f'class="name">{mine_name}</span>' in body
    assert f'class="name">{theirs_name}</span>' not in body


def test_super_admin_business_dropdown_lists_every_business(client, app):
    sign_in(client, app, SUPER_ADMIN)
    body = client.get("/").get_data(as_text=True)
    assert 'id="business-select"' in body
    assert "Lahore Grill House" in body
    assert "Daily Mart Lahore" in body


def test_super_admin_can_open_the_platform_console(client, app):
    sign_in(client, app, SUPER_ADMIN)
    assert client.get("/platform").status_code == 200


def test_normal_user_has_no_business_dropdown(client, app):
    sign_in(client, app, CASHIER)
    body = client.get("/").get_data(as_text=True)
    assert 'id="business-select"' not in body
    assert "Lahore Grill House" in body


def test_cashier_cannot_post_another_business(client, app):
    sign_in(client, app, CASHIER)
    response = client.post("/business/2", data={"business_id": "2", "_csrf": _token(client)})
    assert response.status_code == 403


def test_manager_cannot_post_a_branch_outside_their_membership(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        outside = support.branch_outside_scope(support.require("manager"))
    assert outside is not None
    response = client.post(f"/branch/{outside}", data={"_csrf": _token(client)})
    assert response.status_code == 403


def test_switch_routes_require_csrf(client, app):
    sign_in(client, app, SUPER_ADMIN)
    assert client.post("/business/2", data={"business_id": "2"}).status_code == 400
    assert client.post("/branch/1", data={"branch_id": "1"}).status_code == 400


def test_tampered_business_in_session_falls_back_to_membership(client, app):
    sign_in(client, app, CASHIER)
    _select_business(client, 2)  # a business the cashier has no membership in
    body = client.get("/").get_data(as_text=True)
    assert "Lahore Grill House" in body
    assert "Urban Bites Lahore" not in body


def test_tampered_branch_in_session_falls_back_to_membership(client, app):
    sign_in(client, app, CASHIER)
    with app.app_context():
        cashier = support.require("cashier")
        own = support.scope_branch_id(cashier)
        outside = support.branch_outside_scope(cashier)
        own_code = (
            db.session.execute(
                text("SELECT code FROM branches WHERE id = :i"), {"i": own}
            ).scalar()
            if own
            else None
        )
        outside_code = db.session.execute(
            text("SELECT code FROM branches WHERE id = :i"), {"i": outside}
        ).scalar()
    _select_branch(client, outside)  # a branch this cashier may not read
    body = client.get("/pos").get_data(as_text=True)
    assert outside_code not in body
    if own_code:
        assert own_code in body


# ---------------------------------------------- switching the working context


AS_FETCH = {"X-Requested-With": "fetch", "Accept": "application/json"}


def test_switch_form_carries_the_current_page(client, app):
    """The picker must return to the page you were on, not to the dashboard."""
    sign_in(client, app, SUPER_ADMIN)
    body = client.get("/orders?status=paid&page=2").get_data(as_text=True)
    assert 'name="next" value="/orders?status=paid&amp;page=2"' in body
    assert 'data-context-form' in body
    assert 'id="context-apply"' in body


def test_context_picker_does_not_submit_on_change(client, app):
    """Choosing a restaurant must only refill the branch list; Apply commits."""
    sign_in(client, app, SUPER_ADMIN)
    body = client.get("/products").get_data(as_text=True)
    assert "onchange" not in body.split('<form method="post" action="/context"')[1].split("</form>")[0]
    assert "<script id=\"context-branches\"" in body


def test_context_switch_applies_business_and_branch_together(client, app):
    sign_in(client, app, SUPER_ADMIN)
    with app.app_context():
        other = support.other_business_id()
        branch = db.session.execute(
            text("SELECT id FROM branches WHERE business_id = :b ORDER BY id LIMIT 1"),
            {"b": other},
        ).scalar()
    response = client.post(
        "/context",
        data={
            "_csrf": _token(client),
            "business_id": other,
            "branch_id": branch,
            "next": "/products",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/products")
    with client.session_transaction() as session:
        assert session["bid"] == other
        assert session["branch_id"] == branch
    body = client.get("/products").get_data(as_text=True)
    assert "Working context" in body or "Products" in body


def test_context_switch_returns_json_for_fetch(client, app):
    sign_in(client, app, SUPER_ADMIN)
    with app.app_context():
        other = support.other_business_id()
        branch = db.session.execute(
            text("SELECT id FROM branches WHERE business_id = :b ORDER BY id LIMIT 1"),
            {"b": other},
        ).scalar()
    response = client.post(
        "/context",
        data={"_csrf": _token(client), "business_id": other, "branch_id": branch},
        headers=AS_FETCH,
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["branch"]["id"] == branch
    assert [row["id"] for row in payload["businesses"]]
    # leave the session on the seeded tenant for the next test
    with client.session_transaction() as session:
        session["bid"] = support.BUSINESS_ID


def test_context_switch_refuses_a_foreign_branch(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        outside = support.branch_outside_scope(support.require("manager"))
    assert outside is not None
    response = client.post(
        f"/context", data={"_csrf": _token(client), "branch_id": outside}, headers=AS_FETCH
    )
    assert response.status_code == 403


def test_branch_switch_returns_json_for_fetch(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        manager = support.require("manager")
        inside = support.branch_inside_scope(manager)
        visible = support.allowed_branches(manager)
    response = client.post(f"/branch/{inside}", data={"_csrf": _token(client)}, headers=AS_FETCH)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["branch"]["id"] == inside
    assert [branch["id"] for branch in payload["branches"]] == visible


def test_business_switch_returns_json_for_fetch(client, app):
    sign_in(client, app, JT_MANAGER)
    response = client.post("/business/1", data={"_csrf": _token(client)}, headers=AS_FETCH)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["business"]["name"] == "Lahore Grill House"


def test_switch_returns_to_the_page_you_were_on(client, app):
    """Non-JavaScript fallback: the POST redirects back to the same filtered view."""
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        inside = support.branch_inside_scope(support.require("manager"))
    target = f"/reports?from=2026-01-01&to=2026-01-31&branch={inside}"
    response = client.post(
        f"/branch/{inside}",
        data={"_csrf": _token(client), "next": target},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(target)


def test_switch_ignores_an_external_next(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        inside = support.branch_inside_scope(support.require("manager"))
    response = client.post(
        f"/branch/{inside}",
        data={"_csrf": _token(client), "next": "https://evil.example/steal"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]


def test_json_switch_refuses_another_business(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        foreign = support.other_business_id()
    assert foreign is not None
    response = client.post(f"/business/{foreign}", data={"_csrf": _token(client)}, headers=AS_FETCH)
    assert response.status_code == 403


def test_switch_without_csrf_is_refused(client, app):
    sign_in(client, app, JT_MANAGER)
    assert client.post("/branch/1", data={}, headers=AS_FETCH).status_code == 400
