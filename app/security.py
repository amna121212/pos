"""Who is signed in, which business and branch they act for, what they may do.

Every page and every query goes through the context built here, so a cashier
cannot read another branch by editing a URL or a form field.
"""
from dataclasses import dataclass, field
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from sqlalchemy import select

from app import db
from app.models import Branch, Business, BusinessUser, User
from app.platform_models import Permission, Role, RolePermission

PLATFORM_ROLE = "platform_admin"


@dataclass
class Context:
    """The acting user reduced to the facts a template or query needs."""

    user: User | None = None
    memberships: list = field(default_factory=list)
    business: Business | None = None
    role: str | None = None
    branch: Branch | None = None
    permissions: frozenset = frozenset()
    branches: list = field(default_factory=list)
    businesses: list = field(default_factory=list)

    @property
    def authenticated(self):
        return self.user is not None

    @property
    def business_id(self):
        return self.business.id if self.business is not None else None

    @property
    def branch_id(self):
        return self.branch.id if self.branch is not None else None

    @property
    def is_platform_admin(self):
        return bool(self.user and self.user.is_platform_admin)

    @property
    def can_switch_business(self):
        """Only a platform admin, or a user invited to more than one business."""
        return self.is_platform_admin or len(self.businesses) > 1

    @property
    def allowed_branch_ids(self):
        return [branch.id for branch in self.branches]


def _anonymous():
    return Context()


def load_context():
    """Build the request context once and cache it on flask.g.

    The cache is keyed by the session values it was built from, so a branch
    switch, a sign-out or a re-used application context can never serve a
    stale identity.
    """
    cached = g.get("ctx")
    if cached is not None and g.get("ctx_key") == _fingerprint():
        return cached
    g.ctx = _build_context()
    g.ctx_key = _fingerprint()
    return g.ctx


def _fingerprint():
    return (session.get("uid"), session.get("bid"), session.get("branch_id"))


def context():
    return load_context()


def _build_context():
    user_id = session.get("uid")
    if not user_id:
        return _anonymous()
    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        session.clear()
        return _anonymous()

    memberships = list(
        db.session.scalars(
            select(BusinessUser).where(BusinessUser.user_id == user.id)
        ).all()
    )

    if user.is_platform_admin:
        # The super admin is not a member of any one restaurant, so the business
        # comes from the picker instead of from a membership row.
        businesses = list(db.session.scalars(select(Business).order_by(Business.id)).all())
        if not businesses:
            return Context(user=user, memberships=memberships, permissions=_role_permissions(PLATFORM_ROLE))
        business = _chosen_business(businesses)
        branches = _branches_of(business.id)
        return Context(
            user=user,
            memberships=memberships,
            businesses=businesses,
            business=business,
            role=PLATFORM_ROLE,
            branch=_choose_branch(branches),
            permissions=_role_permissions(PLATFORM_ROLE),
            branches=branches,
        )

    if not memberships:
        session.clear()
        return _anonymous()

    businesses = _membership_businesses(memberships)
    chosen = None
    stored_business = session.get("bid")
    for membership in memberships:
        if membership.business_id == stored_business:
            chosen = membership
            break
    if chosen is None:
        chosen = memberships[0]
        session["bid"] = chosen.business_id

    business = chosen.business or db.session.get(Business, chosen.business_id)
    branches = _branches_for(chosen)
    return Context(
        user=user,
        memberships=memberships,
        businesses=businesses,
        business=business,
        role=chosen.role,
        branch=_choose_branch(branches),
        permissions=_role_permissions(chosen.role),
        branches=branches,
    )


def _membership_businesses(memberships):
    """Every business this user may act for, in a stable order."""
    seen = {}
    for membership in memberships:
        business = membership.business or db.session.get(Business, membership.business_id)
        if business is not None and business.id not in seen:
            seen[business.id] = business
    return sorted(seen.values(), key=lambda business: business.id)


def _chosen_business(businesses):
    """Honour the business picker, otherwise fall back to the first one available."""
    wanted = session.get("bid")
    for business in businesses:
        if business.id == wanted:
            return business
    business = businesses[0]
    session["bid"] = business.id
    return business


def _branches_of(business_id):
    return list(
        db.session.scalars(
            select(Branch).where(Branch.business_id == business_id).order_by(Branch.id)
        ).all()
    )


def _branches_for(membership):
    if membership.branch_id:
        branch = db.session.get(Branch, membership.branch_id)
        return [branch] if branch is not None else []
    return _branches_of(membership.business_id)


def _choose_branch(branches):
    """Honour the branch picker, otherwise fall back to the first branch in scope."""
    if not branches:
        return None
    wanted = session.get("branch_id")
    for branch in branches:
        if branch.id == wanted:
            return branch
    branch = branches[0]
    session["branch_id"] = branch.id
    return branch


_ROLE_PERMISSION_CACHE = {}


