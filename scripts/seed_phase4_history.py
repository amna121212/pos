"""Deterministic synthetic trading history for the three demo businesses.

The period is 1 May 2025 through 31 October 2026 in Asia/Karachi.
Re-running the script after a successful finish does not add rows.
A failed run can be started again: finished days are skipped, and stock
movements are idempotent.
"""
import random
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app import create_app, db
from app.intelligence_models import DatasetManifest
from app.inventory_models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryItem,
    StockAdjustment,
    StockBatch,
    SupplierPurchaseItem,
    SupplierPurchaseOrder,
)
from app.models import Branch, BranchProduct, Business, BusinessUser, CashRegister, DiningTable, PaymentMethod, Printer, Product, Supplier, User
from app.money import money, quantity
from app.operations_models import (
    CashMovement,
    CashierShift,
    DiscountApproval,
    OrderFulfillment,
    PrinterIssueReport,
    PrintJob,
    ShiftReconciliation,
)
from app.order_models import (
    DiningSession,
    KitchenTicket,
    KitchenTicketItem,
    OrderDiscount,
    OrderItem,
    OrderItemModifier,
    OrderPayment,
    OrderStatusEvent,
    ReceiptRecord,
    RestaurantOrder,
)
from app.seeddata.catalog import INGREDIENTS
from app.seeddata.naming import PRIMARY_SUPPLIER, extra_suppliers, receipt_footer_for
from app.seeddata.demand import BRANCH_PROFILES, HISTORY_END, HISTORY_START, RAMADAN_END, RAMADAN_START
from app.services.history_plan import choose_order_type, choose_status, payment_plan, price_lines, weighted_choice
from app.services.integrity import integrity_problems
from app.services.inventory import apply_stock_delta
from app.services.recipes import post_recipe_consumption, recipe_requirements
from app.services.returns import create_posted_return
from app.services.transfers import post_transfer
from app.timeutil import pakistan_local, parse_hhmm
from scripts.common import require_pos_database

DATASET = "SYNTHETIC_HISTORY_V1"
SUPPLY_COVER = Decimal("1.30")


def orders_for_day(profile, day, rng):
    count = profile["base"]
    if day.weekday() >= 4:
        count += profile["weekend_boost"]
    if profile.get("ramadan") and RAMADAN_START <= day <= RAMADAN_END:
        count += 2
    if profile.get("winter_boost") and day.month in (12, 1):
        count += 1
    if profile.get("summer_boost") and day.month in (6, 7, 8):
        count += 1
    count += rng.choice((-1, 0, 0, 0, 1))
    return max(0, count)


def build_plans(branches, catalog, modifiers, requirements, tax_rates):
    plans = []
    for branch in branches:
        profile = BRANCH_PROFILES[branch.code]
        products = catalog[branch.id]
        day = HISTORY_START
        while day <= HISTORY_END:
            day_rng = random.Random(f"pos-hist-v1-count|{branch.id}|{day.isoformat()}")
            count = orders_for_day(profile, day, day_rng)
            for seq in range(1, count + 1):
                order_number = f"SYN-{branch.code}-{day:%Y%m%d}-{seq:02d}"
                plans.append(build_plan(
                    branch=branch,
                    profile=profile,
                    products=products,
                    modifiers=modifiers,
                    requirements=requirements,
                    tax_rate=tax_rates[branch.business_id],
                    day=day,
                    order_number=order_number,
                ))
            day += timedelta(days=1)
    return plans


