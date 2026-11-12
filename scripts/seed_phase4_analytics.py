"""Store deterministic product snapshots and rule-based recommendations."""
from sqlalchemy import select

from app import create_app, db
from app.models import Business
from app.services.analytics import history_bounds, owner_id, refresh_snapshots
from scripts.common import require_pos_database


def run():
    app = create_app()
    with app.app_context():
        require_pos_database()
        start, end = history_bounds()
        businesses = db.session.scalars(select(Business).where(Business.is_demo.is_(True)).order_by(Business.id)).all()
        try:
            for business in businesses:
                run_row = refresh_snapshots(
                    business,
                    period_start=start,
                    period_end=end,
                    owner_user_id=owner_id(business.id),
                )
                print(business.slug, run_row.run_code, run_row.id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        print("SUCCESS: deterministic snapshots stored")


if __name__ == "__main__":
    run()
