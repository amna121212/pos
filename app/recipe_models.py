"""Recipes, kitchen stations and where a menu item is prepared.

A finished plate is a product. Flour, chicken and buns are inventory items.
The recipe is the link between those two ideas.
"""
from app import db


class Recipe(db.Model):
    """One recipe yields one serving of one menu product."""

    __tablename__ = "recipes"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, unique=True)
    name = db.Column(db.String(140), nullable=False)
    yield_qty = db.Column(db.Numeric(10, 3), nullable=False, default=1)
    notes = db.Column(db.String(240))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    lines = db.relationship("RecipeLine", back_populates="recipe")
    __table_args__ = (
        db.CheckConstraint("yield_qty > 0", name="ck_recipe_yield_positive"),
    )


class RecipeLine(db.Model):
    """Ingredient quantity used by one recipe. Quantity is in the ingredient's stock unit."""

    __tablename__ = "recipe_lines"
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey("recipes.id", ondelete="RESTRICT"), nullable=False, index=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    unit = db.Column(db.String(24), nullable=False)
    recipe = db.relationship("Recipe", back_populates="lines")
    __table_args__ = (
        db.UniqueConstraint("recipe_id", "inventory_item_id", name="uq_recipe_ingredient"),
        db.CheckConstraint("quantity > 0", name="ck_recipe_line_qty_positive"),
    )


class KitchenStation(db.Model):
    """A preparation area inside one branch, such as the grill or the pizza oven."""

    __tablename__ = "kitchen_stations"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    printer_id = db.Column(db.Integer, db.ForeignKey("printers.id", ondelete="RESTRICT"))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")
    __table_args__ = (
        db.UniqueConstraint("branch_id", "code", name="uq_station_branch_code"),
        # Composite key so a route cannot point at a station in another branch.
        db.UniqueConstraint("id", "branch_id", name="uq_station_id_branch"),
    )


class ProductStationRoute(db.Model):
    """Sends one menu product to exactly one station in a branch."""

    __tablename__ = "product_station_routes"
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    station_id = db.Column(db.Integer, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("branch_id", "product_id", name="uq_product_station_branch"),
        db.ForeignKeyConstraint(
            ["station_id", "branch_id"],
            ["kitchen_stations.id", "kitchen_stations.branch_id"],
            name="fk_route_station_branch",
            ondelete="RESTRICT",
        ),
    )
