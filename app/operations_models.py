"""Shifts, cash, printing, barcodes, scanners, returns and discount approval.

Posted sales, refunds and cash movements are reversed rather than deleted.
"""
from app import db
from app.timeutil import utcnow


class OrderFulfillment(db.Model):
    """How a ticket is handed to the guest: table, counter, takeaway or a delivery drop."""

    __tablename__ = "order_fulfillments"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("restaurant_orders.id", ondelete="RESTRICT"), nullable=False, unique=True)
    fulfillment_type = db.Column(db.String(20), nullable=False)
    contact_label = db.Column(db.String(80), nullable=False)
    area = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.String(200))
    __table_args__ = (
        db.CheckConstraint(
            "fulfillment_type IN ('dine_in','takeaway','counter_pickup','delivery')",
            name="ck_fulfillment_type",
        ),
    )


class CashierShift(db.Model):
    """One cashier's session on one register."""

    __tablename__ = "cashier_shifts"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    register_id = db.Column(db.Integer, db.ForeignKey("cash_registers.id", ondelete="RESTRICT"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    shift_code = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    opening_float = db.Column(db.Numeric(12, 2), nullable=False)
    opened_at = db.Column(db.DateTime(timezone=True), nullable=False)
    closed_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.UniqueConstraint("branch_id", "shift_code", name="uq_shift_branch_code"),
        db.CheckConstraint("status IN ('open','closed')", name="ck_shift_status"),
        db.CheckConstraint("opening_float >= 0", name="ck_shift_float_nonnegative"),
    )


class CashMovement(db.Model):
    """Cash entering or leaving a shift drawer. Amounts are always positive; the type gives the direction."""

    __tablename__ = "cash_movements"
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id", ondelete="RESTRICT"), nullable=False, index=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False)
    movement_type = db.Column(db.String(24), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reference_code = db.Column(db.String(80), nullable=False)
    note = db.Column(db.String(160))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.UniqueConstraint("shift_id", "movement_type", "reference_code", name="uq_cash_movement_reference"),
        db.CheckConstraint("amount > 0", name="ck_cash_movement_positive"),
        db.CheckConstraint(
            "movement_type IN ('sale_cash','cash_in','cash_out','refund_cash')",
            name="ck_cash_movement_type",
        ),
    )


class ShiftReconciliation(db.Model):
    """Counted drawer versus the expected cash from the shift ledger."""

    __tablename__ = "shift_reconciliations"
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id", ondelete="RESTRICT"), nullable=False, unique=True)
    expected_cash = db.Column(db.Numeric(12, 2), nullable=False)
    counted_cash = db.Column(db.Numeric(12, 2), nullable=False)
    variance = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.String(200))
    reconciled_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class PrintJob(db.Model):
    """One requested print of a receipt, kitchen ticket or barcode label."""

    __tablename__ = "print_jobs"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    printer_id = db.Column(db.Integer, db.ForeignKey("printers.id", ondelete="RESTRICT"))
    job_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="queued")
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(200))
    idempotency_key = db.Column(db.String(80), nullable=False, unique=True)
    related_receipt_id = db.Column(db.Integer, db.ForeignKey("receipt_records.id", ondelete="RESTRICT"))
    related_ticket_id = db.Column(db.Integer, db.ForeignKey("kitchen_tickets.id", ondelete="RESTRICT"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        db.CheckConstraint("job_type IN ('receipt','kitchen','barcode_label')", name="ck_print_job_type"),
        db.CheckConstraint("status IN ('queued','sent','printed','failed')", name="ck_print_job_status"),
        db.CheckConstraint("attempt_count >= 0", name="ck_print_attempts_nonnegative"),
    )


class PrinterIssueReport(db.Model):
    """A reported printer problem, optionally tied to the job that failed."""

    __tablename__ = "printer_issue_reports"
    id = db.Column(db.Integer, primary_key=True)
    printer_id = db.Column(db.Integer, db.ForeignKey("printers.id", ondelete="RESTRICT"), nullable=False, index=True)
    print_job_id = db.Column(db.Integer, db.ForeignKey("print_jobs.id", ondelete="RESTRICT"))
    reported_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"))
    issue_code = db.Column(db.String(40), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.CheckConstraint("status IN ('open','resolved')", name="ck_printer_issue_status"),
    )


class ProductBarcode(db.Model):
    """Internal barcode for a product. These are synthetic codes, not GS1 registrations."""

    __tablename__ = "product_barcodes"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    barcode = db.Column(db.String(32), nullable=False)
    symbology = db.Column(db.String(20), nullable=False, default="CODE128")
    is_primary = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    __table_args__ = (
        db.UniqueConstraint("business_id", "barcode", name="uq_barcode_business"),
        db.UniqueConstraint("product_id", "barcode", name="uq_barcode_product"),
    )


class ScannerSession(db.Model):
    """A paired camera or USB keyboard-wedge scanner session at a branch."""

    __tablename__ = "scanner_sessions"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    session_code = db.Column(db.String(40), nullable=False, unique=True)
    device_label = db.Column(db.String(80), nullable=False)
    mode = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="paired")
    started_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ended_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.CheckConstraint("mode IN ('camera','keyboard_wedge')", name="ck_scanner_mode"),
        db.CheckConstraint("status IN ('paired','closed')", name="ck_scanner_status"),
    )


class SalesReturn(db.Model):
    """A refund or same-price exchange posted against an existing paid order."""

    __tablename__ = "sales_returns"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("restaurant_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    return_number = db.Column(db.String(50), nullable=False)
    return_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    reason = db.Column(db.String(160), nullable=False)
    refund_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    balance_due = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_method_id = db.Column(db.Integer, db.ForeignKey("payment_methods.id", ondelete="RESTRICT"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    posted_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.UniqueConstraint("business_id", "return_number", name="uq_return_business_number"),
        db.CheckConstraint("return_type IN ('refund','exchange')", name="ck_return_type"),
        db.CheckConstraint("status IN ('draft','posted','voided')", name="ck_return_status"),
        db.CheckConstraint("refund_amount >= 0 AND balance_due >= 0", name="ck_return_amounts"),
    )


class SalesReturnLine(db.Model):
    """One returned order line. replacement_product_id is set for an exchange."""

    __tablename__ = "sales_return_lines"
    id = db.Column(db.Integer, primary_key=True)
    sales_return_id = db.Column(db.Integer, db.ForeignKey("sales_returns.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    replacement_product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"))
    __table_args__ = (
        db.UniqueConstraint("sales_return_id", "order_item_id", name="uq_return_line_item"),
        db.CheckConstraint("quantity > 0 AND amount >= 0", name="ck_return_line_amounts"),
    )


class DiscountApproval(db.Model):
    """Manager decision for a discount that crosses the cashier's limit."""

    __tablename__ = "discount_approvals"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("restaurant_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"))
    discount_kind = db.Column(db.String(20), nullable=False)
    requested_amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    reason = db.Column(db.String(160), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    decided_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.CheckConstraint("discount_kind IN ('fixed','percent')", name="ck_discount_kind"),
        db.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_discount_approval_status"),
        db.CheckConstraint("requested_amount >= 0", name="ck_discount_requested_nonnegative"),
    )


class AuditEvent(db.Model):
    """Append-only note of an important action. Rows are not deleted in normal use."""

    __tablename__ = "audit_events"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"))
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"))
    action = db.Column(db.String(40), nullable=False)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.String(40))
    message = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
