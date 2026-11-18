import unittest
from io import BytesIO
import openpyxl
from app import create_app
from app.extensions import db
from app.services.seeder import seed_database
from app.services.scheduler import DeterministicScheduler
from app.models import RosterAssignment, RosterConflict

class RoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        seed_database()

        # Generate a test roster
        scheduler = DeterministicScheduler(month=11, year=2026)
        self.roster = scheduler.generate("Test Route Operations Roster")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_dashboard_route(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Smart Roster Operations Dashboard', res.data)
        self.assertIn(b'464 of 464 required staffing slots', res.data)

    def test_employees_list_route(self):
        res = self.client.get('/employees/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Workforce Directory', res.data)

    def test_operations_routes(self):
        res_brands = self.client.get('/operations/brands')
        self.assertEqual(res_brands.status_code, 200)
        res_procs = self.client.get('/operations/processes')
        self.assertEqual(res_procs.status_code, 200)
        res_pods = self.client.get('/operations/pods')
        self.assertEqual(res_pods.status_code, 200)

    def test_leaves_route(self):
        res = self.client.get('/leaves/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Approved Leaves & Comp-Offs', res.data)

    def test_five_roster_views(self):
        # 1. Company View
        res1 = self.client.get(f'/roster/{self.roster.id}/company')
        self.assertEqual(res1.status_code, 200)
        self.assertIn(b'Company-wide Master Roster', res1.data)

        # 2. Pod View
        res2 = self.client.get(f'/roster/{self.roster.id}/pods')
        self.assertEqual(res2.status_code, 200)
        self.assertIn(b'Pod-wise Operational View', res2.data)

        # 3. Brand View
        res3 = self.client.get(f'/roster/{self.roster.id}/brands')
        self.assertEqual(res3.status_code, 200)
        self.assertIn(b'Brand Fulfillment View', res3.data)

        # 4. Process View
        res4 = self.client.get(f'/roster/{self.roster.id}/processes')
        self.assertEqual(res4.status_code, 200)
        self.assertIn(b'Process-wise Coverage', res4.data)

        # 5. Employee View
        res5 = self.client.get(f'/roster/{self.roster.id}/employee')
        self.assertEqual(res5.status_code, 200)
        self.assertIn(b'Individual Employee Schedule', res5.data)

    def test_export_endpoints(self):
        # CSV Export
        res_csv = self.client.get(f'/roster/{self.roster.id}/export/csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, 'text/csv')
        self.assertIn(b'Emp Code,Employee Name', res_csv.data)
        self.assertIn(b'APX-CS-M', res_csv.data)

        # Excel Export
        res_excel = self.client.get(f'/roster/{self.roster.id}/export/excel')
        self.assertEqual(res_excel.status_code, 200)
        self.assertGreater(len(res_excel.data), 1000)
        workbook = openpyxl.load_workbook(BytesIO(res_excel.data), read_only=True)
        self.assertEqual(
            workbook.sheetnames,
            [
                'Master Roster Matrix',
                'Coverage Analysis',
                'Conflicts & Exceptions',
                'Unavailability & Substitutions'
            ]
        )
        self.assertEqual(workbook['Coverage Analysis']['E3'].value, 'Required Staff')
        self.assertEqual(workbook['Conflicts & Exceptions']['E3'].value, 'Status')
        matrix_values = [
            cell.value
            for row in workbook['Master Roster Matrix'].iter_rows()
            for cell in row
        ]
        self.assertIn('APX-CS-M', matrix_values)

    def test_dashboard_reports_staffed_slots_against_demand(self):
        assignment = RosterAssignment.query.filter_by(
            roster_id=self.roster.id,
            assignment_type='WORK'
        ).first()
        assignment.assignment_type = 'WEEKLY_OFF'
        assignment.brand_id = None
        assignment.process_id = None
        assignment.shift_type_id = None
        db.session.commit()

        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'463 of 464 required staffing slots', response.data)

    def test_manual_edit_revalidates_and_preserves_conflict_record(self):
        assignment = RosterAssignment.query.filter_by(
            roster_id=self.roster.id,
            assignment_type='WORK'
        ).first()
        response = self.client.post(
            f'/api/roster/{self.roster.id}/edit_assignment',
            json={
                'employee_id': assignment.employee_id,
                'date': assignment.date.isoformat(),
                'assignment_type': 'WEEKLY_OFF'
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        conflict = RosterConflict.query.filter_by(
            roster_id=self.roster.id,
            conflict_type='UNDER_STAFFED',
            resolved=False
        ).first()
        self.assertIsNotNone(conflict)

        revalidation = self.client.post(f'/roster/{self.roster.id}/revalidate')
        self.assertEqual(revalidation.status_code, 302)
        db.session.refresh(conflict)
        self.assertFalse(conflict.resolved)
        self.assertIsNotNone(db.session.get(RosterConflict, conflict.id))

if __name__ == '__main__':
    unittest.main()
