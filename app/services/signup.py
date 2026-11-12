"""Self-service registration: a new tenant with its first branch and owner.

A `users` row on its own cannot do anything in this application: every page needs
a business and a branch to scope its queries. Registration therefore creates the
whole starting set in one transaction, or nothing at all.
"""
import re
from datetime import date

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import db
from app.models import Branch, Business, BusinessUser, PaymentMethod, User
from app.platform_models import (
    BusinessSetting,
    BusinessSubscription,
    Role,
    SubscriptionPlan,
    TaxRule,
)

BUSINESS_TYPES = ("restaurant", "cafe", "retail")
OWNER_ROLE = "owner"
BRANCH_CODE = "MAIN"

# Every business needs a way to take money, so a new tenant starts with the
# conventional three. They can be edited later; none of them is a business fact.
DEFAULT_PAYMENT_METHODS = (
    ("cash", "Cash"),
    ("card", "Card"),
    ("bank", "Bank Transfer"),
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
MIN_PASSWORD = 8


class SignupError(ValueError):
    """A registration problem that is safe to show to the person signing up."""


def _slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "business")[:100]


def _unique_slug(name):
    base = _slugify(name)
    candidate = base
    counter = 2
    while db.session.scalar(select(Business.id).where(Business.slug == candidate)) is not None:
        suffix = f"-{counter}"
        candidate = f"{base[:100 - len(suffix)]}{suffix}"
        counter += 1
        if counter > 500:
            raise SignupError("Could not allocate a business name. Try a different name.")
    return candidate


def _clean(value, label, minimum, maximum):
    text = (value or "").strip()
    if len(text) < minimum:
        raise SignupError(f"Enter a {label}.")
    return text[:maximum]


def register_business(
    *,
    business_name,
    business_type,
    city,
    branch_name,
    owner_name,
    email,
    password,
    password_confirm,
    tax_percent="0",
    area="",
):
    """Create business, settings, branch, payment methods, owner and membership.

    Returns the owner `User`. Commits on success and rolls back on any failure.
    """
    business_name = _clean(business_name, "business name", 2, 140)
    city = _clean(city, "city", 2, 80)
    branch_name = _clean(branch_name, "branch name", 2, 120)
    owner_name = _clean(owner_name, "your name", 2, 100)
    area = (area or "").strip()[:100] or city

    if business_type not in BUSINESS_TYPES:
        raise SignupError("Choose a business type.")

    email = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise SignupError("Enter a valid email address.")
    if len(email) > 150:
        raise SignupError("That email address is too long.")

    if len(password or "") < MIN_PASSWORD:
        raise SignupError(f"Use a password of at least {MIN_PASSWORD} characters.")
    if password != password_confirm:
        raise SignupError("The two passwords do not match.")

    try:
        rate = float(str(tax_percent or "0").replace(",", "").strip() or 0)
    except ValueError:
        raise SignupError("Sales tax must be a number.")
    if rate < 0 or rate >= 100:
        raise SignupError("Sales tax must be between 0 and 100.")

    if db.session.scalar(select(User.id).where(User.email == email)) is not None:
        raise SignupError("An account with that email already exists.")
    if db.session.scalar(select(Role.id).where(Role.code == OWNER_ROLE)) is None:
        raise SignupError("Roles are not configured on this server.")

    try:
        business = Business(
            name=business_name,
            slug=_unique_slug(business_name),
            business_type=business_type,
            city=city,
            is_demo=False,
        )
        db.session.add(business)
        db.session.flush()

        db.session.add(
            BusinessSetting(
                business_id=business.id,
                currency_code="PKR",
                timezone_name="Asia/Karachi",
                trading_since=date.today(),
                receipt_header=f"{business_name}, {city}"[:160],
                receipt_footer="Thank you for your visit"[:240],
                allow_negative_stock=False,
                min_gross_margin_pct=15,
            )
        )

        branch = Branch(
            business_id=business.id,
            code=BRANCH_CODE,
            name=branch_name,
            area=area,
            city=city,
            is_active=True,
        )
        db.session.add(branch)
        db.session.flush()

        for code, label in DEFAULT_PAYMENT_METHODS:
            db.session.add(
                PaymentMethod(business_id=business.id, code=code, label=label, enabled=True)
            )

        if rate > 0:
            db.session.add(
                TaxRule(
                    business_id=business.id,
                    code="STD",
                    label=f"Sales tax {rate:g}%"[:120],
                    rate_percent=f"{rate:.3f}",
                    applies_to="all",
                    is_active=True,
                    is_demo_rate=True,
                    notes="Entered at registration. Illustrative, not tax advice.",
                )
            )

        plan = db.session.scalar(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.monthly_fee_pkr)
            .limit(1)
        )
        if plan is not None:
            db.session.add(
                BusinessSubscription(
                    business_id=business.id,
                    plan_id=plan.id,
                    status="trial",
                    started_on=date.today(),
                    notes="Created at registration",
                )
            )

        owner = User(
            display_name=owner_name,
            email=email,
            password_hash=generate_password_hash(password),
            is_active=True,
            is_platform_admin=False,
            is_synthetic=False,
        )
        db.session.add(owner)
        db.session.flush()

        db.session.add(
            BusinessUser(
                business_id=business.id,
                user_id=owner.id,
                branch_id=None,
                role=OWNER_ROLE,
            )
        )
        db.session.commit()
        return owner
    except Exception:
        db.session.rollback()
        raise
