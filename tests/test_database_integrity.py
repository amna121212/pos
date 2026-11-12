"""Checks against the live retail_pos_db. These tests do not delete posted sales."""
import time
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Branch, Business, Product
from app.money import money
from app.order_models import RestaurantOrder
from app.services.analytics import branch_comparison, branch_monthly_summary, top_products
from app.services.csv_import import import_file
from app.services.errors import PaymentError, TenantAccessError
from app.services.integrity import integrity_problems, preserved_demo_counts
from app.services.orders import capture_payment, finalize_receipt, hold_order, resume_order
from app.services.recipes import post_recipe_consumption
from app.services.transfers import post_transfer
from app.inventory_models import InventoryItem, StockMovement
from app.models import PaymentMethod


def test_database_name_is_the_pos_database():
    current = db.session.execute(text("SELECT current_database()")).scalar()
    assert current == "retail_pos_db"


def test_at_least_sixty_application_models_are_registered():
    names = {mapper.class_.__tablename__ for mapper in db.Model.registry.mappers}
    assert "alembic_version" not in names
    assert len(names) >= 60


def test_every_model_can_be_queried_and_relationships_resolve():
    for mapper in db.Model.registry.mappers:
        db.session.execute(select(mapper.class_).limit(1)).all()
        for relationship in mapper.relationships:
            assert relationship.mapper is not None


def test_original_demo_rows_are_preserved():
    counts = preserved_demo_counts()
    assert counts["businesses"] >= 3
    # Registration is open, so new tenants may exist. The seeded six must survive.
    assert counts["branches"] >= 6
    seeded = db.session.execute(
        select(Branch.code, Business.name)
        .join(Business, Business.id == Branch.business_id)
        .where(Business.is_demo.is_(True))
    ).all()
    assert len(seeded) == 6
    assert counts["demo_orders"] == 24
    names = set(db.session.scalars(select(Business.name)).all())
    assert "Lahore Grill House" in names
    assert "Urban Bites Lahore" in names
    assert "Daily Mart Lahore" in names


def test_integrity_queries_are_clean():
    problems = integrity_problems()
    assert problems == []


def test_paid_order_money_is_decimal():
    order = db.session.scalar(select(RestaurantOrder).where(RestaurantOrder.status == "paid").limit(1))
    assert isinstance(order.grand_total, Decimal)
    assert order.grand_total == money(order.subtotal) - money(order.discount_total) + money(order.tax_total)


def test_analytics_are_reproducible():
    business = db.session.scalar(select(Business).where(Business.slug == "lahore-grill-house"))
    first = top_products(business.id, limit=5)
    second = top_products(business.id, limit=5)
    assert first == second
    assert first
    assert isinstance(first[0]["qty"], Decimal)
    comparison = branch_comparison(business.id)
    assert {row["code"] for row in comparison} == {"JT", "DHA"}


def test_reporting_query_finishes_quickly():
    business = db.session.scalar(select(Business).where(Business.slug == "urban-bites-lahore"))
    started = time.perf_counter()
    rows = branch_monthly_summary(business.id)
    elapsed = time.perf_counter() - started
    assert rows
    assert elapsed < 5


def test_posted_business_cannot_be_deleted():
    business = db.session.get(Business, 1)
    db.session.delete(business)
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_cross_tenant_payment_is_blocked():
    order = db.session.scalar(select(RestaurantOrder).where(RestaurantOrder.business_id == 1, RestaurantOrder.status == "paid"))
    method = db.session.scalar(select(PaymentMethod).where(PaymentMethod.business_id == 2))
    with pytest.raises(TenantAccessError):
        capture_payment(
            order_id=order.id,
            payment_method_id=method.id,
            amount=order.grand_total,
            actor_business_id=2,
        )
    db.session.rollback()


def test_second_full_payment_is_refused():
    order = db.session.scalar(select(RestaurantOrder).where(RestaurantOrder.business_id == 1, RestaurantOrder.status == "paid"))
    method = db.session.scalar(select(PaymentMethod).where(
        PaymentMethod.business_id == 1, PaymentMethod.code == "cash"
    ))
    with pytest.raises(PaymentError):
        capture_payment(
            order_id=order.id,
            payment_method_id=method.id,
            amount=order.grand_total,
            actor_business_id=1,
        )
    db.session.rollback()


