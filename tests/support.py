"""Resolve test accounts from the live database.

The suite must not assume a particular seeded person is still active or still
scoped to a particular branch: an administrator can disable or re-scope staff at
any time from the Employees page. These helpers look an *active* member up by role
and report the branch scope it actually has, so the assertions test the rules
rather than one person's row.
"""
from sqlalchemy import select

from app import db
from app.models import Branch, BusinessUser, User

BUSINESS_ID = 1
PLATFORM_EMAIL_FALLBACK = "platform.admin@example.invalid"


def require(role, business_id=BUSINESS_ID):
    """An active account for this role, or skip the test."""
    import pytest

    user = find(role, business_id)
    if user is None:
        pytest.skip(f"no active {role} account in business {business_id}")
    return user


def find(role, business_id=BUSINESS_ID):
    """The lowest-id active user with this role, or None."""
    if role == "super_admin":
        return db.session.scalar(
            select(User)
            .where(User.is_active.is_(True), User.is_platform_admin.is_(True))
            .order_by(User.id)
        )
    return db.session.scalar(
        select(User)
        .join(BusinessUser, BusinessUser.user_id == User.id)
        .where(
            User.is_active.is_(True),
            BusinessUser.business_id == business_id,
            BusinessUser.role == role,
        )
        .order_by(User.id)
    )


def scope_branch_id(user, business_id=BUSINESS_ID):
    """The branch this account is pinned to, or None when it covers the business."""
    membership = db.session.scalar(
        select(BusinessUser).where(
            BusinessUser.user_id == user.id, BusinessUser.business_id == business_id
        )
    )
    return membership.branch_id if membership is not None else None


def allowed_branches(user, business_id=BUSINESS_ID):
    pinned = scope_branch_id(user, business_id)
    if pinned:
        return [pinned]
    return list(
        db.session.scalars(
            select(Branch.id).where(Branch.business_id == business_id).order_by(Branch.id)
        ).all()
    )


def branch_outside_scope(user, business_id=BUSINESS_ID):
    """A real branch id this account must not be able to read."""
    visible = set(allowed_branches(user, business_id))
    for branch_id in db.session.scalars(
        select(Branch.id).order_by(Branch.id)
    ).all():
        if branch_id not in visible:
            return branch_id
    return None


def branch_inside_scope(user, business_id=BUSINESS_ID):
    branches = allowed_branches(user, business_id)
    return branches[0] if branches else None


def other_business_id(business_id=BUSINESS_ID):
    return db.session.scalar(
        select(Branch.business_id).where(Branch.business_id != business_id).order_by(Branch.business_id)
    )