def build_plan(*, branch, profile, products, modifiers, requirements, tax_rate, day, order_number):
    rng = random.Random(f"pos-hist-v1|{order_number}")
    hours = list(profile["hour_weights"])
    hour = weighted_choice(rng, hours, lambda value: profile["hour_weights"][value])
    minute = rng.randrange(0, 30 if hour == 23 else 60)
    when = pakistan_local(day.year, day.month, day.day, hour, minute)
    status = choose_status(rng)
    order_type = choose_order_type(rng, profile["kind"])
    wanted = rng.choice((1, 2, 2, 3, 3, 4) if profile["kind"] == "restaurant" else (1, 1, 2, 2, 3))

    def weight_of(row):
        return row["popularity"] + profile["tag_boost"].get(row["tag"], 0)

    lines = []
    used = set()
    guard = 0
    while len(lines) < wanted and guard < 20:
        guard += 1
        row = weighted_choice(rng, products, weight_of)
        if row["product_id"] in used:
            continue
        used.add(row["product_id"])
        qty = 1
        if row["tag"] in ("bread", "drink", "staple", "snack", "beverage") and rng.random() < 0.35:
            qty = 2
        option_id = None
        modifier_amount = money(0)
        options = modifiers.get(row["product_id"], [])
        if options and rng.random() < 0.25:
            option = rng.choice(options)
            option_id = option["id"]
            modifier_amount = money(money(option["price"]) * qty)
        lines.append({
            "product_id": row["product_id"],
            "quantity": qty,
            "unit_price": row["price"],
            "modifier_amount": modifier_amount,
            "option_id": option_id,
            "note": "Less spicy" if profile["kind"] == "restaurant" and rng.random() < 0.08 else None,
        })
    discount_kind = None
    discount_value = 0
    rejected = None
    if profile["kind"] == "restaurant" and rng.random() < 0.12:
        if rng.random() < 0.5:
            discount_kind, discount_value = "percent", 10
        else:
            discount_kind, discount_value = "fixed", 100
    elif rng.random() < 0.004:
        rejected = ("fixed", Decimal("250"))
    priced, totals = price_lines(
        lines,
        discount_kind=discount_kind or "fixed",
        discount_value=discount_value if discount_kind else 0,
        tax_rate_percent=tax_rate,
    )
    if discount_kind is None:
        totals["discount"] = money(0)
    cash_fraction = None
    card_only = False
    if status == "paid" and totals["grand"] >= money(1500) and rng.random() < 0.22:
        cash_fraction = Decimal("0.60")
    elif status == "paid" and rng.random() < (0.20 if profile["kind"] == "retail" else 0.30):
        card_only = True
    if card_only:
        payments = [{"code": "card", "amount": totals["grand"], "partial": False}] if status == "paid" else payment_plan(grand=totals["grand"], status=status)
    else:
        payments = payment_plan(grand=totals["grand"], status=status, cash_fraction=cash_fraction)
    refund = None
    exchange = None
    if status == "paid" and priced and totals["subtotal"] > 0 and requirements.get(priced[0]["product_id"]):
        if rng.random() < 0.018:
            gross = money(priced[0]["line_total"] + priced[0]["modifier_amount"])
            share = gross / totals["subtotal"]
            refund = {
                "line_index": 0,
                "quantity": priced[0]["quantity"],
                "ex_tax": money(share * (totals["subtotal"] - totals["discount"])),
                "cash": money(share * totals["grand"]),
            }
        elif profile["kind"] == "retail" and rng.random() < 0.012:
            others = [row for row in products if row["product_id"] != priced[0]["product_id"] and requirements.get(row["product_id"])]
            if others:
                replacement = rng.choice(others)
                exchange = {"line_index": 0, "quantity": priced[0]["quantity"], "replacement_product_id": replacement["product_id"]}
    return {
        "business_id": branch.business_id,
        "branch_id": branch.id,
        "branch_code": branch.code,
        "kind": profile["kind"],
        "order_number": order_number,
        "when": when,
        "day": day,
        "status": status,
        "order_type": order_type,
        "guest_count": rng.randint(2, 4),
        "lines": priced,
        "totals": totals,
        "payments": payments,
        "discount_kind": discount_kind,
        "discount_value": discount_value,
        "rejected": rejected,
        "refund": refund,
        "exchange": exchange,
    }


def month_key(day):
    return day.replace(day=1)


def supply_demand(plans, requirements):
    demand = {}
    for plan in plans:
        if plan["status"] != "paid":
            continue
        bucket_key = (plan["branch_id"], month_key(plan["day"]))
        bucket = demand.setdefault(bucket_key, {})
        for line in plan["lines"]:
            for item_id, per_serving, _movement in requirements.get(line["product_id"], []):
                bucket[item_id] = quantity(bucket.get(item_id, 0) + per_serving * line["quantity"])
        exchange = plan["exchange"]
        if exchange:
            for item_id, per_serving, _movement in requirements.get(exchange["replacement_product_id"], []):
                bucket[item_id] = quantity(bucket.get(item_id, 0) + per_serving * exchange["quantity"])
    return demand


