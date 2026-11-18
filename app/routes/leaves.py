from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from app.models import LeaveRequest, Holiday, WeeklyOffRule, Employee, Pod

leaves_bp = Blueprint('leaves', __name__)

@leaves_bp.route('/')
def leaves_list():
    leaves = LeaveRequest.query.order_by(LeaveRequest.start_date.desc()).all()
    holidays = Holiday.query.order_by(Holiday.date).all()
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.name).all()
    return render_template('leaves/leaves_list.html', leaves=leaves, holidays=holidays, employees=employees)

@leaves_bp.route('/apply', methods=['POST'])
def apply_leave():
    employee_id = request.form.get('employee_id', type=int)
    leave_type = request.form.get('leave_type', 'PL')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    reason = request.form.get('reason', '').strip()

    if not employee_id or not start_date_str or not end_date_str:
        flash('Employee, Start Date, and End Date are required.', 'danger')
        return redirect(url_for('leaves.leaves_list'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    if end_date < start_date:
        flash('End date cannot be prior to start date.', 'danger')
        return redirect(url_for('leaves.leaves_list'))

    leave = LeaveRequest(
        employee_id=employee_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        status='APPROVED',
        reason=reason
    )
    db.session.add(leave)
    db.session.commit()
    flash(f'{leave_type} request recorded successfully!', 'success')
    return redirect(url_for('leaves.leaves_list'))

@leaves_bp.route('/<int:leave_id>/status', methods=['POST'])
def update_leave_status(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    new_status = request.form.get('status', 'APPROVED')
    leave.status = new_status
    db.session.commit()
    flash(f'Leave status updated to {new_status}.', 'info')
    return redirect(url_for('leaves.leaves_list'))

@leaves_bp.route('/holidays/add', methods=['POST'])
def add_holiday():
    name = request.form.get('name', '').strip()
    date_str = request.form.get('date')
    is_mandatory = True if request.form.get('is_mandatory') else False

    if not name or not date_str:
        flash('Holiday name and date are required.', 'danger')
        return redirect(url_for('leaves.leaves_list'))

    hol_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    if Holiday.query.filter_by(date=hol_date).first():
        flash('Holiday for this date already exists.', 'warning')
        return redirect(url_for('leaves.leaves_list'))

    holiday = Holiday(name=name, date=hol_date, is_mandatory=is_mandatory)
    db.session.add(holiday)
    db.session.commit()
    flash(f'Holiday "{name}" on {hol_date} added successfully!', 'success')
    return redirect(url_for('leaves.leaves_list'))

@leaves_bp.route('/weekly-offs')
def weekly_off_rules():
    employees = Employee.query.filter_by(is_active=True).order_by(Employee.pod_id, Employee.name).all()
    days_map = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
    return render_template('leaves/rules.html', employees=employees, days_map=days_map)

@leaves_bp.route('/weekly-offs/update', methods=['POST'])
def update_weekly_off():
    employee_id = request.form.get('employee_id', type=int)
    day1 = request.form.get('preferred_day_1', type=int)
    day2_str = request.form.get('preferred_day_2')
    day2 = int(day2_str) if day2_str and day2_str != '' else None
    pattern = request.form.get('pattern_type', 'STAGGERED')

    rule = WeeklyOffRule.query.filter_by(employee_id=employee_id).first()
    if not rule:
        rule = WeeklyOffRule(employee_id=employee_id)
        db.session.add(rule)

    rule.preferred_day_1 = day1
    rule.preferred_day_2 = day2
    rule.pattern_type = pattern

    db.session.commit()
    flash('Weekly off preferences updated successfully!', 'success')
    return redirect(url_for('leaves.weekly_off_rules'))
