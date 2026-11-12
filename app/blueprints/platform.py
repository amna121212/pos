"""Platform console for the cross-business administrator."""
from flask import Blueprint, abort, render_template
from sqlalchemy import func, select

from app import db
from app.models import Branch, Business, BusinessUser, Product
from app.intelligence_models import DatasetManifest
from app.order_models import RestaurantOrder
from app.platform_models import BusinessSubscription, SubscriptionPlan, Role
from app.security import load_context

bp = Blueprint("platform", __name__, url_prefix="/platform")


def _require_platform():
    ctx = load_context()
    if not ctx.authenticated:
        abort(403)
    if not ctx.is_platform_admin:
        abort(403)
    return ctx


@bp.get("")
def index():
    ctx = _require_platform()
    rows = db.session.execute(
        select(Business, BusinessSubscription, SubscriptionPlan)
        .outerjoin(BusinessSubscription, BusinessSubscription.business_id == Business.id)
        .outerjoin(SubscriptionPlan, SubscriptionPlan.id == BusinessSubscription.plan_id)
        .order_by(Business.name)
    ).all()

    businesses = []
    for business, subscription, plan in rows:
        branches = int(
            db.session.scalar(
                select(func.count()).select_from(Branch).where(Branch.business_id == business.id)
            )
            or 0
        )
        products = int(
            db.session.scalar(
                select(func.count()).select_from(Product).where(Product.business_id == business.id)
            )
            or 0
        )
        orders = int(
            db.session.scalar(
                select(func.count())
                .select_from(RestaurantOrder)
                .where(RestaurantOrder.business_id == business.id)
            )
            or 0
        )
        people = int(
            db.session.scalar(
                select(func.count())
                .select_from(BusinessUser)
                .where(BusinessUser.business_id == business.id)
            )
            or 0
        )
        businesses.append(
            {
                "business": business,
                "subscription": subscription,
                "plan": plan,
                "branches": branches,
                "products": products,
                "orders": orders,
                "people": people,
            }
        )

    manifests = db.session.scalars(
        select(DatasetManifest).order_by(DatasetManifest.code)
    ).all()
    roles = db.session.scalars(select(Role).order_by(Role.id)).all()
    return render_template(
        "platform/index.html", businesses=businesses, manifests=manifests, roles=roles
    )


@bp.get("/integrity")
def integrity():
    _require_platform()
    from app.services.integrity import integrity_problems

    problems = integrity_problems()
    return render_template("platform/integrity.html", problems=problems)