def test_receipt_finalisation_is_idempotent():
    order = db.session.scalar(
        select(RestaurantOrder).where(RestaurantOrder.dataset_code == "SYNTHETIC_HISTORY_V1", RestaurantOrder.status == "paid")
    )
    first = finalize_receipt(order.id, actor_business_id=order.business_id)
    second = finalize_receipt(order.id, actor_business_id=order.business_id)
    assert first.id == second.id
    db.session.rollback()


def test_recipe_consumption_does_not_double_deduct():
    reference = db.session.scalar(
        select(StockMovement.reference_code).where(
            StockMovement.movement_type == "recipe_consumption",
            StockMovement.reference_code.like("HCONS-%"),
        ).limit(1)
    )
    order = db.session.scalar(
        select(RestaurantOrder).where(RestaurantOrder.order_number == reference.removeprefix("HCONS-"))
    )
    before = db.session.scalar(select(db.func.count()).select_from(StockMovement).where(
        StockMovement.reference_code == f"HCONS-{order.order_number}"
    ))
    post_recipe_consumption(order.id, actor_business_id=order.business_id)
    post_recipe_consumption(order.id, actor_business_id=order.business_id)
    after = db.session.scalar(select(db.func.count()).select_from(StockMovement).where(
        StockMovement.reference_code == f"HCONS-{order.order_number}"
    ))
    assert before == after
    assert after >= 1
    db.session.rollback()


def test_transfer_cannot_cross_businesses():
    source = db.session.scalar(select(Branch).where(Branch.business_id == 1).order_by(Branch.id))
    other = db.session.scalar(select(Branch).where(Branch.business_id == 3).order_by(Branch.id))
    item = db.session.scalar(select(InventoryItem).where(InventoryItem.business_id == 1))
    with pytest.raises(TenantAccessError):
        post_transfer(
            business_id=1,
            from_branch_id=source.id,
            to_branch_id=other.id,
            transfer_number="SHOULD-NOT-POST",
            lines=[{"item_id": item.id, "quantity": "1"}],
            note="cross tenant",
        )
    db.session.rollback()


def test_hold_and_resume_round_trip():
    business = db.session.get(Business, 1)
    branch = db.session.scalar(select(Branch).where(Branch.business_id == business.id))
    product = db.session.scalar(select(Product).where(Product.business_id == business.id))
    order = RestaurantOrder(
        business_id=business.id,
        branch_id=branch.id,
        order_number="TEST-HOLD-ROLLBACK",
        order_type="takeaway",
        status="open",
        subtotal=money(100),
        discount_total=money(0),
        tax_total=money(0),
        grand_total=money(100),
        dataset_code="TEST_ROLLBACK",
    )
    db.session.add(order)
    db.session.flush()
    hold_order(order.id, actor_business_id=business.id)
    assert order.status == "held"
    resume_order(order.id, actor_business_id=business.id)
    assert order.status == "open"
    db.session.rollback()


def test_business_csv_dry_run_does_not_create_a_tenant(tmp_path):
    before = db.session.scalar(select(db.func.count()).select_from(Business))
    path = tmp_path / "businesses.csv"
    path.write_text(
        "slug,name,business_type,city,trading_since,min_gross_margin_pct\n"
        "lahore-grill-house,Lahore Grill House,restaurant,Lahore,2025-05-01,15\n"
        "canal-view-class-demo,Canal View Class Demo,restaurant,Lahore,2026-01-01,15\n",
        encoding="utf-8",
    )
    result = import_file(path, "businesses", dry_run=True)
    after = db.session.scalar(select(db.func.count()).select_from(Business))
    assert result["status"] == "dry_run"
    assert result["skipped_existing"] == 1
    assert result["inserted"] == 1
    # The dry run must not change the tenant count. Other tenants may already exist,
    # because registration is open, so compare before with after rather than with 3.
    assert before == after
    assert before >= 3


def test_csv_dry_run_does_not_insert_and_rejects_live_email(tmp_path):
    before = db.session.scalar(select(db.func.count()).select_from(Product))
    result = import_file("data/csv_examples/products.csv", "products", dry_run=True)
    after = db.session.scalar(select(db.func.count()).select_from(Product))
    assert result["status"] == "dry_run"
    assert result["inserted"] == 1
    assert before == after
    rejected = import_file("data/csv_examples/staff_rejected.csv", "staff", dry_run=True)
    assert rejected["status"] == "rejected"
    assert rejected["errors"]
