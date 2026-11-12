"""Reports: JSON contract, filter persistence, tenant isolation and reconciliation.

These tests are read-only. They sign a session cookie directly and only issue GET
requests, so nothing is written to the database.
"""
import json
import re

import pytest
from sqlalchemy import select, text

from app import db
from app.models import User

from tests import support

CASHIER = "cashier"
JT_MANAGER = "manager"
KITCHEN = "kitchen"
SUPER_ADMIN = "super_admin"

# A window well inside the synthetic history, so it cannot be empty by accident.
WINDOW = "2026-01-01"
WINDOW_END = "2026-01-31"


@pytest.fixture()
def client(app):
    previous = app.config["SESSION_COOKIE_SECURE"]
    app.config["SESSION_COOKIE_SECURE"] = False
    with app.test_client() as test_client:
        yield test_client
    app.config["SESSION_COOKIE_SECURE"] = previous


def sign_in(client, app, who):
    """Sign in as a role name, resolved against the live database."""
    with app.app_context():
        if "@" in who:
            user = db.session.scalar(select(User).where(User.email == who))
        else:
            user = support.require(who)
        user_id = user.id
    with client.session_transaction() as session:
        session["uid"] = user_id


def scope(app, role):
    """The branch an active account of this role is pinned to."""
    with app.app_context():
        user = support.require(role)
        return support.branch_inside_scope(user), support.branch_outside_scope(user)


def bootstrap(html):
    """Read the JSON the shell embeds, which is what the page renders from."""
    match = re.search(
        r'<script id="report-bootstrap" type="application/json">(.*?)</script>', html, re.S
    )
    assert match, "report shell does not expose its bootstrap state"
    return json.loads(match.group(1))


def api(client, query=""):
    response = client.get("/reports/api/data" + (("?" + query) if query else ""))
    return response, (response.get_json() if response.is_json else None)


def test_reports_page_renders_the_filter_shell(client, app):
    sign_in(client, app, CASHIER)
    response = client.get("/reports")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Sales overview" in body
    assert 'id="filter-from"' in body
    assert 'id="filter-branch"' in body
    assert "/static/js/reports.js" in body
    # The panels are populated from this state, not from a full page load.
    assert bootstrap(body)["sections"]


def test_api_returns_every_section(client, app):
    sign_in(client, app, CASHIER)
    response, payload = api(client, f"from={WINDOW}&to={WINDOW_END}")
    assert response.status_code == 200
    assert payload["ok"] is True
    for name in (
        "overview",
        "daily",
        "weekly",
        "monthly",
        "branches",
        "products",
        "categories",
        "payments",
        "cancelled",
        "cashiers",
        "stock",
        "low_stock",
        "purchases",
        "discounts",
        "operations",
        "provenance",
    ):
        assert name in payload["sections"], name
    assert payload["sections"]["overview"]["current"]["orders"] > 0


def test_regression_report_filters_survive_navigation(client, app):
    """The reported bug: opening reports and clicking around reset the filters.

    A filtered view must be reproducible from the URL, and a later visit to the
    bare /reports URL (what the navigation link points at) must reopen that same
    view instead of falling back to the default period.
    """
    sign_in(client, app, CASHIER)

    branch, _outside = scope(app, CASHIER)
    first = client.get(f"/reports?from={WINDOW}&to={WINDOW_END}&branch={branch}")
    assert first.status_code == 200
    state = bootstrap(first.get_data(as_text=True))["raw"]
    assert state["from"] == WINDOW
    assert state["to"] == WINDOW_END
    assert state["branch"] == "1"

    # Click "Reports" in the navigation, which links to /reports with no query.
    again = client.get("/reports")
    assert again.status_code == 200
    restored = bootstrap(again.get_data(as_text=True))["raw"]
    assert restored["from"] == WINDOW, "date range was reset by navigation"
    assert restored["to"] == WINDOW_END, "date range was reset by navigation"
    assert restored["branch"] == "1", "branch filter was reset by navigation"


def test_filters_are_carried_into_the_embedded_data(client, app):
    """The first paint uses the filtered data, so no reload is needed to apply it."""
    sign_in(client, app, CASHIER)
    response = client.get(f"/reports?from={WINDOW}&to={WINDOW_END}")
    payload = bootstrap(response.get_data(as_text=True))
    assert payload["labels"]["period"].startswith("01 Jan 2026")
    assert payload["sections"]["overview"]["current"]["orders"] > 0


def test_date_range_changes_the_numbers(client, app):
    sign_in(client, app, CASHIER)
    branch, _outside = scope(app, CASHIER)
    _, january = api(client, f"from={WINDOW}&to={WINDOW_END}&branch={branch}")
    _, one_day = api(client, f"from=2026-01-05&to=2026-01-05&branch={branch}")
    assert january["sections"]["overview"]["current"]["orders"] > one_day["sections"]["overview"]["current"]["orders"]
    assert one_day["sections"]["overview"]["current"]["orders"] > 0