def add_transfer_cover(demand, transfers):
    for transfer in transfers:
        key = (transfer["from_branch_id"], HISTORY_START.replace(day=1))
        bucket = demand.setdefault(key, {})
        item_id = transfer["item_id"]
        bucket[item_id] = quantity(bucket.get(item_id, 0) + transfer["quantity"])


def shelf_days_for(sku):
    for ingredient in INGREDIENTS:
        if ingredient.sku == sku:
            return ingredient.shelf_days
    return 0


def create_supply(branches, suppliers, demand):
    made = 0
    items = {item.id: item for item in db.session.scalars(select(InventoryItem)).all()}
    for branch in branches:
        supplier = suppliers[branch.business_id]
        day = HISTORY_START.replace(day=1)
        while day <= HISTORY_END:
            needed = demand.get((branch.id, day), {})
            po_number = f"SYN-PO-{branch.code}-{day:%Y%m}"
            day = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
            if not needed:
                continue
            if db.session.scalar(select(SupplierPurchaseOrder.id).where(
                SupplierPurchaseOrder.business_id == branch.business_id,
                SupplierPurchaseOrder.po_number == po_number,
            )):
                continue
            received_at = pakistan_local(po_number_date(po_number).year, po_number_date(po_number).month, 1, 7, 30)
            po = SupplierPurchaseOrder(
                business_id=branch.business_id,
                branch_id=branch.id,
                supplier_id=supplier,
                po_number=po_number,
                status="received",
                created_at=received_at,
            )
            db.session.add(po)
            db.session.flush()
            receipt = GoodsReceipt(
                purchase_order_id=po.id,
                business_id=branch.business_id,
                branch_id=branch.id,
                receipt_number=f"SYN-GRN-{branch.code}-{po_number[-6:]}",
                received_at=received_at,
            )
            db.session.add(receipt)
            db.session.flush()
            for item_id, raw_qty in needed.items():
                cover = quantity(Decimal(raw_qty) * SUPPLY_COVER)
                if cover <= 0:
                    continue
                item = items[item_id]
                purchase = SupplierPurchaseItem(
                    purchase_order_id=po.id,
                    item_id=item_id,
                    qty_ordered=cover,
                    unit_cost=money(item.standard_cost),
                )
                db.session.add(purchase)
                db.session.flush()
                db.session.add(GoodsReceiptItem(goods_receipt_id=receipt.id, purchase_item_id=purchase.id, quantity=cover))
                shelf = shelf_days_for(item.sku)
                expiry = received_at.date() + timedelta(days=shelf) if shelf else None
                db.session.add(StockBatch(
                    business_id=branch.business_id,
                    branch_id=branch.id,
                    item_id=item_id,
                    batch_number=f"M{received_at:%Y%m}-{branch.id}-{item_id}",
                    received_qty=cover,
                    expiry_date=expiry,
                ))
                apply_stock_delta(
                    business_id=branch.business_id,
                    branch_id=branch.id,
                    item_id=item_id,
                    movement_type="purchase_receipt",
                    delta_qty=cover,
                    reference_code=receipt.receipt_number,
                    created_at=received_at,
                )
            made += 1
    return made


def po_number_date(po_number):
    # SYN-PO-JT-202505
    stamp = po_number.rsplit("-", 1)[-1]
    from datetime import date
    return date(int(stamp[:4]), int(stamp[4:6]), 1)


def create_adjustments(branches):
    for branch in branches:
        if BRANCH_PROFILES[branch.code]["kind"] != "restaurant":
            continue
        code = f"SYN-ADJ-{branch.code}-CHICKEN"
        if db.session.scalar(select(StockAdjustment.id).where(StockAdjustment.adjustment_code == code)):
            continue
        item = db.session.scalar(select(InventoryItem).where(
            InventoryItem.business_id == branch.business_id,
            InventoryItem.sku == "INV-CHICKEN",
        ))
        when = pakistan_local(2025, 6, 15, 9, 0)
        db.session.add(StockAdjustment(
            business_id=branch.business_id,
            branch_id=branch.id,
            item_id=item.id,
            adjustment_code=code,
            delta_qty=quantity("-0.500"),
            reason="Synthetic trim loss",
            created_at=when,
        ))
        apply_stock_delta(
            business_id=branch.business_id,
            branch_id=branch.id,
            item_id=item.id,
            movement_type="stock_adjustment",
            delta_qty=quantity("-0.500"),
            reference_code=code,
            created_at=when,
        )


