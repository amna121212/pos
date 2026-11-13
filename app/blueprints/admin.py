"""Staff, branches, payment methods, shifts and business settings."""
import re
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import db
from app.models import Branch, BusinessUser, CashRegister, PaymentMethod, User
from app.numbering import next_shift_code
from app.operations_models import AuditEvent, CashierShift, SalesReturn, ShiftReconciliation
from app.order_models import OrderPayment, RestaurantOrder
from app.platform_models import BusinessSetting, Role
from app.security import (
    any_permission_required,
    branch_required,
    can,
    clear_permission_cache,
    context,
    permission_required,
)
from app.services.audit import write_audit
from app.timeutil import utcnow

bp = Blueprint("admin", __name__)

EDITABLE_ROLES = ("owner", "manager", "cashier", "kitchen", "inventory")
MIN_PASSWORD = 8
CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,29}$")


def _decimal(raw, label, *, allow_zero=True, allow_negative=False):
    text = (raw or "").strip().replace(",", "")
    if not text:
        return Decimal("0")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{label} must be a number.")
    if not allow_negative and value < 0:
        raise ValueError(f"{label} cannot be negative.")
    if not allow_zero and value == 0:
        raise ValueError(f"{label} must be greater than zero.")
    return value.quantize(Decimal("0.01"))


@bp.get("/staff")
@permission_required("staff.manage")
@branch_required
def staff():
    ctx = context()
    rows = db.session.execute(
        select(BusinessUser, User, Branch)
        .join(User, User.id == BusinessUser.user_id)
        .outerjoin(Branch, Branch.id == BusinessUser.branch_id)
        .where(BusinessUser.business_id == ctx.business_id)
        .order_by(User.display_name)
    ).all()
    return render_template(
        "admin/staff.html",
        rows=rows,
        can_manage=can("staff.manage"),
        roles=EDITABLE_ROLES,
        me=ctx.user.id,
    )


@bp.post("/staff/<int:membership_id>/role")
@permission_required("staff.manage")
@branch_required
def staff_role(membership_id):
    ctx = context()
    membership = db.session.get(BusinessUser, membership_id)
    if membership is None or membership.business_id != ctx.business_id:
        abort(404)
    role = request.form.get("role")
    if role not in EDITABLE_ROLES:
        abort(400)
    if membership.user_id == ctx.user.id:
        flash("You cannot change your own role.", "error")
        return redirect(url_for("admin.staff"))
    membership.role = role
    clear_permission_cache()
    write_audit(
        action="change_role",
        entity_type="business_user",
        entity_id=membership.id,
        business_id=ctx.business_id,
        branch_id=membership.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Set {membership.user.display_name} to {role}",
    )
    db.session.commit()
    flash("Role updated.", "success")
    return redirect(url_for("admin.staff"))


@bp.post("/staff/<int:membership_id>/active")
@permission_required("staff.manage")
@branch_required
def staff_active(membership_id):
    ctx = context()
    membership = db.session.get(BusinessUser, membership_id)
    if membership is None or membership.business_id != ctx.business_id:
        abort(404)
    if membership.user_id == ctx.user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.staff"))
    member = membership.user
    member.is_active = not member.is_active
    write_audit(
        action="toggle_staff",
        entity_type="user",
        entity_id=member.id,
        business_id=ctx.business_id,
        branch_id=membership.branch_id,
        actor_user_id=ctx.user.id,
        message=f"{member.display_name} {'enabled' if member.is_active else 'disabled'}",
    )
    db.session.commit()
    flash(f"{member.display_name} {'enabled' if member.is_active else 'disabled'}.", "info")
    return redirect(url_for("admin.staff"))


@bp.get("/audit")
@any_permission_required("staff.manage", "business.settings")
@branch_required
def audit():
    """Append-only record of important actions, newest first."""
    ctx = context()
    action = request.args.get("action") or ""
    query = select(AuditEvent)
    if ctx.business_id is not None:
        query = query.where(
            (AuditEvent.business_id == ctx.business_id) | (AuditEvent.business_id.is_(None))
        )
    if action:
        query = query.where(AuditEvent.action == action)
    events = db.session.scalars(query.order_by(AuditEvent.created_at.desc()).limit(200)).all()
    actions = [
        row[0]
        for row in db.session.execute(
            select(AuditEvent.action).distinct().order_by(AuditEvent.action)
        ).all()
    ]
    return render_template("admin/audit.html", events=events, action=action, actions=actions)


