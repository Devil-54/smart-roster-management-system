from datetime import date, timedelta
from app.extensions import db
from app.models import (
    Employee, Pod, Brand, Process, ShiftType, EmployeeAssignment,
    LeaveRequest, RosterSchedule, RosterAssignment, UnavailabilityIncident
)
from app.services.validator import validate_roster, validate_single_assignment

class BackupRecommendationEngine:
    """
    Handles post-generation emergency unavailability.
    Scans, filters, and ranks eligible backup replacement candidates.
    """

    @staticmethod
    def get_backup_candidates(roster_id: int, employee_id: int, incident_date: date):
        """
        Analyzes the absent employee's shift and finds the best ranked substitutes.
        """
        # Find current assignment of the unavailable employee
        curr_assignment = RosterAssignment.query.filter_by(
            roster_id=roster_id,
            employee_id=employee_id,
            date=incident_date
        ).first()

        if not curr_assignment or curr_assignment.assignment_type != 'WORK':
            return {
                'success': False,
                'message': 'No active work shift found for this employee on the specified date.',
                'candidates': []
            }

        brand_id = curr_assignment.brand_id
        process_id = curr_assignment.process_id
        shift_id = curr_assignment.shift_type_id
        absent_emp = Employee.query.get(employee_id)

        # 1. Fetch all active employees certified for this brand & process (excluding absent employee)
        certifications = EmployeeAssignment.query.filter(
            EmployeeAssignment.brand_id == brand_id,
            EmployeeAssignment.process_id == process_id,
            EmployeeAssignment.employee_id != employee_id
        ).all()

        candidate_emp_ids = [c.employee_id for c in certifications]
        if not candidate_emp_ids:
            # Fallback: check employees certified for this process in ANY brand
            fallback_certs = EmployeeAssignment.query.filter(
                EmployeeAssignment.process_id == process_id,
                EmployeeAssignment.employee_id != employee_id
            ).all()
            candidate_emp_ids = list(set(c.employee_id for c in fallback_certs))

        candidates = Employee.query.filter(
            Employee.id.in_(candidate_emp_ids),
            Employee.is_active == True
        ).all()

        # Preload assignments on incident_date to check who is already working
        day_assignments = {
            a.employee_id: a for a in RosterAssignment.query.filter_by(
                roster_id=roster_id,
                date=incident_date
            ).all()
        }

        # Preload approved leaves on incident_date
        leaves_today = {
            l.employee_id: l for l in LeaveRequest.query.filter(
                LeaveRequest.status == 'APPROVED',
                LeaveRequest.start_date <= incident_date,
                LeaveRequest.end_date >= incident_date
            ).all()
        }

        # Total shifts worked in this roster for workload balancing
        all_roster_shifts = RosterAssignment.query.filter_by(
            roster_id=roster_id,
            assignment_type='WORK'
        ).all()
        shift_counts = {}
        for a in all_roster_shifts:
            shift_counts[a.employee_id] = shift_counts.get(a.employee_id, 0) + 1

        ranked = []
        for candidate in candidates:
            # Filter 1: Cannot already be on approved leave
            if candidate.id in leaves_today:
                continue

            # Filter 2: Cannot already be working a shift on this date
            cand_day_assignment = day_assignments.get(candidate.id)
            if cand_day_assignment and cand_day_assignment.assignment_type == 'WORK':
                continue

            # Filter 3: Check consecutive working days rule
            validation = validate_single_assignment(
                roster_id=roster_id,
                employee_id=candidate.id,
                target_date=incident_date,
                brand_id=brand_id,
                process_id=process_id,
                shift_type_id=shift_id,
                assignment_type='WORK'
            )
            if not validation['valid']:
                continue

            # Scoring factors
            score = 100
            reasons = []

            # Factor A: Same Pod Affinity (+40)
            if absent_emp.pod_id and candidate.pod_id == absent_emp.pod_id:
                score += 40
                reasons.append(f"Member of same {candidate.pod.name if candidate.pod else 'Pod'}")
            else:
                reasons.append("Cross-Pod qualified resource")

            # Factor B: Primary vs Secondary Certification (+25)
            cand_cert = next((c for c in candidate.assignments if c.brand_id == brand_id and c.process_id == process_id), None)
            if cand_cert and cand_cert.is_primary:
                score += 25
                reasons.append("Primary domain certification")
            else:
                score += 10
                reasons.append("Secondary domain certification")

            # Factor C: Skill level bonus
            skill_lvl = cand_cert.skill_level if cand_cert else 3
            score += skill_lvl * 5
            reasons.append(f"Skill rating: {skill_lvl}/5")

            # Factor D: Workload fairness (higher score for lower monthly workload)
            worked_shifts = shift_counts.get(candidate.id, 0)
            workload_bonus = max(0, 30 - worked_shifts) * 2
            score += workload_bonus
            reasons.append(f"Current monthly load: {worked_shifts} shifts")

            # Current status on incident date
            status_on_day = "Scheduled Off"
            if cand_day_assignment:
                status_on_day = cand_day_assignment.assignment_type.replace('_', ' ').title()

            ranked.append({
                'employee_id': candidate.id,
                'name': candidate.name,
                'emp_code': candidate.emp_code,
                'role': candidate.role,
                'pod_name': candidate.pod.name if candidate.pod else 'Unassigned',
                'status_on_day': status_on_day,
                'score': score,
                'reasons': reasons,
                'warnings': validation.get('warnings', [])
            })

        # Sort descending by score
        ranked.sort(key=lambda x: x['score'], reverse=True)

        return {
            'success': True,
            'incident_date': incident_date.strftime('%Y-%m-%d'),
            'absent_employee': {
                'id': absent_emp.id,
                'name': absent_emp.name,
                'emp_code': absent_emp.emp_code,
                'pod_name': absent_emp.pod.name if absent_emp.pod else 'Unassigned',
                'shift_name': curr_assignment.shift_type.name if curr_assignment.shift_type else 'General',
                'brand_name': curr_assignment.brand.name if curr_assignment.brand else 'N/A',
                'process_name': curr_assignment.process.name if curr_assignment.process else 'N/A'
            },
            'candidates': ranked
        }

    @staticmethod
    def execute_substitution(roster_id: int, absent_emp_id: int, backup_emp_id: int, incident_date: date, reason: str):
        """
        Executes backup substitution:
        1. Records UnavailabilityIncident
        2. Sets absent employee's shift to LEAVE/UNAVAILABLE
        3. Assigns backup employee to the work shift
        4. Triggers revalidation
        """
        absent_assignment = RosterAssignment.query.filter_by(
            roster_id=roster_id,
            employee_id=absent_emp_id,
            date=incident_date
        ).first()

        if not absent_assignment or absent_assignment.assignment_type != 'WORK':
            return {'success': False, 'message': 'Original assignment is not an active work shift.'}

        # Backup employee check
        backup_emp = Employee.query.get(backup_emp_id)
        if not backup_emp:
            return {'success': False, 'message': 'Backup employee not found.'}

        # Copy original shift details
        target_brand_id = absent_assignment.brand_id
        target_process_id = absent_assignment.process_id
        target_shift_id = absent_assignment.shift_type_id

        # Mark absent employee as unavailable / emergency leave
        absent_assignment.assignment_type = 'LEAVE'
        absent_assignment.notes = f"Emergency Unavailability: {reason}"
        absent_assignment.is_manual_override = True

        # Assign backup employee
        backup_assignment = RosterAssignment.query.filter_by(
            roster_id=roster_id,
            employee_id=backup_emp_id,
            date=incident_date
        ).first()

        if backup_assignment:
            backup_assignment.assignment_type = 'WORK'
            backup_assignment.brand_id = target_brand_id
            backup_assignment.process_id = target_process_id
            backup_assignment.shift_type_id = target_shift_id
            backup_assignment.notes = f"Substituted for {absent_assignment.employee.name}"
            backup_assignment.is_manual_override = True
        else:
            backup_assignment = RosterAssignment(
                roster_id=roster_id,
                date=incident_date,
                employee_id=backup_emp_id,
                brand_id=target_brand_id,
                process_id=target_process_id,
                shift_type_id=target_shift_id,
                assignment_type='WORK',
                notes=f"Substituted for {absent_assignment.employee.name}",
                is_manual_override=True
            )
            db.session.add(backup_assignment)

        # Record Incident
        incident = UnavailabilityIncident(
            roster_id=roster_id,
            employee_id=absent_emp_id,
            date=incident_date,
            reason=reason,
            status='SUBSTITUTED',
            substituted_by_id=backup_emp_id
        )
        db.session.add(incident)
        db.session.flush()

        # Revalidate roster
        conflicts = validate_roster(roster_id)
        roster = RosterSchedule.query.get(roster_id)
        if roster:
            roster.conflicts_count = len(conflicts)

        db.session.commit()

        return {
            'success': True,
            'message': f"Successfully substituted {backup_emp.name} for {absent_assignment.employee.name} on {incident_date}.",
            'incident_id': incident.id,
            'conflicts_count': len(conflicts)
        }