def create_transfers(transfers):
    for transfer in transfers:
        post_transfer(
            business_id=transfer["business_id"],
            from_branch_id=transfer["from_branch_id"],
            to_branch_id=transfer["to_branch_id"],
            transfer_number=transfer["number"],
            lines=[{"item_id": transfer["item_id"], "quantity": transfer["quantity"]}],
            note="Synthetic move between two branches of the same business.",
        )


def planned_transfers(branches):
    by_business = {}
    for branch in branches:
        by_business.setdefault(branch.business_id, []).append(branch)
    transfers = []
    for business_id, pair in by_business.items():
        pair = sorted(pair, key=lambda row: row.id)
        source, destination = pair[0], pair[1]
        kind = BRANCH_PROFILES[source.code]["kind"]
        if kind == "restaurant":
            item = db.session.scalar(select(InventoryItem).where(
                InventoryItem.business_id == business_id, InventoryItem.sku == "INV-FLOUR"
            ))
            qty = quantity(5)
            number = f"SYN-TR-{business_id:03d}-FLOUR"
        else:
            item = db.session.scalar(select(InventoryItem).where(
                InventoryItem.business_id == business_id, InventoryItem.sku == "INV-DAI-001"
            ))
            qty = quantity(10)
            number = f"SYN-TR-{business_id:03d}-MILK"
        transfers.append({
            "business_id": business_id,
            "from_branch_id": source.id,
            "to_branch_id": destination.id,
            "item_id": item.id,
            "quantity": qty,
            "number": number,
        })
    return transfers


def branch_context(branches):
    context = {}
    for branch in branches:
        cashier = db.session.scalar(select(User.id).join(BusinessUser, BusinessUser.user_id == User.id).where(
            BusinessUser.branch_id == branch.id, BusinessUser.role == "cashier"
        ))
        manager = db.session.scalar(select(User.id).join(BusinessUser, BusinessUser.user_id == User.id).where(
            BusinessUser.branch_id == branch.id, BusinessUser.role == "manager"
        ))
        register = db.session.scalar(select(CashRegister.id).where(
            CashRegister.branch_id == branch.id, CashRegister.code == "COUNTER-01"
        ))
        receipt_printer = db.session.scalar(select(Printer.id).where(
            Printer.branch_id == branch.id, Printer.label == "Receipt printer"
        ))
        kitchen_printer = db.session.scalar(select(Printer.id).where(
            Printer.branch_id == branch.id, Printer.purpose == "kitchen"
        ))
        tables = db.session.scalars(select(DiningTable.id).where(DiningTable.branch_id == branch.id).order_by(DiningTable.id)).all()
        methods = dict(db.session.execute(select(PaymentMethod.code, PaymentMethod.id).where(
            PaymentMethod.business_id == branch.business_id
        )).all())
        context[branch.id] = {
            "cashier_id": cashier,
            "manager_id": manager,
            "register_id": register,
            "receipt_printer_id": receipt_printer,
            "kitchen_printer_id": kitchen_printer,
            "table_ids": list(tables),
            "methods": methods,
        }
        if cashier is None or register is None or "cash" not in methods:
            raise RuntimeError("Branch is missing a cashier, register or cash method: " + branch.code)
    return context


def ensure_shift(plan, ctx):
    code = f"SH-{plan['branch_code']}-{plan['day']:%Y%m%d}"
    shift = db.session.scalar(select(CashierShift).where(
        CashierShift.branch_id == plan["branch_id"], CashierShift.shift_code == code
    ))
    if shift is not None:
        return shift
    profile = BRANCH_PROFILES[plan["branch_code"]]
    opens, closes = {
        "lahore-grill-house": ("08:00", "23:30"),
        "urban-bites-lahore": ("12:00", "23:30"),
        "daily-mart-lahore": ("09:00", "22:00"),
    }[profile["slug"]]
    open_time = parse_hhmm(opens)
    close_time = parse_hhmm(closes)
    shift = CashierShift(
        business_id=plan["business_id"],
        branch_id=plan["branch_id"],
        register_id=ctx["register_id"],
        user_id=ctx["cashier_id"],
        shift_code=code,
        status="closed",
        opening_float=money(5000 if profile["kind"] == "restaurant" else 3000),
        opened_at=pakistan_local(plan["day"].year, plan["day"].month, plan["day"].day, open_time.hour, open_time.minute),
        closed_at=pakistan_local(plan["day"].year, plan["day"].month, plan["day"].day, close_time.hour, close_time.minute),
    )
    db.session.add(shift)
    db.session.flush()
    return shift


