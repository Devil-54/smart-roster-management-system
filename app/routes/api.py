from datetime import datetime
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import (
    RosterSchedule, RosterAssignment, RosterConflict, Employee,
    Brand, Process, ShiftType
)
from app.services.validator import validate_roster, validate_single_assignment
from app.services.backup_engine import BackupRecommendationEngine

api_bp = Blueprint('api', __name__)

@api_bp.route('/roster/<int:roster_id>/assignment')
def get_assignment(roster_id):
    employee_id = request.args.get('employee_id', type=int)
    date_str = request.args.get('date')

    if not employee_id or not date_str:
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    assignment = RosterAssignment.query.filter_by(
        roster_id=roster_id,
        employee_id=employee_id,
        date=target_date
    ).first()

    if not assignment:
        return jsonify({'success': False, 'message': 'Assignment not found'}), 404

    return jsonify({'success': True, 'assignment': assignment.to_dict()})

@api_bp.route('/roster/<int:roster_id>/validate_edit', methods=['POST'])
def pre_validate_edit(roster_id):
    data = request.get_json() or {}
    employee_id = data.get('employee_id')
    date_str = data.get('date')
    brand_id = data.get('brand_id')
    process_id = data.get('process_id')
    shift_type_id = data.get('shift_type_id')
    assignment_type = data.get('assignment_type', 'WORK')

    if not employee_id or not date_str:
        return jsonify({'valid': False, 'errors': ['Missing required parameters.']}), 400

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    res = validate_single_assignment(
        roster_id=roster_id,
        employee_id=employee_id,
        target_date=target_date,
        brand_id=brand_id,
        process_id=process_id,
        shift_type_id=shift_type_id,
        assignment_type=assignment_type
    )
    return jsonify(res)

@api_bp.route('/roster/<int:roster_id>/edit_assignment', methods=['POST'])
def edit_assignment(roster_id):
    data = request.get_json() or {}
    employee_id = data.get('employee_id')
    date_str = data.get('date')
    assignment_type = data.get('assignment_type', 'WORK')
    brand_id = data.get('brand_id')
    process_id = data.get('process_id')
    shift_type_id = data.get('shift_type_id')
    notes = data.get('notes', 'Manual Admin Override')

    if not employee_id or not date_str:
        return jsonify({'success': False, 'message': 'Missing parameters'}), 400

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    # Prevalidate
    val = validate_single_assignment(
        roster_id=roster_id,
        employee_id=employee_id,
        target_date=target_date,
        brand_id=brand_id,
        process_id=process_id,
        shift_type_id=shift_type_id,
        assignment_type=assignment_type
    )

    if not val['valid']:
        return jsonify({
            'success': False,
            'message': 'Cannot save: hard constraint violation!',
            'errors': val['errors'],
            'warnings': val['warnings']
        }), 422

    assignment = RosterAssignment.query.filter_by(
        roster_id=roster_id,
        employee_id=employee_id,
        date=target_date
    ).first()

    if assignment:
        assignment.assignment_type = assignment_type
        assignment.brand_id = brand_id if assignment_type == 'WORK' else None
        assignment.process_id = process_id if assignment_type == 'WORK' else None
        assignment.shift_type_id = shift_type_id if assignment_type == 'WORK' else None
        assignment.notes = notes
        assignment.is_manual_override = True
    else:
        assignment = RosterAssignment(
            roster_id=roster_id,
            employee_id=employee_id,
            date=target_date,
            assignment_type=assignment_type,
            brand_id=brand_id if assignment_type == 'WORK' else None,
            process_id=process_id if assignment_type == 'WORK' else None,
            shift_type_id=shift_type_id if assignment_type == 'WORK' else None,
            notes=notes,
            is_manual_override=True
        )
        db.session.add(assignment)

    db.session.flush()

    # Revalidate whole roster
    conflicts = validate_roster(roster_id)
    roster = RosterSchedule.query.get(roster_id)
    if roster:
        roster.conflicts_count = len(conflicts)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Assignment updated successfully!',
        'warnings': val.get('warnings', []),
        'conflicts_count': len(conflicts)
    })

