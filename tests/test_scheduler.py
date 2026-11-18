import unittest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.services.seeder import seed_database
from app.services.scheduler import DeterministicScheduler
from app.models import (
    Employee, Brand, Process, ShiftType, WorkingDayRule, RosterSchedule,
    RosterAssignment, EmployeeAssignment, LeaveRequest
)

class SchedulerTestCase(unittest.TestCase):
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

    def test_database_seeder_workforce_count(self):
        """Verify database contains at least 30 synthetic employees across operational pods."""
        count = Employee.query.count()
        self.assertGreaterEqual(count, 30, f"Expected at least 30 employees, found {count}")
        active_count = Employee.query.filter_by(is_active=True).count()
        self.assertEqual(count, active_count)

    def test_deterministic_scheduler_generation(self):
        """Verify scheduler successfully generates roster with work shifts."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate("Test November Roster")

        self.assertIsNotNone(roster)
        self.assertEqual(roster.month, 11)
        self.assertEqual(roster.year, 2026)
        self.assertGreater(roster.total_shifts_scheduled, 100)

        # Verify assignments were persisted
        assignments = RosterAssignment.query.filter_by(roster_id=roster.id).all()
        self.assertGreater(len(assignments), 0)

    def test_hard_constraint_no_double_booking(self):
        """Hard constraint: An employee cannot have more than 1 work shift on any date."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()

        work_assignments = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            assignment_type='WORK'
        ).all()

        seen_slots = set()
        for a in work_assignments:
            slot = (a.employee_id, a.date)
            self.assertNotIn(slot, seen_slots, f"Double-booking detected for employee {a.employee_id} on {a.date}")
            seen_slots.add(slot)

    def test_hard_constraint_max_consecutive_days(self):
        """Hard constraint: No employee works > max_consecutive_days without a rest day."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()

        employees = Employee.query.all()
        for emp in employees:
            assignments = RosterAssignment.query.filter_by(
                roster_id=roster.id,
                employee_id=emp.id
            ).order_by(RosterAssignment.date).all()

            consecutive_streak = 0
            max_limit = emp.max_consecutive_days or 6

            for a in assignments:
                if a.assignment_type == 'WORK':
                    consecutive_streak += 1
                    self.assertLessEqual(
                        consecutive_streak,
                        max_limit,
                        f"Fatigue rule broken: {emp.name} worked {consecutive_streak} days consecutively on {a.date}"
                    )
                else:
                    consecutive_streak = 0

    def test_hard_constraint_approved_leave_respected(self):
        """Hard constraint: Employees on approved leave must not be scheduled to work."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()

        approved_leaves = LeaveRequest.query.filter_by(status='APPROVED').all()
        for leave in approved_leaves:
            curr = leave.start_date
            while curr <= leave.end_date:
                if curr.month == 11 and curr.year == 2026:
                    a = RosterAssignment.query.filter_by(
                        roster_id=roster.id,
                        employee_id=leave.employee_id,
                        date=curr
                    ).first()

                    if a:
                        self.assertNotEqual(
                            a.assignment_type,
                            'WORK',
                            f"Employee {leave.employee.name} was scheduled to work while on approved leave on {curr}"
                        )
                curr += timedelta(days=1)

    def test_hard_constraint_certification_mapping(self):
        """Hard constraint: Employees can only be assigned to brands and processes they are certified for."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()

        work_shifts = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            assignment_type='WORK'
        ).all()

        for a in work_shifts:
            cert = EmployeeAssignment.query.filter_by(
                employee_id=a.employee_id,
                brand_id=a.brand_id,
                process_id=a.process_id
            ).first()
            self.assertIsNotNone(
                cert,
                f"Unqualified assignment: Employee {a.employee.name} assigned to {a.brand.name} - {a.process.name} without certification."
            )

    def test_scheduler_avoids_overnight_shift_overlap(self):
        employee = Employee.query.filter_by(emp_code='DST014').first()
        Employee.query.filter(Employee.id != employee.id).update(
            {Employee.is_active: False},
            synchronize_session=False
        )
        for rule in WorkingDayRule.query.all():
            rule.is_operating = False
            rule.min_staff_required = 0

        monday_rule = WorkingDayRule.query.filter_by(
            brand_id=Brand.query.filter_by(code='LMN').first().id,
            process_id=Process.query.filter_by(code='CS').first().id,
            day_of_week=0
        ).first()
        tuesday_rule = WorkingDayRule.query.filter_by(
            brand_id=Brand.query.filter_by(code='SWF').first().id,
            process_id=monday_rule.process_id,
            day_of_week=1
        ).first()
        monday_rule.is_operating = True
        monday_rule.min_staff_required = 1
        monday_rule.shift_type_id = ShiftType.query.filter_by(code='N').first().id
        tuesday_rule.is_operating = True
        tuesday_rule.min_staff_required = 1
        tuesday_rule.shift_type_id = ShiftType.query.filter_by(code='M').first().id
        db.session.commit()

        roster = DeterministicScheduler(month=11, year=2026).generate()
        monday = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=employee.id,
            date=date(2026, 11, 2)
        ).first()
        tuesday = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=employee.id,
            date=date(2026, 11, 3)
        ).first()

        self.assertEqual(monday.assignment_type, 'WORK')
        self.assertEqual(monday.shift_type.code, 'N')
        self.assertNotEqual(tuesday.assignment_type, 'WORK')

if __name__ == '__main__':
    unittest.main()
