import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models import RosterSchedule, apply_sqlite_migrations
from app.services.scheduler import DeterministicScheduler
from app.services.seeder import seed_database
from app.services.validator import validate_roster

app = create_app(os.environ.get('FLASK_ENV', 'development'))


def initialize_database():
    with app.app_context():
        db.create_all()
        apply_sqlite_migrations(db.engine)
        seed_database()

        if not RosterSchedule.query.first():
            target_month = 11
            target_year = 2026
            print(f"[Init] Auto-generating baseline production roster for {target_month:02d}/{target_year}...")
            try:
                scheduler = DeterministicScheduler(month=target_month, year=target_year)
                roster = scheduler.generate(roster_name="November 2026 Production Operations Roster")
                print(f"[Init] Generated baseline roster '{roster.name}' with {roster.total_shifts_scheduled} shifts and {roster.conflicts_count} conflicts.")
            except Exception as e:
                print(f"[Init] Note during baseline roster generation: {e}")

        latest_roster = RosterSchedule.query.order_by(
            RosterSchedule.year.desc(),
            RosterSchedule.month.desc()
        ).first()
        if latest_roster:
            conflicts = validate_roster(latest_roster.id)
            latest_roster.conflicts_count = len(conflicts)
            db.session.commit()
            print(
                f"[Init] Revalidated '{latest_roster.name}': "
                f"{len(conflicts)} open conflict(s); prior findings retained."
            )


initialize_database()
