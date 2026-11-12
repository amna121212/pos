"""Staff, branches and business settings."""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Branch, BusinessUser, CashRegister, User
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

bp = Blueprint("admin", __name__)

EDITABLE_ROLES = ("owner", "manager", "cashier", "kitchen", "inventory")


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
    from app.operations_models import AuditEvent

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
    return render_template("admin/shifts.html", rows=rows)


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