def test_totals_reconcile_with_the_database(client, app):
    """Every rupee in the overview must match a direct SQL sum of the same rows."""
    sign_in(client, app, CASHIER)
    branch, _outside = scope(app, CASHIER)
    _, payload = api(client, f"from={WINDOW}&to={WINDOW_END}&branch={branch}")
    current = payload["sections"]["overview"]["current"]

    with app.app_context():
        row = db.session.execute(
            text(
                """
                SELECT COUNT(*), COALESCE(SUM(grand_total), 0), COALESCE(SUM(tax_total), 0)
                FROM restaurant_orders
                WHERE business_id = :business AND branch_id = :branch AND status = 'paid'
                  AND (created_at AT TIME ZONE 'Asia/Karachi')::date BETWEEN :start AND :end
                """
            ),
            {
                "business": support.BUSINESS_ID,
                "branch": branch,
                "start": WINDOW,
                "end": WINDOW_END,
            },
        ).one()

    assert current["orders"] == int(row[0])
    assert float(current["gross"]) == pytest.approx(float(row[1]), abs=0.01)
    assert float(current["tax"]) == pytest.approx(float(row[2]), abs=0.01)


def test_empty_period_is_reported_honestly(client, app):
    sign_in(client, app, CASHIER)
    branch, _outside = scope(app, CASHIER)
    response, payload = api(client, f"from=2024-01-01&to=2024-01-31&branch={branch}")
    assert response.status_code == 200
    current = payload["sections"]["overview"]["current"]
    assert current["orders"] == 0
    assert float(current["net_sales"]) == 0.0
    assert payload["sections"]["daily"] == []
    assert payload["sections"]["products"] == []


def test_category_filter_narrows_the_result(client, app):
    sign_in(client, app, CASHIER)
    with app.app_context():
        category_id = db.session.execute(
            text("SELECT id FROM categories WHERE business_id = 1 ORDER BY id LIMIT 1")
        ).scalar()
    branch, _outside = scope(app, CASHIER)
    _, everything = api(client, f"from={WINDOW}&to={WINDOW_END}&branch={branch}")
    _, narrowed = api(
        client, f"from={WINDOW}&to={WINDOW_END}&branch={branch}&category={category_id}"
    )
    assert 0 < narrowed["sections"]["overview"]["current"]["orders"] < everything["sections"]["overview"]["current"]["orders"]
    assert all(row["category_id"] == category_id for row in narrowed["sections"]["categories"])


def test_cashier_cannot_report_on_another_branch(client, app):
    sign_in(client, app, CASHIER)
    _inside, outside = scope(app, CASHIER)
    assert outside is not None
    assert client.get(f"/reports/api/data?branch={outside}").status_code == 403
    assert client.get(f"/reports?branch={outside}").status_code == 403


def test_manager_cannot_report_on_another_branch(client, app):
    sign_in(client, app, JT_MANAGER)
    inside, outside = scope(app, JT_MANAGER)
    if outside is None:
        pytest.skip("this manager can already read every branch")
    assert client.get(f"/reports/api/data?branch={outside}").status_code == 403
    assert client.get(f"/reports/api/data?branch={inside}").status_code == 200


def test_manager_cannot_filter_by_another_business_category(client, app):
    sign_in(client, app, JT_MANAGER)
    with app.app_context():
        foreign = db.session.execute(
            text(
                "SELECT id FROM categories WHERE business_id != :business ORDER BY id LIMIT 1"
            ),
            {"business": support.BUSINESS_ID},
        ).scalar()
    assert client.get(f"/reports/api/data?category={foreign}").status_code == 403


def test_kitchen_staff_cannot_open_reports(client, app):
    sign_in(client, app, KITCHEN)
    assert client.get("/reports").status_code == 403
    assert client.get("/reports/api/data").status_code == 403


def test_unknown_section_is_rejected(client, app):
    sign_in(client, app, CASHIER)
    response = client.get("/reports/api/data?sections=overview,nonsense")
    assert response.status_code == 400


def test_super_admin_reports_follow_the_selected_business(client, app):
    sign_in(client, app, SUPER_ADMIN)
    with app.app_context():
        other = support.other_business_id()
        other_name = db.session.execute(
            text("SELECT name FROM businesses WHERE id = :i"), {"i": other}
        ).scalar()
        other_codes = set(
            db.session.execute(
                text("SELECT code FROM branches WHERE business_id = :i"), {"i": other}
            ).scalars()
        )
    with client.session_transaction() as session:
        session["bid"] = other
        session.pop("branch_id", None)
    response, payload = api(client, f"from={WINDOW}&to={WINDOW_END}")
    assert response.status_code == 200
    assert payload["labels"]["business"] == other_name
    branch_codes = {row["code"] for row in payload["sections"]["branches"]}
    assert branch_codes <= other_codes
    own_codes = {"JT", "DHA"}
    assert not (branch_codes & own_codes)
