"""Sign in, sign out, register a new business, and the branch the till works from."""
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from app import db
from app.cart import clear as clear_cart
from app.models import BusinessUser, User
from app.security import load_context, login_required
from app.services.audit import write_audit
from app.services.signup import BUSINESS_TYPES, SignupError, register_business

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only redirect inside this site."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path or ""
    if not path.startswith("/") or path.startswith("//"):
        return None
    return path + (("?" + parsed.query) if parsed.query else "")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = db.session.scalar(select(User).where(User.email == email))
        if user is None or not user.is_active or not check_password_hash(user.password_hash, password):
            flash("Email or password is not correct.", "error")
            return render_template("auth/login.html", email=email), 401

        membership = db.session.scalar(
            select(BusinessUser).where(BusinessUser.user_id == user.id)
        )
        session.clear()
        session.permanent = True
        session["uid"] = user.id
        if membership is not None:
            session["bid"] = membership.business_id
            if membership.branch_id:
                session["branch_id"] = membership.branch_id
        load_context()
        target = _safe_next(request.form.get("next"))
        return redirect(target or url_for("dashboard.index"))

    if session.get("uid"):
        load_context()
        return redirect(url_for("dashboard.index"))
    return render_template("auth/login.html", email="", next=_safe_next(request.args.get("next")))


@bp.post("/logout")
@login_required
def logout():
    clear_cart()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Create a new business with its first branch and an owner account."""
    if not current_app.config.get("SIGNUP_ENABLED", True):
        abort(404)

    if request.method == "POST":
        try:
            owner = register_business(
                business_name=request.form.get("business_name"),
                business_type=request.form.get("business_type"),
                city=request.form.get("city"),
                branch_name=request.form.get("branch_name"),
                owner_name=request.form.get("owner_name"),
                email=request.form.get("email"),
                password=request.form.get("password"),
                password_confirm=request.form.get("password_confirm"),
                tax_percent=request.form.get("tax_percent"),
                area=request.form.get("area"),
            )
        except SignupError as error:
            return (
                render_template(
                    "auth/signup.html",
                    error=str(error),
                    form=request.form,
                    business_types=BUSINESS_TYPES,
                ),
                400,
            )
        except IntegrityError:
            db.session.rollback()
            return (
                render_template(
                    "auth/signup.html",
                    error="That email address is already registered.",
                    form=request.form,
                    business_types=BUSINESS_TYPES,
                ),
                400,
            )

        session.clear()
        session.permanent = True
        session["uid"] = owner.id
        load_context()
        flash("Account created. Add products to start selling.", "success")
        return redirect(url_for("dashboard.index"))

    if session.get("uid"):
        load_context()
        return redirect(url_for("dashboard.index"))
    return render_template(
        "auth/signup.html", error=None, form={}, business_types=BUSINESS_TYPES
    )


@bp.post("/context")
@login_required
def switch_context():
    """Apply the restaurant and branch chosen in the top-bar picker.

    One request for both, so choosing a restaurant does not fire a reload before
    the branch has been picked.
    """
    from app.security import context as current_context
    from app.security import switch_context as apply_context

    ctx = current_context()
    was_admin = ctx.is_platform_admin
    business_id = request.form.get("business_id", type=int)
    branch_id = request.form.get("branch_id", type=int)
    business_changed = business_id is not None and business_id != ctx.business_id

    business, branch = apply_context(business_id, branch_id)

    if was_admin:
        if business_changed and business is not None:
            write_audit(
                action="switch_business",
                entity_type="business",
                entity_id=business.id,
                business_id=business.id,
                actor_user_id=ctx.user.id,
                message=f"Super admin switched to {business.name}",
            )
        if branch is not None:
            write_audit(
                action="switch_branch",
                entity_type="branch",
                entity_id=branch.id,
                business_id=branch.business_id,
                branch_id=branch.id,
                actor_user_id=ctx.user.id,
                message=f"Super admin switched to branch {branch.code} ({branch.name})",
            )
        db.session.commit()

    load_context()
    fresh = current_context()
    label = " · ".join(
        part
        for part in (
            business.name if business is not None else "",
            f"{branch.code} {branch.name}" if branch is not None else "",
        )
        if part
    )
    if _wants_json():
        return jsonify(_context_payload(fresh, f"Working context: {label}"))
    flash(f"Working context: {label}", "info")
    target = _safe_next(request.form.get("next")) or url_for("dashboard.index")
    return redirect(target)


@bp.post("/business/<int:business_id>")
@login_required
def switch_business(business_id):
    """Change the working business. Super admin: any. Everyone else: their own."""
    from app.security import context as current_context
    from app.security import select_business

    ctx = current_context()
    was_admin = ctx.is_platform_admin
    business = select_business(business_id)
    if was_admin:
        write_audit(
            action="switch_business",
            entity_type="business",
            entity_id=business.id,
            business_id=business.id,
            actor_user_id=ctx.user.id,
            message=f"Super admin switched to {business.name}",
        )
        db.session.commit()
    load_context()
    if _wants_json():
        return jsonify(_context_payload(current_context(), f"Working business: {business.name}"))
    flash(f"Working business: {business.name}", "info")
    target = _safe_next(request.form.get("next")) or url_for("dashboard.index")
    return redirect(target)


@bp.post("/branch/<int:branch_id>")
@login_required
def switch_branch(branch_id):
    from app.security import context as current_context
    from app.security import select_branch

    ctx = current_context()
    was_admin = ctx.is_platform_admin
    select_branch(branch_id)
    clear_cart()
    branch = current_context().branch
    if was_admin and branch is not None:
        write_audit(
            action="switch_branch",
            entity_type="branch",
            entity_id=branch.id,
            business_id=branch.business_id,
            branch_id=branch.id,
            actor_user_id=ctx.user.id,
            message=f"Super admin switched to branch {branch.code} ({branch.name})",
        )
        db.session.commit()
    load_context()
    if _wants_json():
        message = f"Working branch: {branch.name}" if branch is not None else "Working branch changed."
        return jsonify(_context_payload(current_context(), message))
    flash(f"Working branch: {branch.name}" if branch is not None else "Working branch changed.", "info")
    target = _safe_next(request.form.get("next")) or url_for("dashboard.index")
    return redirect(target)


def _wants_json():
    """The reports page switches context in place instead of reloading."""
    return (
        request.headers.get("X-Requested-With") == "fetch"
        or request.accept_mimetypes.best == "application/json"
    )


def _context_payload(ctx, message):
    """Everything a page needs to redraw its selectors after a context switch."""
    return {
        "ok": True,
        "message": message,
        "business": {
            "id": ctx.business_id,
            "name": ctx.business.name if ctx.business is not None else "",
        },
        "branch": {
            "id": ctx.branch_id,
            "code": ctx.branch.code if ctx.branch is not None else "",
            "name": ctx.branch.name if ctx.branch is not None else "",
        },
        "branches": [
            {"id": branch.id, "code": branch.code, "name": branch.name} for branch in ctx.branches
        ],
        "businesses": [
            {"id": business.id, "name": business.name} for business in ctx.businesses
        ],
        "is_platform_admin": ctx.is_platform_admin,
        "role": "" if ctx.is_platform_admin else (ctx.role or ""),
    }