def _role_permissions(role_code):
    """Permission codes granted to a role. Cached because the table rarely changes."""
    if role_code in _ROLE_PERMISSION_CACHE:
        return _ROLE_PERMISSION_CACHE[role_code]
    if role_code == PLATFORM_ROLE:
        codes = frozenset(db.session.scalars(select(Permission.code)).all())
    else:
        rows = db.session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(Role.code == role_code)
        ).all()
        codes = frozenset(row[0] for row in rows)
    _ROLE_PERMISSION_CACHE[role_code] = codes
    return codes


def has_permission(code):
    return code in context().permissions


def can(code):
    """Template helper: can('report.view')."""
    return has_permission(code)


def clear_permission_cache():
    _ROLE_PERMISSION_CACHE.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        ctx = load_context()
        if not ctx.authenticated:
            return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
        return view(*args, **kwargs)

    return wrapped


def business_required(view):
    """Pages that need a tenant. Platform admins are sent to the platform console."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        ctx = load_context()
        if not ctx.authenticated:
            return redirect(url_for("auth.login"))
        if ctx.business is None:
            return redirect(url_for("platform.index"))
        return view(*args, **kwargs)

    return wrapped


def branch_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        ctx = load_context()
        if not ctx.authenticated:
            return redirect(url_for("auth.login"))
        if ctx.business is None:
            return redirect(url_for("platform.index"))
        if ctx.branch is None:
            abort(403, description="No branch is assigned to this account.")
        return view(*args, **kwargs)

    return wrapped


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


def any_permission_required(*codes):
    """Allow the page when the account holds at least one of these permissions."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            ctx = load_context()
            if not ctx.authenticated:
                return redirect(url_for("auth.login"))
            if not ctx.permissions.intersection(codes):
                abort(403, description="This account does not have the required permission.")
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_branch_access(branch_id):
    """Raise 403 unless the acting user is allowed to touch this branch."""
    ctx = load_context()
    if branch_id not in ctx.allowed_branch_ids:
        abort(403, description="That branch is outside your access.")
    return db.session.get(Branch, branch_id)


def require_business_id():
    """Business id for tenant queries, or 403 for a platform-only account."""
    ctx = load_context()
    if ctx.business_id is None:
        abort(403, description="This page needs a business account.")
    return ctx.business_id


def select_branch(branch_id):
    """Switch the working branch after checking the user is allowed there."""
    ctx = load_context()
    if branch_id not in ctx.allowed_branch_ids:
        abort(403, description="That branch is outside your access.")
    session["branch_id"] = branch_id
    return branch_id


def branch_options():
    """Branches per selectable business, for the picker to fill in client side.

    The picker lets someone choose a restaurant and a branch and then press Apply,
    so the page needs every branch of every business it is allowed to show.
    Computed per call: one indexed query per page render, and no cache to go stale
    when the acting identity changes inside a long-lived application context.
    """
    ctx = load_context()
    business_ids = [business.id for business in ctx.businesses]
    rows = []
    if business_ids:
        rows = list(
            db.session.scalars(
                select(Branch)
                .where(Branch.business_id.in_(business_ids))
                .order_by(Branch.business_id, Branch.code)
            ).all()
        )
    allowed = set(ctx.allowed_branch_ids)
    return [
        {
            "id": business.id,
            "name": business.name,
            "branches": [
                {"id": branch.id, "code": branch.code, "name": branch.name}
                for branch in rows
                if branch.business_id == business.id
                and (ctx.is_platform_admin or branch.id in allowed)
            ],
        }
        for business in ctx.businesses
    ]


def switch_context(business_id, branch_id=None):
    """Apply a restaurant and branch together.

    Used by the top-bar Apply button. The business is only re-selected when it
    actually changes, so picking a different branch does not empty the basket.
    """
    ctx = load_context()
    if not ctx.authenticated:
        abort(403, description="Sign in first.")

    business = ctx.business
    if business_id is not None and business_id != ctx.business_id:
        business = select_business(business_id)

    branch = ctx.branch
    if branch_id is not None:
        if branch_id not in load_context().allowed_branch_ids:
            abort(403, description="That branch is outside your access.")
        session["branch_id"] = branch_id
        branch = load_context().branch
    elif business is not None:
        branch = load_context().branch
    return business, branch


def select_business(business_id):
    """Switch the working business, then leave the branch to be chosen again.

    A platform admin may select any business. Any other account may only select a
    business it holds a `business_users` row for, so editing the form field cannot
    cross a tenant boundary.
    """
    ctx = load_context()
    if not ctx.authenticated:
        abort(403, description="Sign in first.")

    allowed = {business.id for business in ctx.businesses}
    if business_id not in allowed:
        abort(403, description="That business is outside your access.")

    business = db.session.get(Business, business_id)
    if business is None:
        abort(404)

    session["bid"] = business.id
    # The old branch belongs to the old business, and basket prices are branch
    # specific, so both are dropped and rebuilt for the new tenant.
    session.pop("branch_id", None)
    from app.cart import clear as clear_cart

    clear_cart()
    return business
