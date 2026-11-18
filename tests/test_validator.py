import unittest
from datetime import date
from app import create_app
from app.extensions import db
from app.services.seeder import seed_database
from app.services.scheduler import DeterministicScheduler
from app.services.validator import validate_roster, validate_single_assignment
from app.models import Employee, Brand, Process, ShiftType, RosterSchedule, RosterAssignment, RosterConflict, LeaveRequest

class ValidatorTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        seed_database()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_conflict_detection_scheduled_on_leave(self):
        """Intentionally scheduling an employee on approved leave must be detected and flagged."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()

        emp = Employee.query.first()
        target_date = date(2026, 11, 15)

        # Record approved leave on target date
        leave = LeaveRequest(
            employee_id=emp.id,
            leave_type='PL',
            start_date=target_date,
            end_date=target_date,
            status='APPROVED',
            reason='Intentional test conflict'
        )
        db.session.add(leave)

        # Force a WORK assignment on the leave date
        assignment = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=emp.id,
            date=target_date
        ).first()

        brand = Brand.query.first()
        proc = Process.query.first()
        shift = ShiftType.query.first()

        if assignment:
            assignment.assignment_type = 'WORK'
            assignment.brand_id = brand.id
            assignment.process_id = proc.id
            assignment.shift_type_id = shift.id
        else:
            db.session.add(RosterAssignment(
                roster_id=roster.id,
                employee_id=emp.id,
                date=target_date,
                assignment_type='WORK',
                brand_id=brand.id,
                process_id=proc.id,
                shift_type_id=shift.id
            ))
        db.session.commit()

        # Run validator
        conflicts = validate_roster(roster.id)
        leave_conflicts = [c for c in conflicts if c.conflict_type == 'SCHEDULED_ON_LEAVE' and c.employee_id == emp.id]
        self.assertGreater(len(leave_conflicts), 0, "Validator failed to catch SCHEDULED_ON_LEAVE violation")
        self.assertIn("approved", leave_conflicts[0].message)

    def test_single_assignment_instant_revalidation(self):
        """Instant validation must reject uncertified brand assignment and leave conflict."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()

        emp = Employee.query.first()
        target_date = date(2026, 11, 20)

        # This employee has no certification for Lumina Cosmetics - Accounts.
        lumina = Brand.query.filter_by(code='LMN').first()
        acc = Process.query.filter_by(code='ACC').first()
        shift = ShiftType.query.filter_by(code='G').first()

        result = validate_single_assignment(
            roster_id=roster.id,
            employee_id=emp.id,
            target_date=target_date,
            brand_id=lumina.id,
            process_id=acc.id,
            shift_type_id=shift.id,
            assignment_type='WORK'
        )

        self.assertFalse(result['valid'])
        self.assertGreater(len(result['errors']), 0)
        self.assertTrue(any("not certified" in err for err in result['errors']))

    def test_calendar_override_is_validated_per_process(self):
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()
        emp = Employee.query.filter_by(emp_code='DST002').first()
        target_date = date(2026, 11, 22)
        assignment = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=emp.id,
            date=target_date
        ).first()
        assignment.assignment_type = 'WORK'
        assignment.brand_id = Brand.query.filter_by(code='APX').first().id
        assignment.process_id = Process.query.filter_by(code='ACC').first().id
        assignment.shift_type_id = ShiftType.query.filter_by(code='G').first().id
        db.session.flush()

        conflicts = validate_roster(roster.id)

        self.assertTrue(any(
            conflict.conflict_type == 'CALENDAR_VIOLATION'
            and conflict.employee_id == emp.id
            and conflict.date == target_date
            for conflict in conflicts
        ))

    def test_overlapping_overnight_shifts_are_rejected_and_reported(self):
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()
        emp = Employee.query.filter_by(emp_code='DST014').first()
        first_brand = Brand.query.filter_by(code='LMN').first()
        second_brand = Brand.query.filter_by(code='SWF').first()
        process = Process.query.filter_by(code='CS').first()
        night = ShiftType.query.filter_by(code='N').first()
        morning = ShiftType.query.filter_by(code='M').first()
        first_date = date(2026, 11, 10)
        second_date = date(2026, 11, 11)

        first = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=emp.id,
            date=first_date
        ).first()
        second = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=emp.id,
            date=second_date
        ).first()
        for assignment, brand, shift in (
            (first, first_brand, night),
            (second, second_brand, morning)
        ):
            assignment.assignment_type = 'WORK'
            assignment.brand_id = brand.id
            assignment.process_id = process.id
            assignment.shift_type_id = shift.id
        db.session.flush()

        result = validate_single_assignment(
            roster_id=roster.id,
            employee_id=emp.id,
            target_date=second_date,
            brand_id=second_brand.id,
            process_id=process.id,
            shift_type_id=morning.id
        )
        conflicts = validate_roster(roster.id)

        self.assertFalse(result['valid'])
        self.assertTrue(any('overlaps' in error.lower() for error in result['errors']))
        self.assertTrue(any(
            conflict.conflict_type == 'SHIFT_OVERLAP'
            and conflict.employee_id == emp.id
            for conflict in conflicts
        ))

    def test_revalidation_preserves_old_conflicts_as_resolved_history(self):
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()
        old_conflict = RosterConflict(
            roster_id=roster.id,
            date=date(2026, 11, 1),
            conflict_type='HISTORICAL_TEST',
            severity='WARNING',
            message='Previously recorded assessment finding',
            resolved=False
        )
        db.session.add(old_conflict)
        db.session.commit()

        validate_roster(roster.id)
        db.session.commit()

        saved = RosterConflict.query.filter_by(
            roster_id=roster.id,
            conflict_type='HISTORICAL_TEST'
        ).first()
        self.assertIsNotNone(saved)
        self.assertTrue(saved.resolved)

if __name__ == '__main__':
    unittest.main()