@bp.get("/shifts")
@any_permission_required("shift.manage", "staff.manage")
@branch_required
def shifts():
    """Cashier shifts and their reconciliations."""
    from app.operations_models import CashierShift, ShiftReconciliation

    ctx = context()
    rows = db.session.execute(
        select(CashierShift, User, Branch, CashRegister, ShiftReconciliation)
        .join(User, User.id == CashierShift.user_id)
        .join(Branch, Branch.id == CashierShift.branch_id)
        .join(CashRegister, CashRegister.id == CashierShift.register_id)
        .outerjoin(ShiftReconciliation, ShiftReconciliation.shift_id == CashierShift.id)
        .where(
            CashierShift.business_id == ctx.business_id,
            CashierShift.branch_id.in_(ctx.allowed_branch_ids),
        )
        .order_by(CashierShift.opened_at.desc())
        .limit(100)
    ).all()
    expected = {
        shift.id: _expected_cash(shift) for shift, _u, _b, _r, reconciliation in rows
        if shift.status == "open" and reconciliation is None
    }
    registers = db.session.scalars(
        select(CashRegister).where(CashRegister.branch_id == ctx.branch_id).order_by(CashRegister.code)
    ).all()
    return render_template(
        "admin/shifts.html",
        rows=rows,
        expected=expected,
        registers=registers,
        can_manage=can("shift.manage"),
    )


@bp.route("/branches/new", methods=["GET", "POST"])
@permission_required("branch.manage")
@branch_required
def branch_new():
    """Add a location to this business."""
    ctx = context()
    values = {"code": "", "name": "", "area": "", "city": ctx.business.city if ctx.business else ""}
    if request.method == "POST":
        values = {
            "code": request.form.get("code", ""),
            "name": request.form.get("name", ""),
            "area": request.form.get("area", ""),
            "city": request.form.get("city", ""),
        }
        try:
            code = (request.form.get("code") or "").strip().upper()
            name = (request.form.get("name") or "").strip()
            area = (request.form.get("area") or "").strip()
            city = (request.form.get("city") or "").strip()
            if not re.match(r"^[A-Z0-9]{2,20}$", code):
                raise ValueError("Branch code must be 2-20 letters or digits, for example DHA.")
            if len(name) < 2:
                raise ValueError("Enter a branch name.")
            if len(area) < 2:
                raise ValueError("Enter the area the branch sits in.")
            if len(city) < 2:
                raise ValueError("Enter the city.")
            branch = Branch(
                business_id=ctx.business_id,
                code=code,
                name=name[:120],
                area=area[:100],
                city=city[:80],
                is_active=True,
            )
            db.session.add(branch)
            db.session.flush()
            write_audit(
                action="create_branch",
                entity_type="branch",
                entity_id=branch.id,
                business_id=ctx.business_id,
                branch_id=branch.id,
                actor_user_id=ctx.user.id,
                message=f"Added branch {code} {name}",
            )
            db.session.commit()
            flash(f"Branch {code} added.", "success")
            return redirect(url_for("admin.branches"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That branch code is already used in this business.", "error")
    return render_template("admin/branch_form.html", values=values)


@bp.get("/branches")
@permission_required("branch.manage")
@branch_required
def branches():
    ctx = context()
    rows = db.session.scalars(
        select(Branch).where(Branch.business_id == ctx.business_id).order_by(Branch.code)
    ).all()
    return render_template(
        "admin/branches.html", rows=rows, can_manage=can("branch.manage"), current=ctx.branch_id
    )


@bp.post("/branches/<int:branch_id>/edit")
@permission_required("branch.manage")
@branch_required
def branch_edit(branch_id):
    ctx = context()
    branch = db.session.get(Branch, branch_id)
    if branch is None or branch.business_id != ctx.business_id:
        abort(404)
    name = (request.form.get("name") or "").strip()
    area = (request.form.get("area") or "").strip()
    if not name or not area:
        flash("Branch name and area are required.", "error")
        return redirect(url_for("admin.branches"))
    branch.name = name[:120]
    branch.area = area[:100]
    branch.is_active = bool(request.form.get("is_active"))
    db.session.commit()
    flash("Branch updated.", "success")
    return redirect(url_for("admin.branches"))


@bp.route("/settings", methods=["GET", "POST"])
@any_permission_required("business.settings", "branch.manage")
@branch_required
def settings():
    ctx = context()
    row = db.session.scalar(
        select(BusinessSetting).where(BusinessSetting.business_id == ctx.business_id)
    )
    if request.method == "POST":
        if not can("business.settings"):
            abort(403)
        if row is None:
            flash("This business has no settings row.", "error")
            return redirect(url_for("admin.settings"))
        header = (request.form.get("receipt_header") or "").strip()
        footer = (request.form.get("receipt_footer") or "").strip()
        if not header or not footer:
            flash("Receipt header and footer are required.", "error")
            return redirect(url_for("admin.settings"))
        try:
            margin = Decimal((request.form.get("min_gross_margin_pct") or "0").replace(",", ""))
        except InvalidOperation:
            flash("Margin must be a number.", "error")
            return redirect(url_for("admin.settings"))
        if margin < 0 or margin >= 100:
            flash("Margin must be between 0 and 100.", "error")
            return redirect(url_for("admin.settings"))
        row.receipt_header = header[:160]
        row.receipt_footer = footer[:240]
        row.min_gross_margin_pct = margin
        row.allow_negative_stock = bool(request.form.get("allow_negative_stock"))
        write_audit(
            action="update_settings",
            entity_type="business_settings",
            entity_id=row.id,
            business_id=ctx.business_id,
            actor_user_id=ctx.user.id,
            message="Business settings updated",
        )
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))
    return render_template(
        "admin/settings.html", settings=row, can_edit=can("business.settings"), business=ctx.business
    )