@api_bp.route('/roster/<int:roster_id>/swap_shifts', methods=['POST'])
def swap_shifts(roster_id):
    data = request.get_json() or {}
    emp1_id = data.get('emp1_id')
    emp2_id = data.get('emp2_id')
    date_str = data.get('date')

    if not emp1_id or not emp2_id or not date_str:
        return jsonify({'success': False, 'message': 'Missing parameters for shift swap.'}), 400

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    a1 = RosterAssignment.query.filter_by(roster_id=roster_id, employee_id=emp1_id, date=target_date).first()
    a2 = RosterAssignment.query.filter_by(roster_id=roster_id, employee_id=emp2_id, date=target_date).first()

    if not a1 or not a2:
        return jsonify({'success': False, 'message': 'Both employees must have existing schedule entries on this date.'}), 404

    # Swap shift attributes
    t_type1, t_brand1, t_proc1, t_shift1 = a1.assignment_type, a1.brand_id, a1.process_id, a1.shift_type_id
    t_type2, t_brand2, t_proc2, t_shift2 = a2.assignment_type, a2.brand_id, a2.process_id, a2.shift_type_id

    # Validate swap for employee 1 taking shift 2
    v1 = validate_single_assignment(roster_id, emp1_id, target_date, t_brand2, t_proc2, t_shift2, t_type2)
    # Validate swap for employee 2 taking shift 1
    v2 = validate_single_assignment(roster_id, emp2_id, target_date, t_brand1, t_proc1, t_shift1, t_type1)

    all_errors = v1['errors'] + v2['errors']
    all_warnings = v1['warnings'] + v2['warnings']

    if all_errors:
        return jsonify({
            'success': False,
            'message': 'Shift swap violates hard constraints!',
            'errors': all_errors,
            'warnings': all_warnings
        }), 422

    # Execute swap
    a1.assignment_type, a1.brand_id, a1.process_id, a1.shift_type_id = t_type2, t_brand2, t_proc2, t_shift2
    a2.assignment_type, a2.brand_id, a2.process_id, a2.shift_type_id = t_type1, t_brand1, t_proc1, t_shift1

    a1.is_manual_override = True
    a2.is_manual_override = True
    a1.notes = f"Swapped with {a2.employee.name}"
    a2.notes = f"Swapped with {a1.employee.name}"

    db.session.flush()
    conflicts = validate_roster(roster_id)
    roster = RosterSchedule.query.get(roster_id)
    if roster:
        roster.conflicts_count = len(conflicts)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"Successfully swapped shifts between {a1.employee.name} and {a2.employee.name} on {date_str}!",
        'warnings': all_warnings,
        'conflicts_count': len(conflicts)
    })

@api_bp.route('/roster/<int:roster_id>/unavailability/candidates')
def get_backup_candidates(roster_id):
    employee_id = request.args.get('employee_id', type=int)
    date_str = request.args.get('date')

    if not employee_id or not date_str:
        return jsonify({'success': False, 'message': 'Missing employee_id or date'}), 400

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    result = BackupRecommendationEngine.get_backup_candidates(roster_id, employee_id, target_date)
    return jsonify(result)

@api_bp.route('/roster/<int:roster_id>/unavailability/substitute', methods=['POST'])
def substitute_backup(roster_id):
    data = request.get_json() or {}
    absent_emp_id = data.get('absent_employee_id')
    backup_emp_id = data.get('backup_employee_id')
    date_str = data.get('date')
    reason = data.get('reason', 'Emergency absence')

    if not absent_emp_id or not backup_emp_id or not date_str:
        return jsonify({'success': False, 'message': 'Missing parameters for substitution'}), 400

    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    result = BackupRecommendationEngine.execute_substitution(
        roster_id=roster_id,
        absent_emp_id=absent_emp_id,
        backup_emp_id=backup_emp_id,
        incident_date=target_date,
        reason=reason
    )
    return jsonify(result)
