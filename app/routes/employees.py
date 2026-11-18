from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from app.models import Employee, Pod, Brand, Process, EmployeeAssignment, WeeklyOffRule, LeaveRequest

employees_bp = Blueprint('employees', __name__)

@employees_bp.route('/')
def list_employees():
    pod_filter = request.args.get('pod_id', type=int)
    role_filter = request.args.get('role', type=str)
    search = request.args.get('q', type=str)

    query = Employee.query

    if pod_filter:
        query = query.filter_by(pod_id=pod_filter)
    if role_filter:
        query = query.filter_by(role=role_filter)
    if search:
        query = query.filter(
            (Employee.name.ilike(f'%{search}%')) |
            (Employee.emp_code.ilike(f'%{search}%')) |
            (Employee.email.ilike(f'%{search}%'))
        )

    employees = query.order_by(Employee.pod_id, Employee.name).all()
    pods = Pod.query.all()
    roles = ['Pod Lead', 'Senior Associate', 'Associate', 'Trainee']

    return render_template(
        'employees/list.html',
        employees=employees,
        pods=pods,
        roles=roles,
        selected_pod=pod_filter,
        selected_role=role_filter,
        search=search or ''
    )

@employees_bp.route('/add', methods=['GET', 'POST'])
def add_employee():
    pods = Pod.query.all()
    brands = Brand.query.all()
    processes = Process.query.all()

    if request.method == 'POST':
        emp_code = request.form.get('emp_code', '').strip().upper()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'Associate')
        pod_id = request.form.get('pod_id', type=int)
        max_consecutive = request.form.get('max_consecutive_days', type=int, default=6)

        # Validation
        if not emp_code or not name or not email:
            flash('Employee Code, Name, and Email are required.', 'danger')
            return redirect(url_for('employees.add_employee'))

        if Employee.query.filter((Employee.emp_code == emp_code) | (Employee.email == email)).first():
            flash('Employee with this Code or Email already exists.', 'danger')
            return redirect(url_for('employees.add_employee'))

        emp = Employee(
            emp_code=emp_code,
            name=name,
            email=email,
            phone=phone,
            role=role,
            pod_id=pod_id,
            hire_date=date.today(),
            is_active=True,
            max_consecutive_days=max_consecutive
        )
        db.session.add(emp)
        db.session.flush()

        # Default weekly off (Sunday)
        db.session.add(WeeklyOffRule(
            employee_id=emp.id,
            preferred_day_1=6,
            pattern_type='STAGGERED'
        ))

        # Primary skill assignment if selected
        brand_id = request.form.get('brand_id', type=int)
        process_id = request.form.get('process_id', type=int)
        if brand_id and process_id:
            db.session.add(EmployeeAssignment(
                employee_id=emp.id,
                brand_id=brand_id,
                process_id=process_id,
                is_primary=True,
                skill_level=3
            ))

        db.session.commit()
        flash(f'Employee {emp.name} ({emp.emp_code}) added successfully!', 'success')
        return redirect(url_for('employees.list_employees'))

    return render_template('employees/form.html', employee=None, pods=pods, brands=brands, processes=processes)

@employees_bp.route('/<int:emp_id>/edit', methods=['GET', 'POST'])
def edit_employee(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    pods = Pod.query.all()
    brands = Brand.query.all()
    processes = Process.query.all()

    if request.method == 'POST':
        emp.name = request.form.get('name', '').strip()
        emp.email = request.form.get('email', '').strip()
        emp.phone = request.form.get('phone', '').strip()
        emp.role = request.form.get('role', emp.role)
        emp.pod_id = request.form.get('pod_id', type=int)
        emp.max_consecutive_days = request.form.get('max_consecutive_days', type=int, default=6)
        emp.is_active = True if request.form.get('is_active') else False

        db.session.commit()
        flash(f'Employee {emp.name} updated successfully!', 'success')
        return redirect(url_for('employees.list_employees'))

    return render_template('employees/form.html', employee=emp, pods=pods, brands=brands, processes=processes)

@employees_bp.route('/<int:emp_id>/assign_skill', methods=['POST'])
def assign_skill(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    brand_id = request.form.get('brand_id', type=int)
    process_id = request.form.get('process_id', type=int)
    skill_level = request.form.get('skill_level', type=int, default=3)
    is_primary = True if request.form.get('is_primary') else False

    if brand_id and process_id:
        existing = EmployeeAssignment.query.filter_by(
            employee_id=emp.id,
            brand_id=brand_id,
            process_id=process_id
        ).first()

        if existing:
            existing.skill_level = skill_level
            existing.is_primary = is_primary
            flash(f"Updated certification for {emp.name}.", 'info')
        else:
            db.session.add(EmployeeAssignment(
                employee_id=emp.id,
                brand_id=brand_id,
                process_id=process_id,
                skill_level=skill_level,
                is_primary=is_primary
            ))
            flash(f"Added certification for {emp.name}.", 'success')

        db.session.commit()

    return redirect(url_for('employees.edit_employee', emp_id=emp.id))

@employees_bp.route('/skill/<int:assignment_id>/delete', methods=['POST'])
def delete_skill(assignment_id):
    assignment = EmployeeAssignment.query.get_or_404(assignment_id)
    emp_id = assignment.employee_id
    db.session.delete(assignment)
    db.session.commit()
    flash('Skill certification removed.', 'info')
    return redirect(url_for('employees.edit_employee', emp_id=emp_id))