def ensure_petty(shift, branch_code, when, seen):
    if branch_code in seen:
        return
    seen.add(branch_code)
    for movement_type, reference, note in (
        ("cash_out", f"PETTY-OUT-{branch_code}", "Synthetic supplier petty cash"),
        ("cash_in", f"PETTY-IN-{branch_code}", "Synthetic owner drawer top-up"),
    ):
        exists = db.session.scalar(select(CashMovement.id).where(
            CashMovement.shift_id == shift.id,
            CashMovement.movement_type == movement_type,
            CashMovement.reference_code == reference,
        ))
        if exists:
            continue
        db.session.add(CashMovement(
            shift_id=shift.id,
            business_id=shift.business_id,
            movement_type=movement_type,
            amount=money(500),
            reference_code=reference,
            note=note,
            created_at=when,
        ))


def choose_table(table_ids, when, free_at):
    for table_id in table_ids:
        if free_at.get(table_id, when) <= when:
            free_at[table_id] = when + timedelta(minutes=50)
            return table_id
    return None


def persist_order(plan, ctx, free_at):
    existing = db.session.scalar(select(RestaurantOrder.id).where(
        RestaurantOrder.branch_id == plan["branch_id"],
        RestaurantOrder.order_number == plan["order_number"],
    ))
    if existing is not None:
        return False
    order_type = plan["order_type"]
    session_id = None
    if order_type == "dine_in" and plan["status"] != "cancelled":
        table_id = choose_table(ctx["table_ids"], plan["when"], free_at)
        if table_id is None:
            order_type = "takeaway"
        else:
            seating = DiningSession(
                business_id=plan["business_id"],
                branch_id=plan["branch_id"],
                dining_table_id=table_id,
                guest_count=plan["guest_count"],
                opened_at=plan["when"],
                closed_at=None if plan["status"] == "held" else plan["when"] + timedelta(minutes=50),
            )
            db.session.add(seating)
            db.session.flush()
            session_id = seating.id
    shift = ensure_shift(plan, ctx)
    order = RestaurantOrder(
        business_id=plan["business_id"],
        branch_id=plan["branch_id"],
        dining_session_id=session_id,
        order_number=plan["order_number"],
        order_type=order_type,
        status=plan["status"],
        subtotal=plan["totals"]["subtotal"],
        discount_total=plan["totals"]["discount"],
        tax_total=plan["totals"]["tax"],
        grand_total=plan["totals"]["grand"],
        tax_rule_id=ctx["tax_rule_id"],
        cashier_shift_id=shift.id,
        dataset_code=DATASET,
        created_at=plan["when"],
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(OrderStatusEvent(
        order_id=order.id, old_status=None, new_status="open",
        message="Synthetic history ticket opened", created_at=plan["when"],
    ))
    item_ids = []
    for line in plan["lines"]:
        item = OrderItem(
            order_id=order.id,
            product_id=line["product_id"],
            quantity=line["quantity"],
            unit_price=line["unit_price"],
            line_total=line["line_total"],
            note=line.get("note"),
        )
        db.session.add(item)
        db.session.flush()
        item_ids.append(item.id)
        if line.get("option_id") is not None:
            db.session.add(OrderItemModifier(
                order_item_id=item.id,
                option_id=line["option_id"],
                price_at_sale=line["modifier_amount"],
            ))
    if plan["totals"]["discount"] > 0:
        label = "Ten percent" if plan["discount_kind"] == "percent" else "Fixed rupee discount"
        db.session.add(OrderDiscount(order_id=order.id, label=label, amount=plan["totals"]["discount"]))
        if plan["discount_kind"] == "percent" or plan["discount_value"] >= 100:
            db.session.add(DiscountApproval(
                business_id=plan["business_id"],
                order_id=order.id,
                requested_by_user_id=ctx["cashier_id"],
                approved_by_user_id=ctx["manager_id"],
                discount_kind=plan["discount_kind"],
                requested_amount=plan["totals"]["discount"],
                status="approved",
                reason="Synthetic manager approval within the demo rule.",
                created_at=plan["when"],
                decided_at=plan["when"],
            ))
    if plan["rejected"]:
        db.session.add(DiscountApproval(
            business_id=plan["business_id"],
            order_id=order.id,
            requested_by_user_id=ctx["cashier_id"],
            approved_by_user_id=ctx["manager_id"],
            discount_kind=plan["rejected"][0],
            requested_amount=money(plan["rejected"][1]),
            status="rejected",
            reason="Synthetic rejection. The discount was not applied.",
            created_at=plan["when"],
            decided_at=plan["when"],
        ))
    contact = {
        "dine_in": "Table guest",
        "takeaway": "Takeaway guest",
        "counter_pickup": "Counter guest",
        "delivery": "Synthetic delivery drop",
    }[order_type]
    db.session.add(OrderFulfillment(
        order_id=order.id,
        fulfillment_type=order_type,
        contact_label=contact,
        area=plan["area"],
        notes="Fictional handoff inside the branch area." if order_type == "delivery" else None,
    ))
    for payment in plan["payments"]:
        if payment["amount"] <= 0:
            continue
        db.session.add(OrderPayment(
            order_id=order.id,
            payment_method_id=ctx["methods"][payment["code"]],
            amount=payment["amount"],
            status="captured",
            paid_at=plan["when"],
        ))
        if payment["code"] == "cash":
            db.session.add(CashMovement(
                shift_id=shift.id,
                business_id=plan["business_id"],
                movement_type="sale_cash",
                amount=payment["amount"],
                reference_code=f"CASH-{plan['order_number']}",
                note="Cash tender on a synthetic ticket",
                created_at=plan["when"],
            ))
    if plan["status"] == "paid":
        db.session.add(OrderStatusEvent(
            order_id=order.id, old_status="open", new_status="paid",
            message="Synthetic payment captured", created_at=plan["when"],
        ))
        post_recipe_consumption(order.id, actor_business_id=plan["business_id"], created_at=plan["when"])
        if plan["kind"] == "restaurant":
            ticket = KitchenTicket(
                order_id=order.id,
                printer_id=ctx["kitchen_printer_id"],
                ticket_number=f"SYN-KOT-{plan['order_number']}",
                status="ready",
                created_at=plan["when"],
            )
            db.session.add(ticket)
            db.session.flush()
            for item_id in item_ids:
                db.session.add(KitchenTicketItem(kitchen_ticket_id=ticket.id, order_item_id=item_id, status="ready"))
            db.session.add(PrintJob(
                business_id=plan["business_id"],
                branch_id=plan["branch_id"],
                printer_id=ctx["kitchen_printer_id"],
                job_type="kitchen",
                status="printed",
                attempt_count=1,
                idempotency_key=f"kot:{ticket.ticket_number}",
                related_ticket_id=ticket.id,
                created_at=plan["when"],
            ))
        receipt = ReceiptRecord(
            order_id=order.id,
            printer_id=ctx["receipt_printer_id"],
            receipt_number=f"SYN-RCPT-{plan['order_number']}",
            print_status="printed",
            issued_at=plan["when"],
        )
        failed = random.Random(f"print|{plan['order_number']}").random() < 0.05
        if failed:
            receipt.print_status = "failed"
        db.session.add(receipt)
        db.session.flush()
        job = PrintJob(
            business_id=plan["business_id"],
            branch_id=plan["branch_id"],
            printer_id=ctx["receipt_printer_id"],
            job_type="receipt",
            status="failed" if failed else "printed",
            attempt_count=2 if failed else 1,
            last_error="Synthetic paper-out on the receipt printer" if failed else None,
            idempotency_key=f"receipt:{receipt.receipt_number}",
            related_receipt_id=receipt.id,
            created_at=plan["when"],
        )
        db.session.add(job)
        db.session.flush()
        if failed:
            db.session.add(PrinterIssueReport(
                printer_id=ctx["receipt_printer_id"],
                print_job_id=job.id,
                reported_by_user_id=ctx["cashier_id"],
                issue_code="paper_out",
                description="Synthetic paper-out recorded so retry status can be demonstrated.",
                status="open",
                created_at=plan["when"],
            ))
        if plan["refund"]:
            method_code = "cash" if any(payment["code"] == "cash" for payment in plan["payments"]) else "card"
            create_posted_return(
                order_id=order.id,
                actor_business_id=plan["business_id"],
                return_number=f"SYN-RET-{plan['order_number']}",
                return_type="refund",
                reason="Synthetic guest changed their mind.",
                lines=[{
                    "order_item_id": item_ids[plan["refund"]["line_index"]],
                    "quantity": plan["refund"]["quantity"],
                    "amount": plan["refund"]["ex_tax"],
                }],
                payment_method_id=ctx["methods"][method_code],
                created_at=plan["when"],
                refund_amount=plan["refund"]["cash"],
            )
            if method_code == "cash" and plan["refund"]["cash"] > 0:
                db.session.add(CashMovement(
                    shift_id=shift.id,
                    business_id=plan["business_id"],
                    movement_type="refund_cash",
                    amount=plan["refund"]["cash"],
                    reference_code=f"REFUND-{plan['order_number']}",
                    note="Cash returned on a synthetic refund",
                    created_at=plan["when"],
                ))
        if plan["exchange"]:
            create_posted_return(
                order_id=order.id,
                actor_business_id=plan["business_id"],
                return_number=f"SYN-EX-{plan['order_number']}",
                return_type="exchange",
                reason="Synthetic even exchange of a grocery item.",
                lines=[{
                    "order_item_id": item_ids[0],
                    "quantity": plan["exchange"]["quantity"],
                    "amount": money(0),
                    "replacement_product_id": plan["exchange"]["replacement_product_id"],
                }],
                payment_method_id=ctx["methods"]["cash"],
                created_at=plan["when"],
                refund_amount=money(0),
            )
    elif plan["status"] == "cancelled":
        db.session.add(OrderStatusEvent(
            order_id=order.id, old_status="open", new_status="cancelled",
            message="Synthetic cancellation before payment", created_at=plan["when"],
        ))
    elif plan["status"] == "partially_paid":
        db.session.add(OrderStatusEvent(
            order_id=order.id, old_status="open", new_status="partially_paid",
            message="Synthetic partial tender left a balance", created_at=plan["when"],
        ))
    return True


def reconcile_shift(shift, day):
    if db.session.scalar(select(ShiftReconciliation.id).where(ShiftReconciliation.shift_id == shift.id)):
        return
    movements = db.session.execute(select(CashMovement.movement_type, CashMovement.amount).where(
        CashMovement.shift_id == shift.id
    )).all()
    expected = money(shift.opening_float)
    for movement_type, amount in movements:
        amount = money(amount)
        if movement_type in ("sale_cash", "cash_in"):
            expected = money(expected + amount)
        else:
            expected = money(expected - amount)
    counted = expected
    note = "Drawer matched the cash ledger."
    if day.weekday() == 6 and expected >= money(20):
        counted = money(expected - money(20))
        note = "Synthetic Sunday difference of 20 PKR. Planted for the reconciliation demo."
    db.session.add(ShiftReconciliation(
        shift_id=shift.id,
        expected_cash=expected,
        counted_cash=counted,
        variance=money(counted - expected),
        note=note,
        reconciled_at=shift.closed_at,
    ))


def group_plans(plans):
    grouped = {}
    for plan in plans:
        grouped.setdefault((plan["branch_id"], plan["day"]), []).append(plan)
    return grouped


def run():
    app = create_app()
    with app.app_context():
        require_pos_database()
        manifest = db.session.scalar(select(DatasetManifest).where(DatasetManifest.code == DATASET))
        if manifest is not None and manifest.status == "complete":
            print("SKIP: synthetic history is already complete")
            return
        if manifest is None:
            raise RuntimeError("Run seed_phase4_master.py before the history generator")
        manifest.status = "running"
        db.session.commit()
        branches = db.session.scalars(select(Branch).join(Business, Business.id == Branch.business_id).where(
            Business.is_demo.is_(True)
        ).order_by(Branch.id)).all()
        catalog = {}
        for branch in branches:
            rows = db.session.execute(select(
                Product.id, Product.sku, BranchProduct.sale_price, Product.business_id
            ).join(BranchProduct, BranchProduct.product_id == Product.id).where(
                BranchProduct.branch_id == branch.id,
                BranchProduct.is_available.is_(True),
            )).all()
            catalog[branch.id] = []
            for product_id, sku, price, business_id in rows:
                from app.seeddata.catalog import meta
                popularity, tag = meta(branch_slug(branches, branch), sku)
                catalog[branch.id].append({
                    "product_id": product_id,
                    "price": money(price),
                    "popularity": popularity,
                    "tag": tag,
                })
        product_ids = [row["product_id"] for rows in catalog.values() for row in rows]
        requirements = recipe_requirements(product_ids)
        modifiers = load_modifiers()
        tax_rates, tax_ids = load_tax()
        areas = {branch.id: branch.area for branch in branches}
        plans = build_plans(branches, catalog, modifiers, requirements, tax_rates)
        print(f"Planned {len(plans)} synthetic tickets")
        transfers = planned_transfers(branches)
        demand = supply_demand(plans, requirements)
        add_transfer_cover(demand, transfers)
        suppliers = {
            row.business_id: row.id
            for row in db.session.scalars(select(Supplier).where(Supplier.name == PRIMARY_SUPPLIER)).all()
        }
        try:
            made = create_supply(branches, suppliers, demand)
            create_adjustments(branches)
            create_transfers(transfers)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        print(f"Supply receipts created this run: {made}")
        context = branch_context(branches)
        for branch_id, ctx in context.items():
            ctx["tax_rule_id"] = tax_ids[db.session.get(Branch, branch_id).business_id]
        grouped = group_plans(plans)
        petty_seen = {
            row.removeprefix("PETTY-IN-")
            for row in db.session.scalars(select(CashMovement.reference_code).where(
                CashMovement.reference_code.like("PETTY-IN-%")
            )).all()
        }
        inserted = 0
        for key in sorted(grouped):
            day_plans = grouped[key]
            first = day_plans[0]
            if db.session.scalar(select(RestaurantOrder.id).where(
                RestaurantOrder.branch_id == first["branch_id"],
                RestaurantOrder.order_number == first["order_number"],
            )):
                continue
            try:
                free_at = {}
                ctx = context[first["branch_id"]]
                shift = None
                for plan in day_plans:
                    plan["area"] = areas[plan["branch_id"]]
                    if persist_order(plan, ctx, free_at):
                        inserted += 1
                    shift = db.session.scalar(select(CashierShift).where(
                        CashierShift.branch_id == plan["branch_id"],
                        CashierShift.shift_code == f"SH-{plan['branch_code']}-{plan['day']:%Y%m%d}",
                    ))
                if shift is not None:
                    ensure_petty(shift, first["branch_code"], first["when"], petty_seen)
                    reconcile_shift(shift, first["day"])
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            if inserted and inserted % 500 < len(day_plans):
                print(f"Inserted about {inserted} tickets, latest {first['order_number']}")
        problems = integrity_problems()
        if problems:
            for problem in problems[:30]:
                print("INTEGRITY", problem)
            raise RuntimeError(f"History integrity failed with {len(problems)} problems")
        manifest = db.session.scalar(select(DatasetManifest).where(DatasetManifest.code == DATASET))
        manifest.status = "complete"
        db.session.commit()
        print(f"SUCCESS: inserted {inserted} synthetic tickets")
        print("orders", db.session.scalar(select(db.func.count()).select_from(RestaurantOrder)))


def branch_slug(branches, branch):
    from app.models import Business
    business = db.session.get(Business, branch.business_id)
    return business.slug


def load_modifiers():
    from app.order_models import MenuModifierGroup, MenuModifierOption
    rows = db.session.execute(select(
        MenuModifierGroup.product_id, MenuModifierOption.id, MenuModifierOption.extra_price
    ).join(MenuModifierOption, MenuModifierOption.group_id == MenuModifierGroup.id)).all()
    modifiers = {}
    for product_id, option_id, price in rows:
        modifiers.setdefault(product_id, []).append({"id": option_id, "price": price})
    return modifiers


def load_tax():
    from app.platform_models import TaxRule
    rates = {}
    ids = {}
    for rule in db.session.scalars(select(TaxRule).where(TaxRule.is_active.is_(True))).all():
        rates[rule.business_id] = Decimal(rule.rate_percent)
        ids[rule.business_id] = rule.id
    return rates, ids


if __name__ == "__main__":
    run()
