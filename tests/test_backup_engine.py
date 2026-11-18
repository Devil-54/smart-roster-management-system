import unittest
from datetime import date
from io import BytesIO
import openpyxl
from app import create_app
from app.extensions import db
from app.services.seeder import seed_database
from app.services.scheduler import DeterministicScheduler
from app.services.backup_engine import BackupRecommendationEngine
from app.services.exporter import export_roster_excel
from app.models import Employee, RosterSchedule, RosterAssignment, UnavailabilityIncident

class BackupEngineTestCase(unittest.TestCase):
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

    def test_backup_recommendation_and_substitution(self):
        """Emergency absence must find certified substitutes and execute seamless replacement."""
        scheduler = DeterministicScheduler(month=11, year=2026)
        roster = scheduler.generate()

        target_date = date(2026, 11, 18)

        # Find an employee scheduled to WORK on target date
        work_assignment = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            date=target_date,
            assignment_type='WORK'
        ).first()
        self.assertIsNotNone(work_assignment)

        absent_emp_id = work_assignment.employee_id
        brand_id = work_assignment.brand_id
        process_id = work_assignment.process_id

        # 1. Query backup recommendations
        result = BackupRecommendationEngine.get_backup_candidates(
            roster_id=roster.id,
            employee_id=absent_emp_id,
            incident_date=target_date
        )

        self.assertTrue(result['success'])
        self.assertGreater(len(result['candidates']), 0, "No eligible backup candidates found")

        # Verify top candidate has highest score
        candidates = result['candidates']
        top_cand = candidates[0]
        self.assertGreaterEqual(top_cand['score'], candidates[-1]['score'])

        # 2. Execute Substitution
        sub_result = BackupRecommendationEngine.execute_substitution(
            roster_id=roster.id,
            absent_emp_id=absent_emp_id,
            backup_emp_id=top_cand['employee_id'],
            incident_date=target_date,
            reason="Sudden acute medical sickness"
        )

        self.assertTrue(sub_result['success'])

        # 3. Verify Database State
        # Absent employee is now on LEAVE
        updated_absent = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=absent_emp_id,
            date=target_date
        ).first()
        self.assertEqual(updated_absent.assignment_type, 'LEAVE')

        # Substitute employee is now WORK on that brand and process
        sub_assignment = RosterAssignment.query.filter_by(
            roster_id=roster.id,
            employee_id=top_cand['employee_id'],
            date=target_date
        ).first()
        self.assertEqual(sub_assignment.assignment_type, 'WORK')
        self.assertEqual(sub_assignment.brand_id, brand_id)
        self.assertEqual(sub_assignment.process_id, process_id)

        # Incident is recorded
        incident = UnavailabilityIncident.query.filter_by(
            roster_id=roster.id,
            employee_id=absent_emp_id,
            date=target_date
        ).first()
        self.assertIsNotNone(incident)
        self.assertEqual(incident.status, 'SUBSTITUTED')
        self.assertEqual(incident.substituted_by_id, top_cand['employee_id'])

        workbook = openpyxl.load_workbook(
            BytesIO(export_roster_excel(roster.id).getvalue()),
            read_only=True
        )
        self.assertEqual(
            workbook['Unavailability & Substitutions']['D4'].value,
            'SUBSTITUTED'
        )

if __name__ == '__main__':
    unittest.main()