# --------------------------------------------------------------- payment methods


@bp.get("/payment-methods")
@permission_required("business.settings")
@branch_required
def payment_methods():
    """What the till offers at checkout."""
    ctx = context()
    rows = db.session.execute(
        select(
            PaymentMethod,
            func.count(OrderPayment.id),
            func.coalesce(func.sum(OrderPayment.amount), 0),
        )
        .outerjoin(OrderPayment, OrderPayment.payment_method_id == PaymentMethod.id)
        .where(PaymentMethod.business_id == ctx.business_id)
        .group_by(PaymentMethod.id)
        .order_by(PaymentMethod.id)
    ).all()
    return render_template(
        "admin/payment_methods.html", rows=rows, can_manage=can("business.settings")
    )


@bp.post("/payment-methods/new")
@permission_required("business.settings")
@branch_required
def payment_method_new():
    ctx = context()
    code = (request.form.get("code") or "").strip().lower()
    label = (request.form.get("label") or "").strip()
    try:
        if not CODE_PATTERN.match(code):
            raise ValueError("Code must be 2-30 characters: letters, digits, dash or underscore.")
        if len(label) < 2:
            raise ValueError("Give the method a label.")
        if db.session.scalar(
            select(PaymentMethod.id).where(
                PaymentMethod.business_id == ctx.business_id, PaymentMethod.code == code
            )
        ):
            raise ValueError("That code is already used in this business.")
        method = PaymentMethod(
            business_id=ctx.business_id, code=code, label=label[:70], enabled=True
        )
        db.session.add(method)
        db.session.flush()
        write_audit(
            action="create_payment_method",
            entity_type="payment_method",
            entity_id=method.id,
            business_id=ctx.business_id,
            branch_id=ctx.branch_id,
            actor_user_id=ctx.user.id,
            message=f"Added payment method {label}",
        )
        db.session.commit()
        flash(f"{label} added.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("That payment method already exists.", "error")
    return redirect(url_for("admin.payment_methods"))


@bp.post("/payment-methods/<int:method_id>/edit")
@permission_required("business.settings")
@branch_required
def payment_method_edit(method_id):
    ctx = context()
    method = db.session.get(PaymentMethod, method_id)
    if method is None or method.business_id != ctx.business_id:
        abort(404)
    label = (request.form.get("label") or "").strip()
    if len(label) < 2:
        flash("Give the method a label.", "error")
        return redirect(url_for("admin.payment_methods"))
    method.label = label[:70]
    method.enabled = bool(request.form.get("enabled"))
    write_audit(
        action="update_payment_method",
        entity_type="payment_method",
        entity_id=method.id,
        business_id=ctx.business_id,
        branch_id=ctx.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Updated payment method {method.label}",
    )
    db.session.commit()
    flash("Payment method saved.", "success")
    return redirect(url_for("admin.payment_methods"))


@bp.post("/payment-methods/<int:method_id>/delete")
@permission_required("business.settings")
@branch_required
def payment_method_delete(method_id):
    ctx = context()
    method = db.session.get(PaymentMethod, method_id)
    if method is None or method.business_id != ctx.business_id:
        abort(404)
    used = int(
        db.session.scalar(
            select(func.count()).select_from(OrderPayment).where(
                OrderPayment.payment_method_id == method.id
            )
        )
        or 0
    )
    if used:
        flash(
            f"{method.label} is used by {used} payment(s). Disable it instead of deleting.",
            "error",
        )
        return redirect(url_for("admin.payment_methods"))
    db.session.delete(method)
    write_audit(
        action="delete_payment_method",
        entity_type="payment_method",
        entity_id=method_id,
        business_id=ctx.business_id,
        branch_id=ctx.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Deleted payment method {method.label}",
    )
    db.session.commit()
    flash("Payment method deleted.", "success")
    return redirect(url_for("admin.payment_methods"))


# ---------------------------------------------------------------- employees


def _branches_for_form(business_id):
    return db.session.scalars(
        select(Branch).where(Branch.business_id == business_id).order_by(Branch.code)
    ).all()


@bp.route("/staff/new", methods=["GET", "POST"])
@permission_required("staff.manage")
@branch_required
def staff_new():
    ctx = context()
    values = {"display_name": "", "email": "", "role": "cashier", "branch_id": ""}
    if request.method == "POST":
        values = {
            "display_name": request.form.get("display_name", ""),
            "email": request.form.get("email", ""),
            "role": request.form.get("role", ""),
            "branch_id": request.form.get("branch_id", ""),
        }
        try:
            display_name = (request.form.get("display_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            role = request.form.get("role") or ""
            branch_id = request.form.get("branch_id", type=int)
            if len(display_name) < 2:
                raise ValueError("Enter the employee's name.")
            if "@" not in email or "." not in email.split("@")[-1]:
                raise ValueError("Enter a valid email address.")
            if len(password) < MIN_PASSWORD:
                raise ValueError(f"Use a password of at least {MIN_PASSWORD} characters.")
            if role not in EDITABLE_ROLES:
                raise ValueError("Choose a role.")
            allowed = {branch.id for branch in _branches_for_form(ctx.business_id)}
            if branch_id is not None and branch_id not in allowed:
                raise ValueError("That branch is not part of this business.")
            if db.session.scalar(select(User.id).where(User.email == email)):
                raise ValueError("That email already has an account.")
            user = User(
                display_name=display_name[:100],
                email=email[:150],
                password_hash=generate_password_hash(password),
                is_active=True,
                is_platform_admin=False,
                is_synthetic=False,
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(
                BusinessUser(
                    business_id=ctx.business_id,
                    user_id=user.id,
                    branch_id=branch_id,
                    role=role,
                )
            )
            write_audit(
                action="create_employee",
                entity_type="user",
                entity_id=user.id,
                business_id=ctx.business_id,
                branch_id=branch_id or ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Added {display_name} as {role}",
            )
            db.session.commit()
            flash(f"{display_name} added.", "success")
            return redirect(url_for("admin.staff"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That account already exists.", "error")
    return render_template(
        "admin/staff_form.html",
        membership=None,
        user=None,
        values=values,
        roles=EDITABLE_ROLES,
        branches=_branches_for_form(ctx.business_id),
    )


@bp.route("/staff/<int:membership_id>/edit", methods=["GET", "POST"])
@permission_required("staff.manage")
@branch_required
def staff_edit(membership_id):
    ctx = context()
    membership = db.session.get(BusinessUser, membership_id)
    if membership is None or membership.business_id != ctx.business_id:
        abort(404)
    user = membership.user
    values = {
        "display_name": user.display_name,
        "email": user.email,
        "role": membership.role,
        "branch_id": str(membership.branch_id or ""),
    }
    if request.method == "POST":
        values = {
            "display_name": request.form.get("display_name", ""),
            "email": user.email,
            "role": request.form.get("role", ""),
            "branch_id": request.form.get("branch_id", ""),
        }
        try:
            display_name = (request.form.get("display_name") or "").strip()
            role = request.form.get("role") or ""
            branch_id = request.form.get("branch_id", type=int)
            if len(display_name) < 2:
                raise ValueError("Enter the employee's name.")
            if role not in EDITABLE_ROLES:
                raise ValueError("Choose a role.")
            allowed = {branch.id for branch in _branches_for_form(ctx.business_id)}
            if branch_id is not None and branch_id not in allowed:
                raise ValueError("That branch is not part of this business.")
            if user.id == ctx.user.id and role != membership.role:
                raise ValueError("You cannot change your own role.")
            user.display_name = display_name[:100]
            membership.role = role
            membership.branch_id = branch_id
            new_password = request.form.get("password") or ""
            if new_password:
                if len(new_password) < MIN_PASSWORD:
                    raise ValueError(f"Use a password of at least {MIN_PASSWORD} characters.")
                user.password_hash = generate_password_hash(new_password)
            clear_permission_cache()
            write_audit(
                action="update_employee",
                entity_type="user",
                entity_id=user.id,
                business_id=ctx.business_id,
                branch_id=branch_id or ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Updated {display_name} ({role})",
            )
            db.session.commit()
            flash("Employee saved.", "success")
            return redirect(url_for("admin.staff"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template(
        "admin/staff_form.html",
        membership=membership,
        user=user,
        values=values,
        roles=EDITABLE_ROLES,
        branches=_branches_for_form(ctx.business_id),
    )


@bp.post("/staff/<int:membership_id>/delete")
@permission_required("staff.manage")
@branch_required
def staff_delete(membership_id):
    ctx = context()
    membership = db.session.get(BusinessUser, membership_id)
    if membership is None or membership.business_id != ctx.business_id:
        abort(404)
    user = membership.user
    if user.id == ctx.user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.staff"))

    shift_count = int(
        db.session.scalar(
            select(func.count()).select_from(CashierShift).where(CashierShift.user_id == user.id)
        )
        or 0
    )
    audit_count = int(
        db.session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_user_id == user.id)
        )
        or 0
    )
    if shift_count or audit_count:
        flash(
            f"{user.display_name} has {shift_count} shift(s) and {audit_count} audit entr(y/ies). "
            "Disable the account instead of deleting it.",
            "error",
        )
        return redirect(url_for("admin.staff"))

    owners = int(
        db.session.scalar(
            select(func.count())
            .select_from(BusinessUser)
            .where(BusinessUser.business_id == ctx.business_id, BusinessUser.role == "owner")
        )
        or 0
    )
    if membership.role == "owner" and owners <= 1:
        flash("This is the last owner. Promote another owner first.", "error")
        return redirect(url_for("admin.staff"))

    name = user.display_name
    db.session.delete(membership)
    db.session.flush()
    remaining = int(
        db.session.scalar(
            select(func.count()).select_from(BusinessUser).where(BusinessUser.user_id == user.id)
        )
        or 0
    )
    if remaining == 0:
        db.session.delete(user)
    write_audit(
        action="delete_employee",
        entity_type="user",
        entity_id=user.id,
        business_id=ctx.business_id,
        branch_id=ctx.branch_id,
        actor_user_id=ctx.user.id,
        message=f"Deleted {name}",
    )
    db.session.commit()
    flash(f"{name} deleted.", "success")
    return redirect(url_for("admin.staff"))


# ------------------------------------------------------------------- shifts


def _expected_cash(shift):
    """Opening float plus cash taken on this shift, minus posted refunds."""
    business_id = shift.business_id
    cash_methods = select(PaymentMethod.id).where(
        PaymentMethod.business_id == business_id,
        PaymentMethod.code == "cash",
    )
    collected = db.session.scalar(
        select(func.coalesce(func.sum(OrderPayment.amount), 0))
        .join(RestaurantOrder, RestaurantOrder.id == OrderPayment.order_id)
        .where(
            OrderPayment.status == "captured",
            OrderPayment.payment_method_id.in_(cash_methods),
            RestaurantOrder.cashier_shift_id == shift.id,
        )
    ) or 0
    refunded = db.session.scalar(
        select(func.coalesce(func.sum(SalesReturn.refund_amount), 0))
        .join(RestaurantOrder, RestaurantOrder.id == SalesReturn.order_id)
        .where(
            RestaurantOrder.cashier_shift_id == shift.id,
            SalesReturn.status == "posted",
        )
    ) or 0
    return Decimal(shift.opening_float) + Decimal(str(collected)) - Decimal(str(refunded))


@bp.route("/shifts/open", methods=["GET", "POST"])
@permission_required("shift.manage")
@branch_required
def shift_open():
    ctx = context()
    registers = db.session.scalars(
        select(CashRegister).where(CashRegister.branch_id == ctx.branch_id).order_by(CashRegister.code)
    ).all()
    staff_rows = db.session.execute(
        select(BusinessUser, User)
        .join(User, User.id == BusinessUser.user_id)
        .where(
            BusinessUser.business_id == ctx.business_id,
            BusinessUser.role.in_(("cashier", "manager", "owner")),
            User.is_active.is_(True),
        )
        .order_by(User.display_name)
    ).all()
    if request.method == "POST":
        try:
            register_id = request.form.get("register_id", type=int)
            user_id = request.form.get("user_id", type=int)
            opening = _decimal(request.form.get("opening_float"), "Opening float")
            register = next((row for row in registers if row.id == register_id), None)
            if register is None:
                raise ValueError("Choose a cash register for this branch.")
            member = next((row for row in staff_rows if row[1].id == user_id), None)
            if member is None:
                raise ValueError("Choose a cashier who works in this business.")
            already = db.session.scalar(
                select(CashierShift).where(
                    CashierShift.user_id == user_id,
                    CashierShift.branch_id == ctx.branch_id,
                    CashierShift.status == "open",
                )
            )
            if already is not None:
                raise ValueError(
                    f"{member[1].display_name} already has open shift {already.shift_code}."
                )
            branch = db.session.get(Branch, ctx.branch_id)
            shift = CashierShift(
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                register_id=register.id,
                user_id=user_id,
                shift_code=next_shift_code(branch),
                status="open",
                opening_float=opening,
                opened_at=utcnow(),
            )
            db.session.add(shift)
            db.session.flush()
            write_audit(
                action="open_shift",
                entity_type="cashier_shift",
                entity_id=shift.id,
                business_id=ctx.business_id,
                branch_id=ctx.branch_id,
                actor_user_id=ctx.user.id,
                message=f"Opened {shift.shift_code} with float {opening}",
            )
            db.session.commit()
            flash(f"Shift {shift.shift_code} opened.", "success")
            return redirect(url_for("admin.shifts"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
        except IntegrityError:
            db.session.rollback()
            flash("That shift code is already in use. Try again.", "error")
    return render_template(
        "admin/shift_open.html", registers=registers, staff=staff_rows, me=ctx.user.id
    )


@bp.post("/shifts/<int:shift_id>/close")
@permission_required("shift.manage")
@branch_required
def shift_close(shift_id):
    ctx = context()
    shift = db.session.get(CashierShift, shift_id)
    if shift is None or shift.business_id != ctx.business_id:
        abort(404)
    if shift.branch_id not in ctx.allowed_branch_ids:
        abort(403)
    if shift.status == "closed":
        flash("That shift is already closed.", "warn")
        return redirect(url_for("admin.shifts"))
    try:
        counted = _decimal(request.form.get("counted_cash"), "Counted cash")
        expected = _expected_cash(shift)
        shift.status = "closed"
        shift.closed_at = utcnow()
        db.session.add(
            ShiftReconciliation(
                shift_id=shift.id,
                expected_cash=expected,
                counted_cash=counted,
                variance=counted - expected,
                note=(request.form.get("note") or "")[:200] or None,
                reconciled_at=utcnow(),
            )
        )
        write_audit(
            action="close_shift",
            entity_type="cashier_shift",
            entity_id=shift.id,
            business_id=ctx.business_id,
            branch_id=shift.branch_id,
            actor_user_id=ctx.user.id,
            message=f"Closed {shift.shift_code}: expected {expected}, counted {counted}",
        )
        db.session.commit()
        flash(
            f"Shift {shift.shift_code} closed. Variance {counted - expected:+.2f}.",
            "success",
        )
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    except IntegrityError:
        db.session.rollback()
        flash("That shift already has a reconciliation.", "error")
    return redirect(url_for("admin.shifts"))
